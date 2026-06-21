"""Export curated scenario replays for the Next.js dashboard static cache.

Writes:
  - data/api_cache/scenario.json          (scenario_id -> LiveReport)
  - data/api_cache/analysis.json          (company_id -> LiveReport)
  - data/scenario_replay_summary.json     (notebook / metrics source)
  - data/scenario_replay_summary.csv
  - data/scenario_replay_events.csv
  - dashboard/public/api_cache/scenario.json
  - dashboard/public/api_cache/analysis.json
  - dashboard/public/api_cache/scenario_replay_summary.json

Run from project root with the virtualenv active:

    python scripts/export_dashboard_cache.py
    python scripts/export_dashboard_cache.py --refresh   # re-run all 7 scenarios (~2 min)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import DATA_DIR
from src.run_scenario_demo import (
    SCENARIOS_DIR,
    _write_all_results,
    replay_scenario,
    replay_scenario_for_api,
)

DATA_API_CACHE = DATA_DIR / "api_cache"
DASHBOARD_CACHE = ROOT / "dashboard" / "public" / "api_cache"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_existing_scenario_cache() -> dict[str, dict]:
    path = DATA_API_CACHE / "scenario.json"
    dashboard_path = DASHBOARD_CACHE / "scenario.json"
    candidates = [path, dashboard_path]
    caches: list[dict[str, dict]] = []
    for candidate in candidates:
        if candidate.exists():
            cache = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(cache, dict) and cache:
                caches.append(cache)
    if not caches:
        return {}
    return max(caches, key=len)


def _analysis_from_scenario_cache(scenario_cache: dict[str, dict]) -> dict[str, dict]:
    analysis: dict[str, dict] = {}
    for report in scenario_cache.values():
        company_id = report.get("id")
        if company_id is not None:
            analysis[str(company_id)] = report
    return analysis


def _merge_summary_into_live_report(live: dict, summary: dict) -> dict:
    """Pin validated replay scores/alarms from summary onto a computed LiveReport."""
    summary_events = sorted(summary.get("events", []), key=lambda event: int(event["index"]))
    if not summary_events:
        return live

    live_by_index = {
        int(event.get("scenario_index") or index): event
        for index, event in enumerate(live.get("events", []), start=1)
    }

    merged_events: list[dict] = []
    for source in summary_events:
        idx = int(source["index"])
        live_event = live_by_index.get(idx, {})

        event = dict(live_event)
        event["title"] = source.get("title") or event.get("title")
        event["date"] = source.get("date") or event.get("date")
        event["source"] = source.get("source") or event.get("source")
        event["url"] = source.get("url") or event.get("url")
        event["evidence"] = source.get("evidence") or event.get("evidence")
        event["semantic_distance"] = source.get("semantic_signal", event.get("semantic_distance"))
        event["topology_signal"] = source.get("topology_signal", event.get("topology_signal"))
        event["behavioral_signal"] = source.get("behavioral_signal", event.get("behavioral_signal"))
        event["combined_risk"] = source.get("combined_risk", event.get("combined_risk"))
        event["triaged_in"] = source.get("triaged_in", event.get("triaged_in", True))
        event["extracted_fact"] = (
            source.get("evidence")
            or source.get("extracted_fact")
            or event.get("extracted_fact")
            or event.get("title")
        )
        event["scenario_index"] = idx
        if source.get("new_graph_nodes") is not None:
            event["new_graph_nodes"] = source.get("new_graph_nodes")
        elif "new_graph_nodes" not in event:
            event["new_graph_nodes"] = []
        event["stream_statistics"] = {
            "semantic": source.get("semantic_stat", 0.0),
            "topology": source.get("topology_stat", 0.0),
            "behavioral_tx": source.get("behavioral_stat", 0.0),
        }
        event["stream_ratios"] = {
            "semantic": source.get("semantic_ratio", 0.0),
            "topology": source.get("topology_ratio", 0.0),
            "behavioral_tx": source.get("behavioral_ratio", 0.0),
        }
        event["alarms"] = source.get("alarms") or event.get("alarms") or {
            "semantic": False,
            "topology": False,
            "behavioral_tx": False,
        }
        if "masked_title" not in event:
            event["masked_title"] = event.get("title") or source.get("title") or ""
        merged_events.append(event)

    live["events"] = merged_events

    threshold = float(summary.get("threshold") or live.get("decision", {}).get("threshold") or 0.5)
    max_risk = float(summary.get("decision", {}).get("max_combined_risk") or 0.0)
    if not max_risk and merged_events:
        max_risk = max(float(event.get("combined_risk") or 0.0) for event in merged_events)

    alarm_index = summary.get("alarm_event_index")
    alarm_fired = alarm_index is not None or max_risk > threshold
    triggering_event = summary.get("decision", {}).get("triggering_event")
    if not triggering_event and alarm_index and merged_events:
        triggering_event = merged_events[int(alarm_index) - 1].get("title")

    live["decision"] = {
        **(live.get("decision") or {}),
        "alarm_fired": alarm_fired,
        "max_combined_risk": round(max_risk, 4),
        "threshold": threshold,
        "triggering_event": triggering_event,
    }

    scenario_meta = live.get("scenario") or {}
    scenario_meta["description"] = summary.get("description") or scenario_meta.get("description")
    scenario_meta["reference_model"] = summary.get("reference_model") or scenario_meta.get("reference_model")
    scenario_meta["curated_event_count"] = len(summary.get("events") or [])
    scenario_meta["processed_event_count"] = len(merged_events)
    scenario_meta["alarm_event_index"] = summary.get("alarm_event_index")
    scenario_meta["alarm_date"] = summary.get("alarm_date")
    scenario_meta["alarm_title"] = summary.get("alarm_title")
    live["scenario"] = scenario_meta
    return live


def _scenario_timestamp(live: dict) -> str:
    scenario = live.get("scenario") or {}
    alarm_index = scenario.get("alarm_event_index")
    events = live.get("events") or []
    event = None
    if alarm_index:
        event = next((e for e in events if int(e.get("scenario_index") or 0) == int(alarm_index)), None)
    if event is None and events:
        event = max(events, key=lambda e: float(e.get("combined_risk") or 0.0))
    date = (event or {}).get("date") or "2026-06-21"
    return f"{date}T09:00:00+00:00"


def _build_static_report_markdown(live: dict) -> str:
    client = live.get("client") or {}
    decision = live.get("decision") or {}
    events = live.get("events") or []
    peak = max(events, key=lambda e: float(e.get("combined_risk") or 0.0)) if events else {}
    streams = peak.get("alarms") or {}
    stream_summary = ", ".join(
        f"{name.replace('_', ' ')}={'active' if active else 'inactive'}"
        for name, active in streams.items()
    ) or "No individual stream exceeded its standalone alarm threshold"
    report_id = f"ALT_{int(live.get('id') or 0):03d}" if live.get("id") else "ALT_SCENARIO"
    risk = float(decision.get("max_combined_risk") or peak.get("combined_risk") or 0.0)
    trigger_title = decision.get("triggering_event") or peak.get("title") or "Curated replay trigger"
    fact = peak.get("extracted_fact") or peak.get("evidence") or trigger_title
    semantic = peak.get("semantic_distance", 0.0)
    topology = peak.get("topology_signal", live.get("topology", {}).get("company_exposure", 0.0))
    behavioral = peak.get("behavioral_signal", 0.0)
    source = peak.get("source") or "Curated scenario evidence"
    url = peak.get("url") or "N/A"
    return (
        f"# AML COMPLIANCE REPORT - ALERT RECORD {report_id}\n\n"
        "## 1. EXECUTIVE SUMMARY\n"
        f"{client.get('legal_name', 'The client')} breached the configured KYC drift threshold "
        f"during the curated historical replay. The maximum combined risk reached {risk:.2f} "
        f"against a threshold of {float(decision.get('threshold') or 0.5):.2f}.\n\n"
        "## 2. TRIGGERING EVIDENCE\n"
        f"- Triggering event: {trigger_title}\n"
        f"- Extracted fact: {fact}\n"
        f"- Source: {source}\n"
        f"- URL: {url}\n\n"
        "## 3. MULTI-STREAM KYC DRIFT ANALYSIS\n"
        f"- Semantic signal: {semantic}\n"
        f"- Topology exposure: {topology}\n"
        f"- Behavioural transaction signal: {behavioral}\n"
        f"- Alarm stream status: {stream_summary}\n\n"
        "## 4. AUDITABLE METRIC TRACE\n"
        f"- Combined risk: {risk:.4f}\n"
        f"- Threshold: {float(decision.get('threshold') or 0.5):.4f}\n"
        f"- Processed replay events: {len(events)}\n\n"
        "## 5. RECOMMENDED GOVERNANCE ACTION\n"
        "Open an enhanced due-diligence review, preserve source evidence, and require "
        "four-eyes approval before any mitigation action is executed."
    )


def _ensure_governance_and_report(live: dict) -> dict:
    decision = live.get("decision") or {}
    alarm_fired = bool(decision.get("alarm_fired"))
    if not alarm_fired:
        live["governance"] = None
        live["report_markdown"] = None
        return live

    client = live.get("client") or {}
    report_id = f"ALT_{int(live.get('id') or 0):03d}" if live.get("id") else "ALT_SCENARIO"
    events = live.get("events") or []
    peak = max(events, key=lambda e: float(e.get("combined_risk") or 0.0)) if events else {}
    trigger_streams = [name for name, active in (peak.get("alarms") or {}).items() if active]
    risk = float(decision.get("max_combined_risk") or peak.get("combined_risk") or 0.0)
    timestamp = _scenario_timestamp(live)

    live["governance"] = {
        "alert_id": report_id,
        "target_entity_id": f"COMPANY_{live.get('id') or 'SCENARIO'}",
        "target_display_name": client.get("legal_name", "Curated scenario client"),
        "risk_score": round(risk, 4),
        "trigger_streams": trigger_streams,
        "status": "DETECTED",
        "assigned_analyst": None,
        "proposed_mitigation_action": None,
        "compliance_approver": None,
        "audit_trail": [
            {
                "timestamp": timestamp,
                "user": "system",
                "action": "Alert detected by curated replay drift fusion gateway",
                "resulting_status": "DETECTED",
            }
        ],
    }

    report_text = str(live.get("report_markdown") or "")
    spanish_residue = any(
        token in report_text.lower()
        for token in (
            " rechaza ",
            " requiere ",
            " emitió ",
            " fue ordenada ",
            " presenta su quiebra ",
            " auditoría ",
            " inversores",
            "{'semantic'",
        )
    )
    if not report_text or spanish_residue:
        live["report_markdown"] = _build_static_report_markdown(live)

    return live


def _apply_summary_merge(
    scenario_cache: dict[str, dict], summary_payload: list[dict]
) -> dict[str, dict]:
    summary_by_id = {entry["scenario_id"]: entry for entry in summary_payload}
    for scenario_id, live in scenario_cache.items():
        summary = summary_by_id.get(scenario_id)
        if summary is not None:
            _merge_summary_into_live_report(live, summary)
    return scenario_cache


def _sanitise_summary_payload(summary_payload: list[dict]) -> list[dict]:
    clean_payload: list[dict] = []
    for entry in summary_payload:
        clean_entry = dict(entry)
        clean_events = []
        for event in entry.get("events", []):
            clean_event = dict(event)
            clean_event["extracted_fact"] = (
                clean_event.get("evidence")
                or clean_event.get("extracted_fact")
                or clean_event.get("title")
            )
            clean_events.append(clean_event)
        clean_entry["events"] = clean_events
        clean_payload.append(clean_entry)
    return clean_payload


def export_dashboard_cache(
    *,
    refresh: bool = False,
    live_reports_only: bool = False,
    pin_scores: bool = True,
) -> None:
    scenario_paths = sorted(SCENARIOS_DIR.glob("*.json"))
    if not scenario_paths:
        raise SystemExit(f"No scenario JSON files found under {SCENARIOS_DIR}")

    if refresh:
        scenario_cache: dict[str, dict] = {}
        summary_results = []
        for path in scenario_paths:
            scenario_id = json.loads(path.read_text(encoding="utf-8")).get("scenario_id", path.stem)
            print(f"Replaying {scenario_id} …")
            api_report = replay_scenario_for_api(str(scenario_id))
            cli_result = replay_scenario(path)
            scenario_cache[str(scenario_id)] = api_report
            summary_results.append(cli_result)
        _write_all_results(summary_results, DATA_DIR)
    elif live_reports_only:
        scenario_cache = {}
        for path in scenario_paths:
            scenario_id = json.loads(path.read_text(encoding="utf-8")).get("scenario_id", path.stem)
            print(f"Building LiveReport for {scenario_id} …")
            scenario_cache[str(scenario_id)] = replay_scenario_for_api(str(scenario_id))
    else:
        scenario_cache = _load_existing_scenario_cache()
        missing = [
            json.loads(path.read_text(encoding="utf-8")).get("scenario_id", path.stem)
            for path in scenario_paths
            if json.loads(path.read_text(encoding="utf-8")).get("scenario_id", path.stem)
            not in scenario_cache
            and path.stem not in scenario_cache
        ]
        if missing:
            raise SystemExit(
                "Missing scenario cache entries: "
                f"{missing}. Re-run with --refresh to regenerate all LiveReports."
            )

    summary_path = DATA_DIR / "scenario_replay_summary.json"
    if not summary_path.exists():
        raise SystemExit(
            f"{summary_path} not found. Run with --refresh to generate summary outputs."
        )
    summary_payload = _sanitise_summary_payload(
        json.loads(summary_path.read_text(encoding="utf-8"))
    )

    if pin_scores and not refresh:
        scenario_cache = _apply_summary_merge(scenario_cache, summary_payload)
        print("Pinned validated scores/alarms from scenario_replay_summary.json")

    for report in scenario_cache.values():
        _ensure_governance_and_report(report)

    analysis_cache = _analysis_from_scenario_cache(scenario_cache)

    _write_json(DATA_API_CACHE / "scenario.json", scenario_cache)
    _write_json(DATA_API_CACHE / "analysis.json", analysis_cache)
    _write_json(DATA_DIR / "scenario_replay_summary.json", summary_payload)
    _write_json(DASHBOARD_CACHE / "scenario.json", scenario_cache)
    _write_json(DASHBOARD_CACHE / "analysis.json", analysis_cache)
    _write_json(DASHBOARD_CACHE / "scenario_replay_summary.json", summary_payload)

    print(f"Exported {len(scenario_cache)} scenario LiveReports.")
    print(f"Exported {len(analysis_cache)} company analysis entries.")
    print(f"Wrote dashboard cache under {DASHBOARD_CACHE}")
    for report in scenario_cache.values():
        scenario_id = report.get("scenario", {}).get("scenario_id", "?")
        client = report.get("client", {}).get("legal_name", "?")
        alarm = report.get("decision", {}).get("alarm_fired")
        events = len(report.get("events", []))
        print(f"  - {client} ({scenario_id}): {events} events, alarm={alarm}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export dashboard static API caches.")
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-run all 7 curated scenarios through the engine before exporting.",
    )
    parser.add_argument(
        "--live-reports-only",
        action="store_true",
        help="Rebuild LiveReports only (keep existing scenario_replay_summary.json).",
    )
    parser.add_argument(
        "--no-pin-scores",
        action="store_true",
        help="Do not pin scores/alarms from scenario_replay_summary.json onto LiveReports.",
    )
    args = parser.parse_args()
    export_dashboard_cache(
        refresh=args.refresh,
        live_reports_only=args.live_reports_only,
        pin_scores=not args.no_pin_scores,
    )


if __name__ == "__main__":
    main()
