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
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


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
        event["extracted_fact"] = source.get("extracted_fact") or event.get("extracted_fact")
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
    live["scenario"] = scenario_meta
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
    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))

    if pin_scores and not refresh:
        scenario_cache = _apply_summary_merge(scenario_cache, summary_payload)
        print("Pinned validated scores/alarms from scenario_replay_summary.json")

    analysis_cache = _analysis_from_scenario_cache(scenario_cache)

    _write_json(DATA_API_CACHE / "scenario.json", scenario_cache)
    _write_json(DATA_API_CACHE / "analysis.json", analysis_cache)
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
