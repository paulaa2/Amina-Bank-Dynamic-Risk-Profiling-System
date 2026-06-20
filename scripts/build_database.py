
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a plain script from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import db
from scripts.collectors import domain as domain_col
from scripts.collectors import funding as funding_col
from scripts.collectors import news as news_col
from scripts.collectors import registry as registry_col
from scripts.collectors import sanctions as sanctions_col
from scripts.collectors import topology as topology_col
from scripts.models import (
    Company,
    DomainRecord,
    FundingEvent,
    NewsArticle,
    RegistryRecord,
    SanctionsHit,
    TopologyNode,
    TopologyEdge,
)
from scripts.seed_kyc import BASELINE_COMPANIES

# Fields in seed_kyc that are NOT columns in Company (handled separately)
_SEED_EXTRA_KEYS = {"topology"}


def seed_companies(session) -> list[tuple[Company, list[dict]]]:
    """Insert baseline KYC profiles if the table is empty.

    Returns list of (Company, topology_entries) so the caller can
    run the topology collector after the main collection loop.
    """
    existing = session.query(Company).count()
    if existing:
        rows = session.query(Company).all()
        # Rebuild topology map from original seed so we can re-collect if needed
        topology_map = {d["legal_name"]: d.get("topology", []) for d in BASELINE_COMPANIES}
        return [(c, topology_map.get(c.legal_name, [])) for c in rows]

    result = []
    for data in BASELINE_COMPANIES:
        topology_entries = data.get("topology", [])
        company_data = {k: v for k, v in data.items() if k not in _SEED_EXTRA_KEYS}
        company = Company(**company_data)
        session.add(company)
        session.flush()
        db.log_audit(session, "seed_company", "company", company.id,
                     {"legal_name": company.legal_name})
        result.append((company, topology_entries))
    print(f"Seeded {len(result)} baseline KYC profiles.")
    return result


def collect_for_company(
    session,
    company: Company,
    topology_entries: list[dict],
    news_limit: int,
) -> None:
    name = company.legal_name
    print(f"\n=== {name} ===")

    # 1. News & adverse media
    news = news_col.fetch_news(name, limit_per_query=news_limit)
    for a in news:
        session.add(NewsArticle(company_id=company.id, **a))
    print(f"  news        : {len(news)} articles")

    # 2. Sanctions / watchlists
    sanctions = sanctions_col.fetch_sanctions(name)
    for h in sanctions:
        session.add(SanctionsHit(company_id=company.id, query_name=name, **h))
    print(f"  sanctions   : {len(sanctions)} hit(s)")

    # 3. Corporate registry (GLEIF)
    registry = registry_col.fetch_registry(legal_name=name, lei=company.lei)
    for r in registry:
        session.add(RegistryRecord(company_id=company.id, **r))
    print(f"  registry    : {len(registry)} record(s)")

    # 4. Funding / scale
    funding = funding_col.fetch_funding(name)
    for f in funding:
        session.add(FundingEvent(company_id=company.id, **f))
    print(f"  funding     : {len(funding)} event(s)")

    # 5. Domain / website
    domain = domain_col.fetch_domain(company.domain) if company.domain else None
    if domain:
        session.add(DomainRecord(company_id=company.id, **domain))
    print(f"  domain      : {'1 record' if domain else 'n/a'}")

    # 6. Topology: directors and shareholders
    if topology_entries:
        print(f"  topology    : {len(topology_entries)} person(s)/entit(ies) to screen")
        topology_col.build_topology(
            session,
            company_id=company.id,
            company_legal_name=name,
            topology_entries=topology_entries,
            news_limit_per_query=3,
        )

    session.flush()
    db.log_audit(session, "collect_signals", "company", company.id, {
        "news": len(news), "sanctions": len(sanctions), "registry": len(registry),
        "funding": len(funding), "domain": bool(domain),
        "topology_nodes": len(topology_entries),
    })


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the risk-profiling database.")
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables")
    parser.add_argument("--company", help="only process a company whose name contains this text")
    parser.add_argument("--no-collect", action="store_true",
                        help="only init schema and seed KYC baselines")
    parser.add_argument("--news-limit", type=int, default=25, help="max articles per company")
    args = parser.parse_args()

    from scripts import config as _cfg
    print(f"Database: {_cfg.DATABASE_URL}")
    db.init_db(drop=args.reset)
    print("Schema ready." + (" (reset)" if args.reset else ""))

    with db.session_scope() as session:
        company_pairs = seed_companies(session)

    if args.no_collect:
        print("\n--no-collect set: skipping data collection.")
        _summary()
        return

    for company, topology_entries in company_pairs:
        if args.company and args.company.lower() not in company.legal_name.lower():
            continue
        with db.session_scope() as session:
            company = session.merge(company)
            collect_for_company(session, company, topology_entries, args.news_limit)

    _summary()


def _summary() -> None:
    with db.session_scope() as session:
        print("\n===== DATABASE SUMMARY =====")
        for model, label in [
            (Company,      "companies (KYC baselines)"),
            (NewsArticle,  "news articles"),
            (SanctionsHit, "sanctions hits"),
            (RegistryRecord,"registry records"),
            (FundingEvent, "funding events"),
            (DomainRecord, "domain records"),
            (TopologyNode, "topology nodes (persons/entities)"),
            (TopologyEdge, "topology edges"),
        ]:
            print(f"  {label:<36}: {session.query(model).count()}")


if __name__ == "__main__":
    main()
