"""Read-only repository over the SQLite risk-profiling database.

This module is the engine's single integration boundary with the
data-collection layer. It reads the database produced by ``scripts/`` using a
direct, read-only SQLite connection and returns plain domain objects, so the
engine never imports collector / API code.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


def _db_path_from_url(database_url: str) -> Path:
    """Extract the file path from a ``sqlite:///`` SQLAlchemy URL."""
    prefix = "sqlite:///"
    if database_url.startswith(prefix):
        return Path(database_url[len(prefix):])
    return Path(database_url)


def _json_list(value) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


@dataclass
class TopologyNodeDTO:
    node_id: str
    name: str
    node_type: str
    role: str | None
    ownership_pct: float | None
    intrinsic_risk: float
    sanctions_hit: bool
    max_adverse_score: float
    adverse_news_count: int


@dataclass
class TopologyEdgeDTO:
    source_node_id: str
    target_node_id: str
    rel_type: str
    control_weight: float


@dataclass
class NewsEvent:
    title: str
    summary: str
    url: str
    source: str | None
    published_at: dt.datetime | None
    adverse_score: float
    matched_keywords: list[str] = field(default_factory=list)


@dataclass
class ClientProfile:
    id: int
    legal_name: str
    aliases: list[str]
    domain: str | None
    country: str | None
    legal_form: str | None
    jurisdiction: str | None
    expected_business_model: str | None
    expected_activity: str | None
    expected_monthly_volume_eur: float | None
    baseline_risk_rating: str | None
    notes: str | None
    nodes: list[TopologyNodeDTO] = field(default_factory=list)
    edges: list[TopologyEdgeDTO] = field(default_factory=list)

    # Stable node ID used for the company itself inside the contagion graph.
    company_node_id: str = "COMPANY"

    def profile_text(self) -> str:
        """Concise text describing the onboarding business model (for m0)."""
        parts = [self.legal_name, self.expected_business_model, self.expected_activity]
        return ". ".join(p for p in parts if p)

    def all_aliases(self) -> list[str]:
        """Client aliases plus every known graph-node name (for triage)."""
        names = [self.legal_name, *self.aliases]
        names.extend(n.name for n in self.nodes)
        return [n for n in names if n]


class ClientProfileRepository:
    """Loads client profiles, their control graph and Layer-1 news events."""

    def __init__(self, database_url: str) -> None:
        self.db_path = _db_path_from_url(database_url)
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Risk-profiling database not found at {self.db_path}. "
                "Build it first with: python -m scripts.build_database"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"file:{self.db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def list_companies(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, legal_name, country, baseline_risk_rating FROM companies "
                "ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def load_profile(self, name_substring: str | None = None, company_id: int | None = None) -> ClientProfile:
        """Load a single client profile with its full control graph.

        Selection priority: explicit ``company_id``, else case-insensitive
        substring on ``legal_name``, else the first company in the table.
        """
        with self._connect() as conn:
            company = self._select_company(conn, name_substring, company_id)
            nodes, node_id_by_pk = self._load_nodes(conn, company["id"])
            edges = self._load_edges(conn, company, node_id_by_pk)

        return ClientProfile(
            id=company["id"],
            legal_name=company["legal_name"],
            aliases=_json_list(company["aliases"]),
            domain=company["domain"],
            country=company["country"],
            legal_form=company["legal_form"],
            jurisdiction=company["jurisdiction"],
            expected_business_model=company["expected_business_model"],
            expected_activity=company["expected_activity"],
            expected_monthly_volume_eur=company["expected_monthly_volume_eur"],
            baseline_risk_rating=company["baseline_risk_rating"],
            notes=company["notes"],
            nodes=nodes,
            edges=edges,
            company_node_id=f"COMPANY_{company['id']}",
        )

    def load_news(self, company_id: int, limit: int = 50) -> list[NewsEvent]:
        """Return the most adverse, most recent news events for a company."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT title, summary, url, source, published_at, adverse_score, "
                "matched_keywords FROM news_articles WHERE company_id = ? "
                "ORDER BY adverse_score DESC, published_at DESC LIMIT ?",
                (company_id, limit),
            ).fetchall()
        events: list[NewsEvent] = []
        for r in rows:
            events.append(
                NewsEvent(
                    title=r["title"] or "",
                    summary=r["summary"] or "",
                    url=r["url"] or "",
                    source=r["source"],
                    published_at=_parse_dt(r["published_at"]),
                    adverse_score=float(r["adverse_score"] or 0.0),
                    matched_keywords=_json_list(r["matched_keywords"]),
                )
            )
        return events

    # -- internals ---------------------------------------------------------

    @staticmethod
    def _select_company(conn, name_substring, company_id) -> sqlite3.Row:
        if company_id is not None:
            row = conn.execute(
                "SELECT * FROM companies WHERE id = ?", (company_id,)
            ).fetchone()
            if row is None:
                raise LookupError(f"No company with id={company_id}.")
            return row
        if name_substring:
            row = conn.execute(
                "SELECT * FROM companies WHERE LOWER(legal_name) LIKE ? ORDER BY id LIMIT 1",
                (f"%{name_substring.lower()}%",),
            ).fetchone()
            if row is None:
                raise LookupError(f"No company matching '{name_substring}'.")
            return row
        row = conn.execute("SELECT * FROM companies ORDER BY id LIMIT 1").fetchone()
        if row is None:
            raise LookupError("The companies table is empty; build the database first.")
        return row

    @staticmethod
    def _load_nodes(conn, company_id):
        rows = conn.execute(
            "SELECT id, node_id, name, node_type, role, ownership_pct, intrinsic_risk, "
            "sanctions_hit, max_adverse_score, adverse_news_count "
            "FROM topology_nodes WHERE company_id = ?",
            (company_id,),
        ).fetchall()
        nodes: list[TopologyNodeDTO] = []
        node_id_by_pk: dict[int, str] = {}
        for r in rows:
            node_id_by_pk[r["id"]] = r["node_id"]
            nodes.append(
                TopologyNodeDTO(
                    node_id=r["node_id"],
                    name=r["name"],
                    node_type=r["node_type"],
                    role=r["role"],
                    ownership_pct=r["ownership_pct"],
                    intrinsic_risk=float(r["intrinsic_risk"] or 0.0),
                    sanctions_hit=bool(r["sanctions_hit"]),
                    max_adverse_score=float(r["max_adverse_score"] or 0.0),
                    adverse_news_count=int(r["adverse_news_count"] or 0),
                )
            )
        return nodes, node_id_by_pk

    @staticmethod
    def _load_edges(conn, company, node_id_by_pk):
        company_node_id = f"COMPANY_{company['id']}"
        rows = conn.execute(
            "SELECT source_node_id, target_company_id, rel_type, control_weight "
            "FROM topology_edges WHERE target_company_id = ?",
            (company["id"],),
        ).fetchall()
        edges: list[TopologyEdgeDTO] = []
        for r in rows:
            source = node_id_by_pk.get(r["source_node_id"])
            if source is None:
                continue
            edges.append(
                TopologyEdgeDTO(
                    source_node_id=source,
                    target_node_id=company_node_id,
                    rel_type=r["rel_type"],
                    control_weight=float(r["control_weight"] or 1.0),
                )
            )
        return edges


def _parse_dt(value) -> dt.datetime | None:
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return value
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None
