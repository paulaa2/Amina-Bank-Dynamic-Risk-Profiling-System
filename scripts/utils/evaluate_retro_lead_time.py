"""Retrospective lead-time evaluation for the demo clients.

The goal is presentation evidence, not a regulatory backtest: compare the
engine's first alarm timestamp against a public reference date for each case.
Report generation is disabled to avoid cloud-token cost during repeated runs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from src.config import load_config
from src.pipeline import PerpetualKYCPipeline


REFERENCE_CASES: list[dict[str, str]] = [
    {
        "company": "Wirecard",
        "label": "Wirecard AG",
        "case_type": "fraud / insolvency",
        "reference_date": "2020-06-25",
        "reference_event": "Wirecard files for insolvency after the EUR 1.9B accounting scandal.",
    },
    {
        "company": "FTX",
        "label": "FTX Trading Ltd",
        "case_type": "fraud / bankruptcy",
        "reference_date": "2022-11-11",
        "reference_event": "FTX Group files for Chapter 11 bankruptcy.",
    },
    {
        "company": "MicroStrategy",
        "label": "MicroStrategy Incorporated",
        "case_type": "semantic drift",
        "reference_date": "2020-08-11",
        "reference_event": "MicroStrategy announces its first major Bitcoin treasury purchase.",
    },
    {
        "company": "VTB",
        "label": "VTB Bank",
        "case_type": "sanctions",
        "reference_date": "2022-02-24",
        "reference_event": "Full-blocking sanctions announced after Russia's invasion of Ukraine.",
    },
    {
        "company": "Gazprombank",
        "label": "Gazprombank",
        "case_type": "sanctions / state exposure",
        "reference_date": "2022-03-12",
        "reference_event": "Public adverse coverage of Gazprombank dodging Western sanctions.",
    },
    {
        "company": "Surgutneftegas",
        "label": "Surgutneftegas",
        "case_type": "sanctions",
        "reference_date": "2025-01-10",
        "reference_event": "US/UK sanctions package targets Russian oil majors.",
    },
    {
        "company": "OpenAI",
        "label": "OpenAI",
        "case_type": "regulatory / safety litigation",
        "reference_date": "2026-06-01",
        "reference_event": "Public reporting of safety and consumer-protection legal pressure.",
    },
]


def _parse_date(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value).replace(tzinfo=dt.timezone.utc)


def _parse_day(value: str) -> dt.date:
    return dt.datetime.fromisoformat(value).date()


def _event_timestamp_by_title(pipeline: PerpetualKYCPipeline, company: str, max_events: int) -> dict[str, str]:
    profile = pipeline.repository.load_profile(name_substring=company)
    events = pipeline._chronological_events(
        pipeline.repository.load_news(profile.id, limit=max(max_events * 3, 30))
    )[:max_events]
    out: dict[str, str] = {}
    for event in events:
        if event.published_at:
            out[event.title] = pipeline._event_timestamp_str(event)
    return out


def _evaluate_case(case: dict[str, str], max_events: int) -> dict[str, Any]:
    pipeline = PerpetualKYCPipeline(load_config())

    # We only need the alarm decision for retrospective metrics.
    pipeline._draft_report = lambda trace, warnings: "Report generation skipped for retrospective evaluation."  # type: ignore[method-assign]

    timestamps = _event_timestamp_by_title(pipeline, case["company"], max_events)
    report = pipeline.run(name_substring=case["company"], max_events=max_events)

    trigger_title = report.decision.get("triggering_event")
    trigger_ts = timestamps.get(trigger_title) if trigger_title else None
    reference_ts = _parse_date(case["reference_date"])
    lead_days = None
    status = "no_alarm"
    if trigger_ts:
        lead_days = (_parse_day(case["reference_date"]) - _parse_day(trigger_ts)).days
        if lead_days > 0:
            status = "early"
        elif lead_days == 0:
            status = "same_day"
        else:
            status = "late"

    return {
        **case,
        "alarm_fired": bool(report.decision.get("alarm_fired")),
        "max_combined_risk": report.decision.get("max_combined_risk"),
        "threshold": report.decision.get("threshold"),
        "triggering_event": trigger_title,
        "trigger_timestamp": trigger_ts,
        "lead_days": lead_days,
        "status": status,
        "events_seen": report.cost.get("events_seen"),
        "events_passed_triage": report.cost.get("events_passed_triage"),
        "cloud_reports_generated": report.cost.get("cloud_reports_generated"),
        "top_contributors": report.topology.get("top_contributors", [])[:3],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrospective pKYC alert lead time.")
    parser.add_argument("--max-events", type=int, default=7)
    parser.add_argument(
        "--output",
        default="data/evaluation_lead_time.json",
        help="JSON artifact path for charts / PowerPoint prep.",
    )
    args = parser.parse_args()

    results = [_evaluate_case(case, args.max_events) for case in REFERENCE_CASES]
    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "max_events": args.max_events,
        "method_note": (
            "Public-reference retrospective benchmark. Positive lead_days means the "
            "engine alarm timestamp precedes the public reference date. This is a "
            "demo metric over the current Google News / OSINT snapshot, not a "
            "regulatory-grade historical backtest."
        ),
        "cases": results,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
