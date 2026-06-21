"""Discrete-event global demo for cross-client pKYC contagion.

Runs multiple ego-centric client pipelines in one process and one thread, using
a chronological event queue and shared in-memory threat intelligence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass, field
from typing import Any

from .config import load_config
from .cost import CostTracker
from .detectors import (
    DriftFusion,
    PageHinkleyDetector,
    QuantitativeTransactionStream,
    StreamSignal,
)
from .entities import EntityResolver
from .ingestion import ClientProfile, NewsEvent
from .pipeline import EngineReport, EventOutcome, PerpetualKYCPipeline
from .security import DataAnonymizer
from .triage import RelevanceTriage

_SEMANTIC = "semantic"
_TOPOLOGY = "topology"
_BEHAVIOURAL = "behavioral_tx"


@dataclass(frozen=True)
class QueuedEvent:
    """A Layer-1 event tagged with its owning client pipeline."""

    timestamp: dt.datetime
    target_company: str
    event: NewsEvent


@dataclass
class ClientRuntime:
    """Mutable state for one ego-centric client pipeline."""

    name: str
    pipeline: PerpetualKYCPipeline
    profile: ClientProfile
    anonymizer: DataAnonymizer
    resolver: EntityResolver
    graph: Any
    triage: RelevanceTriage
    local_ok: bool
    profile_text: str
    m0: list[float] | None
    fusion: DriftFusion
    sem_det: PageHinkleyDetector
    topo_det: PageHinkleyDetector
    tx_det: PageHinkleyDetector
    tx_stream: QuantitativeTransactionStream
    tx_amounts: list[float]
    warnings: list[str] = field(default_factory=list)
    outcomes: list[EventOutcome] = field(default_factory=list)
    frozen: bool = False
    max_risk: float = 0.0
    peak_outcome: EventOutcome | None = None
    report_markdown: str | None = None
    governance: dict | None = None
    company_exposure: float = 0.0
    contributors: list[dict[str, Any]] = field(default_factory=list)
    has_cycle: bool = False
    processed_events: int = 0


def _utc_timestamp(event: NewsEvent) -> dt.datetime:
    timestamp = event.published_at or dt.datetime.now(dt.timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
    return timestamp.astimezone(dt.timezone.utc)


def _node_real_name(node_id: str, node_data: dict[str, Any], anonymizer: DataAnonymizer) -> str:
    label = str(node_data.get("label") or "").strip()
    if label:
        return anonymizer.unmask_text(label).strip()
    return anonymizer.unmask_text(node_id).strip()


def _build_runtime(
    company: str,
    max_events_per_client: int,
    simulate_tx_anomaly: bool,
) -> tuple[ClientRuntime, list[QueuedEvent]]:
    pipeline = PerpetualKYCPipeline(load_config())
    pipeline.cost = CostTracker(
        groq_input_usd_per_mtok=pipeline.config.groq_input_usd_per_mtok,
        groq_output_usd_per_mtok=pipeline.config.groq_output_usd_per_mtok,
    )
    warnings: list[str] = []
    local_ok = pipeline.ollama.available()
    if not local_ok:
        warnings.append("Ollama is not reachable; semantic stage runs in lexical-fallback mode.")

    profile = pipeline.repository.load_profile(name_substring=company)
    news = pipeline._chronological_events(
        pipeline.repository.load_news(profile.id, limit=max(max_events_per_client * 3, 30))
    )[:max_events_per_client]

    anonymizer = DataAnonymizer()
    anonymizer.register_sensitive_entity(profile.legal_name, "COMPANY")
    for node in profile.nodes:
        anonymizer.register_sensitive_entity(node.name, node.node_type)

    registry = pipeline._build_registry(profile)
    graph = pipeline._build_graph(profile)
    profile_text = profile.profile_text()
    m0, sem_baseline = pipeline._initialise_semantic_baseline(profile, local_ok, warnings)

    sem_det = PageHinkleyDetector()
    sem_det.seed(
        sem_baseline,
        k_std_delta=pipeline.config.ph_semantic_delta_std,
        k_std_threshold=pipeline.config.ph_semantic_threshold_std,
    )
    initial_exposure = graph.exposure_of(
        profile.company_node_id, beta=pipeline.config.contagion_beta
    )
    topo_det = PageHinkleyDetector()
    topo_det.seed(pipeline._topo_baseline(initial_exposure))

    tx_stream = QuantitativeTransactionStream()
    tx_amounts, tx_baseline_z = pipeline._simulate_transactions(
        profile, inject_anomaly=simulate_tx_anomaly
    )
    tx_det = PageHinkleyDetector()
    tx_det.seed(tx_baseline_z if len(tx_baseline_z) >= 3 else [0.1, 0.2, 0.15, 0.25, 0.2])

    fusion = DriftFusion(
        [
            StreamSignal(_SEMANTIC, sem_det, weight=1.0),
            StreamSignal(_TOPOLOGY, topo_det, weight=0.8),
            StreamSignal(_BEHAVIOURAL, tx_det, weight=0.9),
        ],
        target_fwer=pipeline.config.target_fwer,
    )

    runtime = ClientRuntime(
        name=company,
        pipeline=pipeline,
        profile=profile,
        anonymizer=anonymizer,
        resolver=EntityResolver(registry),
        graph=graph,
        triage=RelevanceTriage(profile.all_aliases()),
        local_ok=local_ok,
        profile_text=profile_text,
        m0=m0,
        fusion=fusion,
        sem_det=sem_det,
        topo_det=topo_det,
        tx_det=tx_det,
        tx_stream=tx_stream,
        tx_amounts=tx_amounts,
        warnings=warnings,
    )
    runtime.company_exposure = graph.exposure_of(
        profile.company_node_id, beta=pipeline.config.contagion_beta
    )
    runtime.contributors = graph.top_risk_contributors(
        profile.company_node_id, beta=pipeline.config.contagion_beta
    )
    runtime.has_cycle = graph.check_ownership_cycles(profile.company_node_id)

    queued_events = [
        QueuedEvent(_utc_timestamp(event), company, event)
        for event in news
    ]
    return runtime, queued_events


def _pull_shared_threats(
    runtime: ClientRuntime,
    shared_threat_memory: dict[str, float],
) -> list[dict[str, Any]]:
    inherited: list[dict[str, Any]] = []
    for node_id, node_data in runtime.graph.graph.nodes(data=True):
        real_name = _node_real_name(str(node_id), node_data, runtime.anonymizer)
        if real_name not in shared_threat_memory:
            continue
        global_risk = float(shared_threat_memory[real_name])
        local_risk = float(node_data.get("intrinsic_risk", 0.0) or 0.0)
        if global_risk <= local_risk:
            continue
        runtime.graph.set_intrinsic_risk(str(node_id), global_risk)
        inherited.append(
            {
                "entity_name": real_name,
                "node_id": str(node_id),
                "previous_risk": local_risk,
                "max_risk": global_risk,
            }
        )
    return inherited


def _push_shared_threats(
    runtime: ClientRuntime,
    shared_threat_memory: dict[str, float],
) -> list[dict[str, Any]]:
    published: list[dict[str, Any]] = []
    for node_id, node_data in runtime.graph.graph.nodes(data=True):
        risk = float(node_data.get("intrinsic_risk", 0.0) or 0.0)
        if risk <= 0.5:
            continue
        real_name = _node_real_name(str(node_id), node_data, runtime.anonymizer)
        if not real_name:
            continue
        previous = float(shared_threat_memory.get(real_name, 0.0))
        if risk <= previous:
            continue
        shared_threat_memory[real_name] = risk
        published.append({"entity_name": real_name, "max_risk": risk})
    return published


def _refresh_topology(runtime: ClientRuntime) -> None:
    runtime.company_exposure = runtime.graph.exposure_of(
        runtime.profile.company_node_id, beta=runtime.pipeline.config.contagion_beta
    )
    runtime.contributors = runtime.graph.top_risk_contributors(
        runtime.profile.company_node_id, beta=runtime.pipeline.config.contagion_beta
    )
    runtime.has_cycle = runtime.graph.check_ownership_cycles(runtime.profile.company_node_id)


def _process_event(
    runtime: ClientRuntime,
    event: NewsEvent,
    shared_threat_memory: dict[str, float],
    global_index: int,
    total_events: int,
) -> None:
    runtime.pipeline.cost.events_seen += 1
    runtime.processed_events += 1

    inherited = _pull_shared_threats(runtime, shared_threat_memory)
    if inherited:
        for item in inherited:
            print(
                "[GLOBAL ORCHESTRATOR] Cross-client threat inherited "
                f"target={runtime.name} entity={item['entity_name']} "
                f"risk={item['max_risk']:.4f}",
                file=sys.stderr,
                flush=True,
            )
        _refresh_topology(runtime)

    verdict = runtime.triage.is_relevant(f"{event.title} {event.summary}")
    if not verdict.is_relevant:
        outcome = EventOutcome(
            event.title,
            "",
            "",
            0.0,
            0.0,
            {},
            False,
            False,
            topology_signal=round(runtime.company_exposure, 4),
            behavioral_signal=0.0,
        )
        outcome.date = _utc_timestamp(event).isoformat()
        outcome.source = event.source
        outcome.url = event.url
        outcome.evidence = event.summary
        runtime.outcomes.append(outcome)
        print(
            f"[GLOBAL EVENT {global_index}/{total_events}] target={runtime.name} "
            f"timestamp={_utc_timestamp(event).isoformat()} skipped_by_triage title={event.title[:120]}",
            file=sys.stderr,
            flush=True,
        )
        return

    runtime.pipeline.cost.events_passed_triage += 1
    masked_title = runtime.anonymizer.mask_text(event.title)
    fact_text, used_fallback, entities = runtime.pipeline._extract_fact(masked_title, runtime.local_ok)
    new_nodes = runtime.pipeline._resolve_and_update_graph(
        entities=entities,
        resolver=runtime.resolver,
        registry=runtime.resolver.registry,
        graph=runtime.graph,
        anonymizer=runtime.anonymizer,
        company_node_id=runtime.profile.company_node_id,
        adverse_score=event.adverse_score,
        event_text=f"{event.title} {event.summary} {fact_text}",
    )
    _refresh_topology(runtime)

    sem_distance = runtime.pipeline._semantic_distance(
        profile_text=runtime.profile_text,
        m0=runtime.m0,
        embed_text=fact_text,
        event=event,
        local_ok=runtime.local_ok,
    )
    tx_amount = runtime.tx_amounts[
        (runtime.processed_events - 1) % len(runtime.tx_amounts)
    ] if runtime.tx_amounts else 0.0
    tx_z = runtime.tx_stream.record_transaction(tx_amount)
    result = runtime.fusion.update(
        {
            _SEMANTIC: sem_distance,
            _TOPOLOGY: runtime.company_exposure,
            _BEHAVIOURAL: tx_z,
        }
    )

    outcome = EventOutcome(
        title=event.title,
        masked_title=masked_title,
        extracted_fact=fact_text,
        semantic_distance=round(sem_distance, 4),
        combined_risk=round(result.combined_risk, 4),
        alarms=result.alarms,
        triaged_in=True,
        used_fallback=used_fallback,
        topology_signal=round(runtime.company_exposure, 4),
        behavioral_signal=round(tx_z, 4),
        stream_statistics=result.statistics,
        stream_ratios=result.ratios,
        new_graph_nodes=new_nodes,
    )
    outcome.date = _utc_timestamp(event).isoformat()
    outcome.source = event.source
    outcome.url = event.url
    outcome.evidence = event.summary
    runtime.outcomes.append(outcome)
    if result.combined_risk > runtime.max_risk:
        runtime.max_risk = result.combined_risk
        runtime.peak_outcome = outcome

    for item in _push_shared_threats(runtime, shared_threat_memory):
        print(
            "[GLOBAL ORCHESTRATOR] Shared threat published "
            f"source={runtime.name} entity={item['entity_name']} risk={item['max_risk']:.4f}",
            file=sys.stderr,
            flush=True,
        )

    trigger_fired = result.combined_risk > runtime.pipeline.config.combined_risk_threshold
    print(
        f"[GLOBAL EVENT {global_index}/{total_events}] target={runtime.name} "
        f"timestamp={_utc_timestamp(event).isoformat()} "
        f"risk={result.combined_risk:.4f} semantic={sem_distance:.4f} "
        f"topology={runtime.company_exposure:.4f} trigger={str(trigger_fired).upper()} "
        f"title={event.title[:120]}",
        file=sys.stderr,
        flush=True,
    )

    if trigger_fired:
        runtime.frozen = True
        trace = runtime.pipeline._build_anomaly_trace(
            runtime.profile,
            outcome,
            runtime.company_exposure,
            runtime.contributors,
            runtime.has_cycle,
            runtime.max_risk,
        )
        runtime.report_markdown = runtime.pipeline._draft_report(trace, runtime.warnings)
        runtime.governance = runtime.pipeline._run_governance(
            runtime.profile, outcome, runtime.max_risk
        ).as_dict()
        print(
            f"[GLOBAL ORCHESTRATOR] Early stop target={runtime.name} "
            f"risk={result.combined_risk:.4f}; future events for this client skipped.",
            file=sys.stderr,
            flush=True,
        )


def _runtime_report(runtime: ClientRuntime) -> EngineReport:
    return EngineReport(
        client=runtime.pipeline._client_summary(runtime.profile),
        security={
            "masked_entities": runtime.anonymizer.registered_count,
            "company_token": runtime.anonymizer.token_for(runtime.profile.legal_name),
            "note": "Global demo keeps each client ego graph isolated.",
        },
        topology={
            "company_exposure": round(runtime.company_exposure, 4),
            "circular_ownership_detected": runtime.has_cycle,
            "top_contributors": [
                {
                    "name": c["label"],
                    "type": c["type"],
                    "relation": c["rel_type"],
                    "intrinsic_risk": round(c["intrinsic_risk"], 3),
                    "contributed": round(c["contributed"], 3),
                }
                for c in runtime.contributors[:5]
            ],
        },
        streams=runtime.pipeline._stream_summary(
            runtime.fusion, runtime.sem_det, runtime.topo_det, runtime.tx_det, runtime.company_exposure
        ),
        decision={
            "alarm_fired": runtime.frozen,
            "max_combined_risk": round(runtime.max_risk, 4),
            "threshold": runtime.pipeline.config.combined_risk_threshold,
            "triggering_event": runtime.peak_outcome.title if runtime.peak_outcome else None,
        },
        cost=runtime.pipeline.cost.summary(),
        events=runtime.outcomes,
        governance=runtime.governance,
        report_markdown=runtime.report_markdown,
        warnings=runtime.warnings,
    )


def _report_to_dict(report: EngineReport) -> dict[str, Any]:
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
                "masked_title": e.masked_title,
                "extracted_fact": e.extracted_fact,
                "triaged_in": e.triaged_in,
                "semantic_distance": e.semantic_distance,
                "combined_risk": e.combined_risk,
                "alarms": e.alarms,
                "new_graph_nodes": e.new_graph_nodes,
                "date": getattr(e, "date", None),
                "source": getattr(e, "source", None),
                "url": getattr(e, "url", None),
                "evidence": getattr(e, "evidence", None),
                "topology_signal": e.topology_signal,
                "behavioral_signal": e.behavioral_signal,
                "stream_statistics": e.stream_statistics,
                "stream_ratios": e.stream_ratios,
            }
            for e in report.events
        ],
        "report_markdown": report.report_markdown,
    }


def run_global_demo(
    companies: list[str],
    max_events_per_client: int,
    simulate_tx_anomaly: bool,
) -> dict[str, Any]:
    shared_threat_memory: dict[str, float] = {}
    pipelines: dict[str, ClientRuntime] = {}
    global_event_queue: list[QueuedEvent] = []

    for company in companies:
        runtime, events = _build_runtime(company, max_events_per_client, simulate_tx_anomaly)
        pipelines[company] = runtime
        global_event_queue.extend(events)

    global_event_queue.sort(key=lambda queued: queued.timestamp)
    total_events = len(global_event_queue)

    print(
        f"[GLOBAL ORCHESTRATOR] Loaded {len(pipelines)} client pipelines and "
        f"{total_events} chronological events.",
        file=sys.stderr,
        flush=True,
    )

    for index, queued in enumerate(global_event_queue, start=1):
        runtime = pipelines[queued.target_company]
        if runtime.frozen:
            print(
                f"[GLOBAL EVENT {index}/{total_events}] target={runtime.name} "
                "skipped_client_frozen",
                file=sys.stderr,
                flush=True,
            )
            continue
        _process_event(runtime, queued.event, shared_threat_memory, index, total_events)

    return {
        "shared_threat_memory": shared_threat_memory,
        "clients": {
            company: _report_to_dict(_runtime_report(runtime))
            for company, runtime in pipelines.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Global pKYC discrete-event demo.")
    parser.add_argument(
        "--companies",
        nargs="+",
        default=["VTB", "MicroStrategy"],
        help="Client name substrings to include in the global event queue.",
    )
    parser.add_argument("--max-events", type=int, default=6, help="Events loaded per client.")
    parser.add_argument(
        "--simulate-tx-anomaly",
        action="store_true",
        help="Inject a simulated transaction anomaly in every client runtime.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    args = parser.parse_args()

    result = run_global_demo(args.companies, args.max_events, args.simulate_tx_anomaly)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return

    print("AMINA BANK - GLOBAL pKYC DISCRETE EVENT DEMO")
    print(f"Clients: {', '.join(result['clients'].keys())}")
    print(f"Shared threats discovered: {len(result['shared_threat_memory'])}")
    for name, report in result["clients"].items():
        decision = report["decision"]
        cost = report["cost"]
        print(
            f"- {name}: alarm={decision['alarm_fired']} "
            f"max_risk={decision['max_combined_risk']} "
            f"events={len(report['events'])} "
            f"cloud_cost=${cost['cloud_tokens']['cost_usd']}"
        )


if __name__ == "__main__":
    main()
