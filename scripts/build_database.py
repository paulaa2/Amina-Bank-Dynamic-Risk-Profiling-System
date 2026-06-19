"""End-to-end database generator.

Run from the project root with either:
    python scripts/build_database.py [options]
    python -m scripts.build_database [options]

Steps:
  1. Initialise the SQLite schema (optionally resetting it).
  2. Seed Layer 2 baseline KYC profiles.
  3. For each company, collect Layer 1 public signals from the free APIs.
  4. Persist everything with an audit trail.
"""
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
from scripts.models import (
    Company,
    DomainRecord,
    FundingEvent,
    NewsArticle,
    RegistryRecord,
    SanctionsHit,
)
from scripts.seed_kyc import BASELINE_COMPANIES


def seed_companies(session) -> list[Company]:
    """Insert baseline KYC profiles if the table is empty."""
    existing = session.query(Company).count()
    if existing:
        return session.query(Company).all()
    companies = []
    for data in BASELINE_COMPANIES:
        company = Company(**data)
        session.add(company)
        session.flush()
        db.log_audit(session, "seed_company", "company", company.id,
                     {"legal_name": company.legal_name})
        companies.append(company)
    print(f"Seeded {len(companies)} baseline KYC profiles.")
    return companies


def collect_for_company(session, company: Company, news_limit: int) -> None:
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

    session.flush()
    db.log_audit(session, "collect_signals", "company", company.id, {
        "news": len(news), "sanctions": len(sanctions), "registry": len(registry),
        "funding": len(funding), "domain": bool(domain),
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
        companies = seed_companies(session)

    if args.no_collect:
        print("\n--no-collect set: skipping data collection.")
        _summary()
        return

    for company in companies:
        if args.company and args.company.lower() not in company.legal_name.lower():
            continue
        with db.session_scope() as session:
            company = session.merge(company)
            collect_for_company(session, company, args.news_limit)

    _summary()


def _summary() -> None:
    with db.session_scope() as session:
        print("\n===== DATABASE SUMMARY =====")
        for model, label in [
            (Company, "companies (KYC baselines)"),
            (NewsArticle, "news articles"),
            (SanctionsHit, "sanctions hits"),
            (RegistryRecord, "registry records"),
            (FundingEvent, "funding events"),
            (DomainRecord, "domain records"),
        ]:
            print(f"  {label:<28}: {session.query(model).count()}")


if __name__ == "__main__":
    main()
