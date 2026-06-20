
from __future__ import annotations

import hashlib
import re
import urllib.parse
from typing import Optional

import feedparser

from .base import adverse_media_score, parse_date


# ── news query templates (same shape as news.py but person-oriented) ──────────

_QUERY_TEMPLATES: list[tuple[str, str]] = [
    ("adverse_en",  '"{name}" (fraud OR corruption OR sanction OR arrest OR charged OR convicted OR "money laundering")'),
    ("legal_en",    '"{name}" (indicted OR arrested OR court OR trial OR sentence OR prison OR plea)'),
    ("regulatory_en",'"{name}" (fine OR penalty OR SEC OR OFAC OR FCA OR investigation OR watchlist)'),
]

_RSS_BASE = "https://news.google.com/rss/search"


def _stable_node_id(company_legal_name: str, person_name: str) -> str:
    """Deterministic ID so re-runs don't create duplicate rows."""
    raw = f"{company_legal_name}|{person_name}".lower().strip()
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _news_for_person(name: str, limit_per_query: int = 5) -> list[dict]:
    """Return a deduplicated list of news dicts for the named individual."""
    seen_urls: set[str] = set()
    results: list[dict] = []

    for label, template in _QUERY_TEMPLATES:
        query = template.format(name=name)
        params = urllib.parse.urlencode({
            "q": query,
            "hl": "en-US",
            "gl": "US",
            "ceid": "US:en",
        })
        url = f"{_RSS_BASE}?{params}"
        try:
            feed = feedparser.parse(url)
        except Exception:
            continue

        count = 0
        for entry in feed.entries:
            if count >= limit_per_query:
                break
            link = getattr(entry, "link", "") or ""
            if link in seen_urls:
                continue
            seen_urls.add(link)

            title   = getattr(entry, "title", "") or ""
            summary = getattr(entry, "summary", "") or ""
            source  = ""
            if hasattr(entry, "source") and isinstance(entry.source, dict):
                source = entry.source.get("title", "")

            score, keywords = adverse_media_score(f"{title} {summary}")
            results.append({
                "title":          title,
                "url":            link,
                "published_at":   parse_date(getattr(entry, "published", None)),
                "source":         source,
                "adverse_score":  score,
                "keywords":       keywords,
                "query_label":    label,
            })
            count += 1

    return results


def _sanctions_for_person(name: str) -> tuple[bool, float]:
    """Return (hit, score). Reuses the bulk-CSV matcher from sanctions.py."""
    try:
        from .sanctions import fetch_sanctions
        hits = fetch_sanctions(name)
        if hits:
            best = max(h.get("score", 0.0) for h in hits)
            return True, min(best / 100.0, 1.0)
    except Exception:
        pass
    return False, 0.0


def build_topology(
    session,
    company_id: int,
    company_legal_name: str,
    topology_entries: list[dict],
    news_limit_per_query: int = 5,
    verbose: bool = True,
) -> list[dict]:
    """Create TopologyNode + TopologyEdge rows for all entries in topology.

    Returns a summary list of dicts for logging.
    """
    from ..models import TopologyNode, TopologyEdge  # late import avoids circular deps

    summary: list[dict] = []

    for entry in topology_entries:
        person_name    = entry["name"]
        node_type      = entry.get("node_type", "PERSON")
        role           = entry.get("role")
        ownership_pct  = entry.get("ownership_pct")
        rel_type       = entry.get("rel_type", "DIRECTS")
        control_weight = entry.get("control_weight", 1.0)

        node_id = _stable_node_id(company_legal_name, person_name)

        if verbose:
            print(f"  [topology] {node_type}: {person_name} ({rel_type})")

        # 1. Search news
        news_items = _news_for_person(person_name, limit_per_query=news_limit_per_query)
        adverse_scores = [n["adverse_score"] for n in news_items if n["adverse_score"] > 0]
        max_adverse    = max(adverse_scores, default=0.0)
        adverse_count  = sum(1 for s in adverse_scores if s > 0.2)

        # 2. Sanctions screening
        sanctions_hit, sanctions_score = _sanctions_for_person(person_name)

        # 3. Intrinsic risk: sanctions trumps everything, otherwise max adverse
        intrinsic_risk = max(
            1.0 if sanctions_hit else 0.0,
            max_adverse,
            sanctions_score,
        )

        if verbose:
            flag = " [SANCTIONS HIT]" if sanctions_hit else ""
            print(f"    -> adverse news: {len(adverse_scores)}, max_score={max_adverse:.2f}, intrinsic_risk={intrinsic_risk:.2f}{flag}")

        # 4. Persist node (upsert-style: delete old then insert)
        old = session.query(TopologyNode).filter_by(
            company_id=company_id, node_id=node_id
        ).first()
        if old:
            session.delete(old)
            session.flush()

        node = TopologyNode(
            company_id        = company_id,
            node_id           = node_id,
            name              = person_name,
            node_type         = node_type,
            role              = role,
            ownership_pct     = ownership_pct,
            intrinsic_risk    = intrinsic_risk,
            sanctions_hit     = sanctions_hit,
            max_adverse_score = max_adverse,
            adverse_news_count= adverse_count,
        )
        session.add(node)
        session.flush()  # get node.id

        # 5. Create directed edge -> company
        edge = TopologyEdge(
            source_node_id   = node.id,
            target_company_id= company_id,
            rel_type         = rel_type,
            control_weight   = control_weight,
        )
        session.add(edge)

        summary.append({
            "name":           person_name,
            "intrinsic_risk": intrinsic_risk,
            "sanctions_hit":  sanctions_hit,
            "adverse_count":  adverse_count,
        })

    session.commit()
    return summary
