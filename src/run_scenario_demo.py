"""Replay curated as-of scenarios through the statistical drift engine.

This runner is intentionally separate from ``run_demo``:

* ``run_demo`` consumes the live SQLite OSINT snapshot and is good for shock
  detection / end-to-end pKYC.
* ``run_scenario_demo`` consumes evidence-backed dated events with calibrated
  stream observations. It is good for demonstrating gradual drift, Page-Hinkley
  memory and DriftFusion without relying on whatever Google News returns today.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from .config import DATA_DIR, load_config
from .detectors import DriftFusion, PageHinkleyDetector, StreamSignal

_SEMANTIC = "semantic"
_TOPOLOGY = "topology"
_BEHAVIOURAL = "behavioral_tx"


def _detector(values: list[float], calibration: dict[str, float]) -> PageHinkleyDetector:
    detector = PageHinkleyDetector()
    detector.seed(
        values,
        k_std_delta=float(calibration.get("k_std_delta", 1.0)),
        k_std_threshold=float(calibration.get("k_std_threshold", 6.0)),
    )
    return detector


def replay_scenario(path: Path) -> dict[str, Any]:
    scenario = json.loads(path.read_text(encoding="utf-8"))
    config = load_config()
    baseline = scenario["baseline"]
    calibration = scenario["detector_calibration"]
    fusion = DriftFusion(
        [
            StreamSignal(
                _SEMANTIC,
                _detector(baseline[_SEMANTIC], calibration[_SEMANTIC]),
                weight=float(calibration[_SEMANTIC].get("weight", 1.0)),
            ),
            StreamSignal(
                _TOPOLOGY,
                _detector(baseline[_TOPOLOGY], calibration[_TOPOLOGY]),
                weight=float(calibration[_TOPOLOGY].get("weight", 0.8)),
            ),
            StreamSignal(
                _BEHAVIOURAL,
                _detector(baseline[_BEHAVIOURAL], calibration[_BEHAVIOURAL]),
                weight=float(calibration[_BEHAVIOURAL].get("weight", 0.9)),
            ),
        ],
        target_fwer=config.target_fwer,
    )

    threshold = float(scenario.get("alarm_threshold", config.combined_risk_threshold))
    rows: list[dict[str, Any]] = []
    alarm_row: dict[str, Any] | None = None

    for index, event in enumerate(scenario["events"], start=1):
        result = fusion.update(
            {
                _SEMANTIC: float(event["semantic_signal"]),
                _TOPOLOGY: float(event["topology_signal"]),
                _BEHAVIOURAL: float(event["behavioral_signal"]),
            }
        )
        trigger = result.combined_risk > threshold
        row = {
            "index": index,
            "date": event["date"],
            "title": event["title"],
            "source": event["source"],
            "url": event["url"],
            "evidence": event["evidence"],
            "semantic_signal": float(event["semantic_signal"]),
            "topology_signal": float(event["topology_signal"]),
            "behavioral_signal": float(event["behavioral_signal"]),
            "semantic_stat": result.statistics.get(_SEMANTIC, 0.0),
            "topology_stat": result.statistics.get(_TOPOLOGY, 0.0),
            "behavioral_stat": result.statistics.get(_BEHAVIOURAL, 0.0),
            "semantic_ratio": result.ratios.get(_SEMANTIC, 0.0),
            "topology_ratio": result.ratios.get(_TOPOLOGY, 0.0),
            "behavioral_ratio": result.ratios.get(_BEHAVIOURAL, 0.0),
            "combined_risk": result.combined_risk,
            "alarms": result.alarms,
            "trigger": trigger,
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
        "bonferroni_scale": fusion.bonferroni_scale,
        "alarm_event_index": alarm_row["index"] if alarm_row else None,
        "alarm_date": alarm_row["date"] if alarm_row else None,
        "alarm_title": alarm_row["title"] if alarm_row else None,
        "events": rows,
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
        default=(DATA_DIR / "scenario_microstrategy_drift_result.json").as_posix(),
    )
    parser.add_argument(
        "--output-csv",
        default=(DATA_DIR / "scenario_microstrategy_drift_result.csv").as_posix(),
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
            print(
                f"- {result['client']}: alarm_event={result['alarm_event_index']} "
                f"date={result['alarm_date']} risk="
                f"{result['events'][result['alarm_event_index'] - 1]['combined_risk']:.4f}"
                if result["alarm_event_index"]
                else f"- {result['client']}: no alarm"
            )
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
