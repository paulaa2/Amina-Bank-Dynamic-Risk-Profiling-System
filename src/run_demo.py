"""Command-line demo for the Perpetual KYC drift engine.

Usage examples (run from the project root)::

    python -m src.run_demo --list
    python -m src.run_demo --company MicroStrategy
    python -m src.run_demo --company "VTB" --max-events 6 --show-report
    python -m src.run_demo --company OpenAI --json
"""

from __future__ import annotations

import argparse
import json

from .config import load_config
from .pipeline import EngineReport, PerpetualKYCPipeline


def _print_human(report: EngineReport) -> None:
    line = "=" * 72
    print(line)
    print("AMINA BANK - PERPETUAL KYC (pKYC) DRIFT ENGINE")
    print(line)

    c = report.client
    print(f"\nClient        : {c['legal_name']} ({c['country']}, {c['jurisdiction']})")
    print(f"Baseline KYC  : risk={c['baseline_risk_rating']} | model: {c['expected_business_model']}")
    print(f"Graph nodes   : {c['known_graph_nodes']} known directors/owners")

    s = report.security
    print(f"\n[Phase 1] Masking proxy: {s['masked_entities']} sensitive entities tokenised "
          f"(client -> {s['company_token']}).")

    t = report.topology
    print(f"\n[Phase 2/3] Topological contagion: company exposure = {t['company_exposure']}")
    if t["circular_ownership_detected"]:
        print("            Circular ownership detected (layering signal).")
    for contrib in t["top_contributors"]:
        print(f"            - {contrib['name']} [{contrib['type']}/{contrib['relation']}] "
              f"intrinsic={contrib['intrinsic_risk']} -> contributes {contrib['contributed']}")

    st = report.streams
    print(f"\n[Phase 4] Multi-stream fusion (Bonferroni x{st['bonferroni_scale']}):")
    print(f"            semantic   : stat={st['semantic']['last_statistic']} / thr={st['semantic']['threshold']}")
    print(f"            topology   : stat={st['topology']['last_statistic']} / thr={st['topology']['threshold']}")
    print(f"            behavioral : stat={st['behavioral_tx']['last_statistic']} / thr={st['behavioral_tx']['threshold']}")

    processed = [e for e in report.events if e.triaged_in]
    discarded = len(report.events) - len(processed)
    print(f"\n[Stages 1-3] Events seen={len(report.events)} | discarded by triage={discarded} "
          f"| processed={len(processed)}")
    for e in processed[:6]:
        flag = " (fallback)" if e.used_fallback else ""
        print(f"            risk={e.combined_risk:<6} dist={e.semantic_distance:<6}{flag} | {e.title[:70]}")

    d = report.decision
    verdict = "ALARM" if d["alarm_fired"] else "no alarm"
    print(f"\n[Decision] {verdict}: max combined risk = {d['max_combined_risk']} "
          f"(threshold {d['threshold']})")
    if d["triggering_event"]:
        print(f"            triggering event: {d['triggering_event']}")

    cost = report.cost
    print(f"\n[Cost] events_seen={cost['events_seen']} | cloud_reports={cost['cloud_reports_generated']}")
    print(f"       local tokens (free): {cost['local_tokens']['prompt']}+{cost['local_tokens']['completion']}")
    print(f"       cloud tokens: {cost['cloud_tokens']['prompt']}+{cost['cloud_tokens']['completion']} "
          f"= ${cost['cloud_tokens']['cost_usd']}")
    print(f"       projected cloud cost / 1000 analyses = ${cost['projected_cloud_cost_per_1000_analyses_usd']}")

    if report.governance:
        g = report.governance
        print(f"\n[Phase 6] Governance: status={g['status']} | analyst={g['assigned_analyst']} "
              f"-> approver={g['compliance_approver']}")
        for entry in g["audit_trail"]:
            print(f"            {entry['timestamp']} [{entry['user']}] {entry['action']}")

    if report.warnings:
        print("\n[Warnings]")
        for w in report.warnings:
            print(f"  - {w}")

    if report.report_markdown:
        print("\n" + line)
        print("AML COMPLIANCE REPORT (Stage 4)")
        print(line)
        print(report.report_markdown)


def _report_to_dict(report: EngineReport) -> dict:
    return {
        "client": report.client,
        "security": report.security,
        "topology": report.topology,
        "streams": report.streams,
        "decision": report.decision,
        "cost": report.cost,
        "governance": report.governance,
        "warnings": report.warnings,
        "events": [
            {
                "title": e.title,
                "triaged_in": e.triaged_in,
                "semantic_distance": e.semantic_distance,
                "combined_risk": e.combined_risk,
                "alarms": e.alarms,
            }
            for e in report.events
        ],
        "report_markdown": report.report_markdown,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AMINA Bank pKYC drift engine demo.")
    parser.add_argument("--company", help="substring of the client legal name to analyse")
    parser.add_argument("--id", type=int, help="explicit company id to analyse")
    parser.add_argument("--max-events", type=int, help="cap on Layer-1 events processed")
    parser.add_argument(
        "--simulate-tx-anomaly",
        action="store_true",
        help="inject a simulated transactional spike to exercise the behavioural stream",
    )
    parser.add_argument("--list", action="store_true", help="list available clients and exit")
    parser.add_argument("--show-report", action="store_true", help="always print the AML report")
    parser.add_argument("--json", action="store_true", help="emit the full result as JSON")
    args = parser.parse_args()

    config = load_config()

    if args.list:
        repo = PerpetualKYCPipeline(config).repository
        print("Available clients:")
        for row in repo.list_companies():
            print(f"  [{row['id']}] {row['legal_name']} ({row['country']}, {row['baseline_risk_rating']})")
        return

    pipeline = PerpetualKYCPipeline(config)
    report = pipeline.run(
        name_substring=args.company,
        company_id=args.id,
        max_events=args.max_events,
        simulate_tx_anomaly=args.simulate_tx_anomaly,
    )

    if args.json:
        print(json.dumps(_report_to_dict(report), ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(report)


if __name__ == "__main__":
    main()
