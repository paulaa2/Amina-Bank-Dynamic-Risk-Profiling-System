"""Replay evidence-backed as-of scenarios through the pKYC engine.

The scenario JSON only curates dated public facts. Semantic, topology and
behavioural signals are always computed by the same pipeline as ``run_demo``.

Stream events are processed **oldest-first** by ``date`` by default (same rule as
live news ingestion). A scenario may set ``"replay_order": "json"`` to preserve
curated narrative order when dates alone would mis-order causally related hits.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Any

from scripts.collectors.base import adverse_media_score

from .config import DATA_DIR, load_config
from .ingestion import ClientProfileRepository, NewsEvent
from .pipeline import EngineReport, PerpetualKYCPipeline
from .run_demo import _report_to_dict

_SEMANTIC = "semantic"
_TOPOLOGY = "topology"
_BEHAVIOURAL = "behavioral_tx"

SCENARIOS_DIR = DATA_DIR / "scenarios"


def _parse_event_date(value: str) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value)


def _scenario_events_as_news(scenario: dict[str, Any]) -> list[NewsEvent]:
    events: list[NewsEvent] = []
    for event in scenario["events"]:
        text = " ".join(
            str(part or "")
            for part in (event.get("title"), event.get("evidence"), event.get("source"))
        )
        adverse_score, matched_keywords = adverse_media_score(text)
        events.append(
            NewsEvent(
                title=str(event.get("title") or ""),
                summary=str(event.get("evidence") or ""),
                url=str(event.get("url") or ""),
                source=str(event.get("source") or ""),
                published_at=_parse_event_date(str(event.get("date") or "")),
                adverse_score=adverse_score,
                matched_keywords=matched_keywords,
                burn_in=bool(event.get("burn_in", False)),
            )
        )
    return events


def _chronological(events: list[NewsEvent]) -> list[NewsEvent]:
    """Oldest first; matches live ``run_demo`` ordering."""
    return sorted(events, key=lambda event: event.published_at or dt.datetime.max)


def _chronological_scenario_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(events, key=lambda event: str(event.get("date") or ""))


def _order_events(events: list[NewsEvent], replay_order: str) -> list[NewsEvent]:
    if replay_order == "json":
        return list(events)
    return _chronological(events)


def _order_scenario_events(events: list[dict[str, Any]], replay_order: str) -> list[dict[str, Any]]:
    if replay_order == "json":
        return list(events)
    return _chronological_scenario_events(events)


def find_scenario_path(scenario_id: str, scenario_dir: Path | None = None) -> Path:
    """Resolve a scenario JSON path by ``scenario_id`` or filename stem."""
    root = scenario_dir or SCENARIOS_DIR
    for path in sorted(root.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("scenario_id") == scenario_id or path.stem == scenario_id:
            return path
    raise LookupError(f"Unknown scenario '{scenario_id}' under {root}")


def list_replay_scenarios(scenario_dir: Path | None = None) -> list[dict[str, Any]]:
    """Return metadata for every curated replay scenario (for API / dashboard)."""
    root = scenario_dir or SCENARIOS_DIR
    scenarios: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        scenarios.append(
            {
                "scenario_id": str(data.get("scenario_id") or path.stem),
                "client": str(data.get("client") or ""),
                "description": str(data.get("description") or ""),
                "reference_model": str(data.get("reference_model") or ""),
                "event_count": len(data.get("events") or []),
            }
        )
    return scenarios


def run_scenario_engine(path: Path) -> tuple[dict[str, Any], EngineReport]:
    """Execute one scenario through the pKYC pipeline and return raw scenario + report."""
    scenario = json.loads(path.read_text(encoding="utf-8"))
    replay_order = str(scenario.get("replay_order") or "chronological")
    news = _scenario_events_as_news(scenario)
    burn_in = _order_events([event for event in news if event.burn_in], replay_order)
    stream = _order_events([event for event in news if not event.burn_in], replay_order)
    pipeline = PerpetualKYCPipeline(load_config())
    report = pipeline.run(
        name_substring=scenario["client"],
        max_events=len(stream),
        simulate_tx_anomaly=False,
        events_override=stream,
        burn_in_events=burn_in or None,
    )
    return scenario, report


def replay_scenario_for_api(
    scenario_id: str,
    database_url: str | None = None,
) -> dict[str, Any]:
    """Run a curated scenario and return a dashboard-compatible LiveReport payload."""
    path = find_scenario_path(scenario_id)
    scenario, report = run_scenario_engine(path)
    result = _report_to_dict(report)
    replay_order = str(scenario.get("replay_order") or "chronological")
    scenario_events = _order_scenario_events(
        [event for event in scenario["events"] if not event.get("burn_in")],
        replay_order,
    )
    for index, (source_event, output_event) in enumerate(
        zip(scenario_events, result.get("events", [])),
        start=1,
    ):
        output_event["scenario_index"] = index
        output_event["date"] = source_event.get("date")
        output_event["source"] = source_event.get("source")
        output_event["url"] = source_event.get("url")
        output_event["evidence"] = source_event.get("evidence")
    result["scenario"] = {
        "scenario_id": str(scenario.get("scenario_id") or path.stem),
        "description": scenario.get("description"),
        "reference_model": scenario.get("reference_model"),
        "curated_event_count": len(scenario_events),
        "processed_event_count": len(result.get("events", [])),
    }

    config = load_config()
    db_url = database_url or config.database_url
    repo = ClientProfileRepository(db_url)
    client_name = str(scenario["client"])
    matched_id = next(
        (
            row["id"]
            for row in repo.list_companies()
            if client_name.lower() in row["legal_name"].lower()
            or row["legal_name"].lower() in client_name.lower()
        ),
        None,
    )
    if matched_id is not None:
        result["id"] = str(matched_id)
    return result


def replay_scenario(path: Path) -> dict[str, Any]:
    scenario, report = run_scenario_engine(path)
    threshold = float(report.decision["threshold"])
    replay_order = str(scenario.get("replay_order") or "chronological")
    rows: list[dict[str, Any]] = []
    alarm_row: dict[str, Any] | None = None
    scenario_events = _order_scenario_events(
        [event for event in scenario["events"] if not event.get("burn_in")],
        replay_order,
    )
    for index, (event, outcome) in enumerate(zip(scenario_events, report.events), start=1):
        trigger = outcome.combined_risk > threshold
        row = {
            "index": index,
            "date": event["date"],
            "title": outcome.title,
            "source": event["source"],
            "url": event["url"],
            "evidence": event["evidence"],
            "semantic_signal": outcome.semantic_distance,
            "topology_signal": outcome.topology_signal,
            "behavioral_signal": outcome.behavioral_signal,
            "semantic_stat": outcome.stream_statistics.get(_SEMANTIC, 0.0),
            "topology_stat": outcome.stream_statistics.get(_TOPOLOGY, 0.0),
            "behavioral_stat": outcome.stream_statistics.get(_BEHAVIOURAL, 0.0),
            "semantic_ratio": outcome.stream_ratios.get(_SEMANTIC, 0.0),
            "topology_ratio": outcome.stream_ratios.get(_TOPOLOGY, 0.0),
            "behavioral_ratio": outcome.stream_ratios.get(_BEHAVIOURAL, 0.0),
            "combined_risk": outcome.combined_risk,
            "alarms": outcome.alarms,
            "trigger": trigger,
            "triaged_in": outcome.triaged_in,
            "extracted_fact": outcome.extracted_fact,
            "new_graph_nodes": outcome.new_graph_nodes,
        }
        rows.append(row)
        if trigger and alarm_row is None:
            alarm_row = row

    return {
        "scenario_id": scenario["scenario_id"],
        "client": scenario["client"],
        "description": scenario["description"],
        "reference_model": scenario["reference_model"],
        "threshold": threshold,
        "bonferroni_scale": report.streams["bonferroni_scale"],
        "alarm_event_index": alarm_row["index"] if alarm_row else None,
        "alarm_date": alarm_row["date"] if alarm_row else None,
        "alarm_title": alarm_row["title"] if alarm_row else None,
        "events": rows,
        "decision": report.decision,
        "warnings": report.warnings,
    }


def _write_csv(result: dict[str, Any], path: Path) -> None:
    rows = result["events"]
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "index",
        "date",
        "title",
        "semantic_signal",
        "topology_signal",
        "behavioral_signal",
        "semantic_stat",
        "topology_stat",
        "behavioral_stat",
        "semantic_ratio",
        "topology_ratio",
        "behavioral_ratio",
        "combined_risk",
        "trigger",
        "source",
        "url",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})


def _write_all_results(results: list[dict[str, Any]], output_dir: Path) -> tuple[Path, Path]:
    """Persist aggregate scenario summaries and per-event rows."""
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "scenario_replay_summary.csv"
    events_path = output_dir / "scenario_replay_events.csv"
    json_path = output_dir / "scenario_replay_summary.json"

    summary_rows = []
    event_rows = []
    for result in results:
        events = result["events"]
        alarm_idx = result["alarm_event_index"]
        pre_alarm = [row for row in events if alarm_idx is None or row["index"] < alarm_idx]
        summary_rows.append(
            {
                "scenario_id": result["scenario_id"],
                "client": result["client"],
                "alarm_event_index": alarm_idx,
                "alarm_date": result["alarm_date"],
                "alarm_title": result["alarm_title"],
                "events_total": len(events),
                "pre_alarm_events": len(pre_alarm),
                "risk_before_alarm": round(pre_alarm[-1]["combined_risk"], 4) if pre_alarm else 0.0,
                "alarm_risk": round(events[alarm_idx - 1]["combined_risk"], 4) if alarm_idx else None,
                "description": result["description"],
            }
        )
        for row in events:
            event_rows.append(
                {
                    "scenario_id": result["scenario_id"],
                    "client": result["client"],
                    **{
                        key: row.get(key)
                        for key in [
                            "index",
                            "date",
                            "title",
                            "semantic_signal",
                            "topology_signal",
                            "behavioral_signal",
                            "semantic_ratio",
                            "topology_ratio",
                            "behavioral_ratio",
                            "combined_risk",
                            "trigger",
                            "source",
                            "url",
                        ]
                    },
                }
            )

    with summary_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)
    with events_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(event_rows[0].keys()))
        writer.writeheader()
        writer.writerows(event_rows)
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary_path, events_path


def _graph_mutation_summary(result: dict[str, Any]) -> str:
    """Compact graph-mutation line for CLI summaries."""
    seen: set[str] = set()
    labels: list[str] = []
    for row in result.get("events", []):
        for node in row.get("new_graph_nodes") or []:
            name = str(node.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            tag = "new" if node.get("is_new", True) else "link"
            labels.append(f"{name} ({tag})")
    if not labels:
        return "graph: no new nodes"
    return "graph: " + ", ".join(labels)


def _print_human(result: dict[str, Any]) -> None:
    print(f"SCENARIO: {result['scenario_id']} — {result['client']}")
    print(result["description"])
    print(f"Threshold={result['threshold']} | Bonferroni scale={result['bonferroni_scale']:.3f}")
    print()
    print("idx | date       | semantic | topology | tx     | combined | stream alarms              | trigger | title")
    print("-" * 138)
    for row in result["events"]:
        alarms = ",".join(
            name for name, fired in row["alarms"].items() if fired
        ) or "none"
        print(
            f"{row['index']:>3} | {row['date']} | "
            f"{row['semantic_signal']:.3f}    | {row['topology_signal']:.3f}    | "
            f"{row['behavioral_signal']:.3f}  | {row['combined_risk']:.4f}   | "
            f"{alarms:<25} | {str(row['trigger']).upper():<7} | {row['title'][:50]}"
        )
    if result["alarm_event_index"]:
        print()
        print(
            f"ALARM: event {result['alarm_event_index']} on {result['alarm_date']} "
            f"({result['alarm_title']})"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay an evidence-backed drift scenario.")
    parser.add_argument(
        "--scenario",
        default=(DATA_DIR / "scenarios" / "microstrategy_drift.json").as_posix(),
        help="Path to scenario JSON.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON result.")
    parser.add_argument(
        "--output-json",
        default=(DATA_DIR / "scenario_microstrategy_result.json").as_posix(),
    )
    parser.add_argument(
        "--output-csv",
        default=(DATA_DIR / "scenario_microstrategy_result.csv").as_posix(),
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Replay every scenario JSON under data/scenarios and write aggregate outputs.",
    )
    parser.add_argument(
        "--scenario-dir",
        default=(DATA_DIR / "scenarios").as_posix(),
        help="Directory used by --all.",
    )
    parser.add_argument(
        "--output-dir",
        default=DATA_DIR.as_posix(),
        help="Directory for --all aggregate outputs.",
    )
    parser.add_argument(
        "--push-to-api",
        action="store_true",
        help=(
            "After --all, POST each result to the running API so the dashboard "
            "shows graph mutations automatically. Default API URL: http://localhost:8000"
        ),
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the running API (used with --push-to-api).",
    )
    args = parser.parse_args()

    if args.all:
        scenario_paths = sorted(Path(args.scenario_dir).glob("*.json"))
        results = [replay_scenario(path) for path in scenario_paths]
        summary_path, events_path = _write_all_results(results, Path(args.output_dir))
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
            return
        print(f"Replayed {len(results)} scenarios.")
        print(f"Wrote {summary_path} and {events_path}")
        print()
        for result in results:
            if result["alarm_event_index"]:
                alarm_risk = result["events"][result["alarm_event_index"] - 1]["combined_risk"]
                print(
                    f"- {result['client']}: alarm_event={result['alarm_event_index']} "
                    f"date={result['alarm_date']} risk={alarm_risk:.4f} | "
                    f"{_graph_mutation_summary(result)}"
                )
            else:
                print(
                    f"- {result['client']}: no alarm | {_graph_mutation_summary(result)}"
                )
        print()
        print(f"Full graph details: {Path(args.output_dir) / 'scenario_replay_summary.json'}")

        if args.push_to_api:
            import urllib.request
            import urllib.error
            api = args.api_url.rstrip("/")
            print()
            pushed = 0
            for result in results:
                sid = result.get("scenario_id")
                if not sid:
                    continue
                url = f"{api}/api/scenario-replay/{sid}?force_refresh=true"
                req = urllib.request.Request(url, method="POST")
                try:
                    with urllib.request.urlopen(req, timeout=300) as resp:
                        data = json.loads(resp.read())
                        company = data.get("client", {}).get("legal_name", sid)
                        nodes = sum(len(e.get("new_graph_nodes") or []) for e in data.get("events", []))
                        print(f"  ✓ {company} → cached in API ({nodes} graph nodes)")
                        pushed += 1
                except urllib.error.URLError as exc:
                    print(f"  ✗ {sid}: could not reach API ({exc}) — is `python -m src.api` running?")
            if pushed:
                print(f"\nDashboard ready: open http://localhost:3000 and click any client → 'Curated replay'")
        return

    result = replay_scenario(Path(args.scenario))
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(result, Path(args.output_csv))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        _print_human(result)
        print(f"\nWrote {output_json} and {args.output_csv}")


if __name__ == "__main__":
    main()
