
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


PUBLIC = "public"     
INTERNAL = "internal"  
DERIVED = "derived"    


class Base(DeclarativeBase):
    pass


class Company(Base):
    """Layer 2 - simulated internal KYC baseline for a monitored entity."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    data_classification: Mapped[str] = mapped_column(String(16), default=INTERNAL)

    # Identity
    legal_name: Mapped[str] = mapped_column(String(255), index=True)
    aliases: Mapped[list | None] = mapped_column(JSON, default=list)
    domain: Mapped[str | None] = mapped_column(String(255))
    lei: Mapped[str | None] = mapped_column(String(20), index=True)
    country: Mapped[str | None] = mapped_column(String(8))
    legal_form: Mapped[str | None] = mapped_column(String(120))
    jurisdiction: Mapped[str | None] = mapped_column(String(120))

    # Baseline KYC assumptions (what the bank believed at onboarding)
    expected_business_model: Mapped[str | None] = mapped_column(Text)
    expected_activity: Mapped[str | None] = mapped_column(Text)
    expected_monthly_volume_eur: Mapped[float | None] = mapped_column(Float)
    baseline_risk_rating: Mapped[str | None] = mapped_column(String(16))  # LOW/MEDIUM/HIGH
    onboarding_date: Mapped[dt.date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    news = relationship("NewsArticle", back_populates="company", cascade="all, delete-orphan")
    sanctions = relationship("SanctionsHit", back_populates="company", cascade="all, delete-orphan")
    registry = relationship("RegistryRecord", back_populates="company", cascade="all, delete-orphan")
    funding = relationship("FundingEvent", back_populates="company", cascade="all, delete-orphan")
    domains = relationship("DomainRecord", back_populates="company", cascade="all, delete-orphan")
    signals = relationship("RiskSignal", back_populates="company", cascade="all, delete-orphan")
    topology_nodes = relationship("TopologyNode", back_populates="company", cascade="all, delete-orphan")


class NewsArticle(Base):
    """Layer 1 - news & adverse media (Google News RSS)."""

    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    data_classification: Mapped[str] = mapped_column(String(16), default=PUBLIC)
    source_api: Mapped[str] = mapped_column(String(40), default="google_news_rss")

    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, index=True)
    source: Mapped[str | None] = mapped_column(String(255))
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    summary: Mapped[str | None] = mapped_column(Text)

    # Cheap Stage-1 signal (keyword based, no LLM)
    adverse_score: Mapped[float] = mapped_column(Float, default=0.0)
    matched_keywords: Mapped[list | None] = mapped_column(JSON, default=list)

    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    company = relationship("Company", back_populates="news")


class SanctionsHit(Base):
    """Layer 1 - sanctions & watchlist match (OpenSanctions)."""

    __tablename__ = "sanctions_hits"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    data_classification: Mapped[str] = mapped_column(String(16), default=PUBLIC)
    source_api: Mapped[str] = mapped_column(String(40), default="opensanctions")

    query_name: Mapped[str] = mapped_column(String(255))
    matched_name: Mapped[str] = mapped_column(String(512))
    entity_id: Mapped[str | None] = mapped_column(String(120))
    schema: Mapped[str | None] = mapped_column(String(64))
    datasets: Mapped[list | None] = mapped_column(JSON, default=list)
    countries: Mapped[list | None] = mapped_column(JSON, default=list)
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    source_url: Mapped[str | None] = mapped_column(Text)

    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    company = relationship("Company", back_populates="sanctions")


class RegistryRecord(Base):
    """Layer 1 - corporate registry / ownership data (GLEIF LEI)."""

    __tablename__ = "registry_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    data_classification: Mapped[str] = mapped_column(String(16), default=PUBLIC)
    source_api: Mapped[str] = mapped_column(String(40), default="gleif")

    lei: Mapped[str | None] = mapped_column(String(20), index=True)
    legal_name: Mapped[str | None] = mapped_column(String(512))
    other_names: Mapped[list | None] = mapped_column(JSON, default=list)
    entity_status: Mapped[str | None] = mapped_column(String(40))     # ACTIVE / INACTIVE
    lei_status: Mapped[str | None] = mapped_column(String(40))        # ISSUED / LAPSED / RETIRED
    legal_form: Mapped[str | None] = mapped_column(String(255))
    jurisdiction: Mapped[str | None] = mapped_column(String(40))
    country: Mapped[str | None] = mapped_column(String(8))
    address: Mapped[str | None] = mapped_column(Text)
    registration_date: Mapped[dt.datetime | None] = mapped_column(DateTime)
    last_update_date: Mapped[dt.datetime | None] = mapped_column(DateTime)
    parent_lei: Mapped[str | None] = mapped_column(String(20))
    source_url: Mapped[str | None] = mapped_column(Text)

    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    company = relationship("Company", back_populates="registry")


class FundingEvent(Base):
    """Layer 1 - funding & startup intelligence (news-derived, free)."""

    __tablename__ = "funding_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    data_classification: Mapped[str] = mapped_column(String(16), default=PUBLIC)
    source_api: Mapped[str] = mapped_column(String(40), default="google_news_rss")

    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(255))
    amount_value: Mapped[float | None] = mapped_column(Float)
    amount_currency: Mapped[str | None] = mapped_column(String(8))
    round_type: Mapped[str | None] = mapped_column(String(64))
    announced_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    company = relationship("Company", back_populates="funding")


class DomainRecord(Base):
    """Layer 1 - website & domain monitoring (RDAP/WHOIS + Wayback)."""

    __tablename__ = "domain_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    data_classification: Mapped[str] = mapped_column(String(16), default=PUBLIC)
    source_api: Mapped[str] = mapped_column(String(40), default="rdap")

    domain: Mapped[str] = mapped_column(String(255), index=True)
    registrar: Mapped[str | None] = mapped_column(String(255))
    statuses: Mapped[list | None] = mapped_column(JSON, default=list)
    nameservers: Mapped[list | None] = mapped_column(JSON, default=list)
    registration_date: Mapped[dt.datetime | None] = mapped_column(DateTime)
    last_changed_date: Mapped[dt.datetime | None] = mapped_column(DateTime)
    expiration_date: Mapped[dt.datetime | None] = mapped_column(DateTime)

    # Wayback Machine earliest/most-recent snapshot (website history signal)
    wayback_first_snapshot: Mapped[dt.datetime | None] = mapped_column(DateTime)
    wayback_last_snapshot_url: Mapped[str | None] = mapped_column(Text)

    fetched_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    company = relationship("Company", back_populates="domains")


class RiskSignal(Base):
    """Derived layer - normalised risk flag mapped to the challenge use cases."""

    __tablename__ = "risk_signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    data_classification: Mapped[str] = mapped_column(String(16), default=DERIVED)

    signal_type: Mapped[str] = mapped_column(String(64), index=True)  # e.g. SANCTIONS_HIT
    flag: Mapped[str] = mapped_column(String(120))                    # human label
    severity: Mapped[str] = mapped_column(String(16))                 # LOW/MEDIUM/HIGH/CRITICAL
    confidence: Mapped[float] = mapped_column(Float, default=0.5)     # 0..1
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    recommended_action: Mapped[str | None] = mapped_column(Text)

    # Explainability / auditability: where did the evidence come from
    evidence_source: Mapped[str | None] = mapped_column(String(40))   # which collector
    source_citations: Mapped[list | None] = mapped_column(JSON, default=list)

    # Decision governance lifecycle
    status: Mapped[str] = mapped_column(String(24), default="NEW")    # NEW/UNDER_REVIEW/...
    reviewed_by: Mapped[str | None] = mapped_column(String(120))

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    company = relationship("Company", back_populates="signals")


class TopologyNode(Base):
    """Layer 2 — person or entity in the corporate graph (director, shareholder, subsidiary).

    Each node is linked to a Company (the monitored client). The graph engine
    propagates risk from flagged nodes to the company via TopologyEdge.
    """

    __tablename__ = "topology_nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    data_classification: Mapped[str] = mapped_column(String(16), default=INTERNAL)

    node_id: Mapped[str] = mapped_column(String(120), index=True)   # stable ID used in the graph
    name: Mapped[str] = mapped_column(String(255), index=True)       # real name (masked before LLM)
    node_type: Mapped[str] = mapped_column(String(32))               # PERSON / COMPANY / JURISDICTION
    role: Mapped[str | None] = mapped_column(String(120))            # CEO, Director, Shareholder 25%…
    ownership_pct: Mapped[float | None] = mapped_column(Float)       # % if shareholder

    # Risk computed by the topology collector from news + sanctions
    intrinsic_risk: Mapped[float] = mapped_column(Float, default=0.0)   # 0..1
    sanctions_hit: Mapped[bool] = mapped_column(default=False)
    max_adverse_score: Mapped[float] = mapped_column(Float, default=0.0)
    adverse_news_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    company = relationship("Company", back_populates="topology_nodes")
    outgoing_edges = relationship(
        "TopologyEdge", foreign_keys="TopologyEdge.source_node_id",
        back_populates="source_node", cascade="all, delete-orphan",
    )


class TopologyEdge(Base):
    """Directed edge in the compliance graph: source --[rel_type]--> target_company.

    Mirrors the edge model from ComplianceDirectedGraph in final_implementation.md:
      W = 1.0  for DIRECTS, OWNS_MAJORITY  (full contagion)
      W = 0.1  for LOCATED_AT, OWNS_MINORITY  (attenuated)
    """

    __tablename__ = "topology_edges"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_node_id: Mapped[int] = mapped_column(ForeignKey("topology_nodes.id"), index=True)
    target_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)

    rel_type: Mapped[str] = mapped_column(String(32))        # DIRECTS / OWNS_MAJORITY / OWNS_MINORITY / LOCATED_AT
    control_weight: Mapped[float] = mapped_column(Float, default=1.0)   # W in the contagion formula

    source_node = relationship("TopologyNode", foreign_keys=[source_node_id], back_populates="outgoing_edges")
    target_company = relationship("Company")


class AuditLog(Base):
    """Governance - immutable trail of system actions."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(120), default="system")
    action: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict | None] = mapped_column(JSON, default=dict)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
