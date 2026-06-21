"""Perpetual KYC (pKYC) pipeline orchestrator.

Wires together the six phases described in the technical specification into a
single, cost-aware, explainable run for one monitored client:

    Phase 1  Masking proxy        register sensitive identities (GDPR)
    Phase 2  Entity resolution    build the closed-list registry / graph
    Phase 3  Statistical + graph  semantic drift, topological contagion, Z-score
    Phase 4  Risk fusion          Bonferroni-corrected multi-stream combination
    Phase 5  Unmasking proxy      de-anonymise the anomaly trace locally
    Phase 6  Governance           four-eyes workflow + auditable AML report

Stages 1-3 are free (local triage, local Ollama extraction/embeddings, pure
Python math). Stage 4 (Groq report) runs only when the fused risk crosses the
configured threshold.
"""

from __future__ import annotations

import datetime as dt
import random
import sys
from dataclasses import dataclass, field

from .config import EngineConfig, load_config
from .cost import CostTracker
from .detectors import (
    DriftFusion,
    PageHinkleyDetector,
    QuantitativeTransactionStream,
    StreamSignal,
    cosine_distance,
)
from .entities import EntityRegistry, EntityResolver
from .governance import AlertStatus, ComplianceAlert, FourEyesWorkflow
from .graph import ComplianceDirectedGraph
from .ingestion import ClientProfile, ClientProfileRepository, NewsEvent
from .llm.agents import AMLSynthesizer, SentinelExtractor
from .llm.groq_client import GroqClient
from .llm.ollama_client import OllamaClient
from .security import DataAnonymizer
from .triage import RelevanceTriage

_SEMANTIC = "semantic"
_TOPOLOGY = "topology"
_BEHAVIOURAL = "behavioral_tx"


@dataclass
class EventOutcome:
    """Per-event record produced during the Stage 1-3 loop."""

    title: str
    masked_title: str
    extracted_fact: str
    semantic_distance: float
    combined_risk: float
    alarms: dict[str, bool]
    triaged_in: bool
    used_fallback: bool
    topology_signal: float = 0.0
    behavioral_signal: float = 0.0
    stream_statistics: dict[str, float] = field(default_factory=dict)
    stream_ratios: dict[str, float] = field(default_factory=dict)
    new_graph_nodes: list[dict[str, object]] = field(default_factory=list)


@dataclass
class EngineReport:
    """Structured result of one engine run (the analyst-facing payload)."""

    client: dict
    security: dict
    topology: dict
    streams: dict
    decision: dict
    cost: dict
    events: list[EventOutcome] = field(default_factory=list)
    governance: dict | None = None
    report_markdown: str | None = None
    warnings: list[str] = field(default_factory=list)


class PerpetualKYCPipeline:
    """End-to-end pKYC drift engine for a single client."""

    def __init__(self, config: EngineConfig | None = None) -> None:
        self.config = config or load_config()
        self.repository = ClientProfileRepository(self.config.database_url)
        self.ollama = OllamaClient(
            host=self.config.ollama_host,
            chat_model=self.config.ollama_extractor_model,
            embedding_model=self.config.ollama_embedding_model,
            timeout=self.config.request_timeout,
        )
        self.sentinel = SentinelExtractor(self.ollama)
        self.cost = CostTracker(
            groq_input_usd_per_mtok=self.config.groq_input_usd_per_mtok,
            groq_output_usd_per_mtok=self.config.groq_output_usd_per_mtok,
        )

    # -- public API --------------------------------------------------------

    def run(
        self,
        name_substring: str | None = None,
        company_id: int | None = None,
        max_events: int | None = None,
        simulate_tx_anomaly: bool | None = None,
        events_override: list[NewsEvent] | None = None,
        burn_in_events: list[NewsEvent] | None = None,
    ) -> EngineReport:
        self.cost = CostTracker(
            groq_input_usd_per_mtok=self.config.groq_input_usd_per_mtok,
            groq_output_usd_per_mtok=self.config.groq_output_usd_per_mtok,
        )
        warnings: list[str] = []
        if simulate_tx_anomaly is None:
            simulate_tx_anomaly = self.config.simulate_tx_anomaly
        local_ok = self.ollama.available()
        if not local_ok:
            warnings.append(
                "Ollama is not reachable; semantic stage runs in lexical-fallback mode."
            )

        profile = self.repository.load_profile(name_substring, company_id)
        limit = max_events or (len(events_override) if events_override is not None else self.config.max_events_per_run)
        if events_override is None:
            news = self._chronological_events(
                self.repository.load_news(profile.id, limit=max(limit * 3, 30))
            )
        else:
            news = list(events_override)

        # Phase 1: masking proxy ------------------------------------------
        anonymizer = DataAnonymizer()
        company_token = anonymizer.register_sensitive_entity(profile.legal_name, "COMPANY")
        for node in profile.nodes:
            anonymizer.register_sensitive_entity(node.name, node.node_type)

        # Phase 2: entity resolution registry / control graph -------------
        registry = self._build_registry(profile)
        resolver = EntityResolver(registry)
        graph = self._build_graph(profile)
        if events_override is not None:
            self._apply_onboarding_topology(graph, profile)

        # Semantic cold-start is calibrated once; Layer-1 events stay lazy.
        profile_text = profile.profile_text()
        m0, sem_baseline = self._initialise_semantic_baseline(profile, local_ok, warnings)
        sem_det = PageHinkleyDetector()
        sem_det.seed(
            sem_baseline,
            k_std_delta=self.config.ph_semantic_delta_std,
            k_std_threshold=self.config.ph_semantic_threshold_std,
        )
        initial_exposure = graph.exposure_of(
            profile.company_node_id, beta=self.config.contagion_beta
        )
        topo_det = PageHinkleyDetector()
        topo_det.seed(self._topo_baseline(initial_exposure))

        tx_stream = QuantitativeTransactionStream()
        tx_amounts, tx_baseline_z = self._simulate_transactions(
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
            target_fwer=self.config.target_fwer,
        )

        # Stage 1-4: process Layer-1 events sequentially with early stopping.
        triage = RelevanceTriage(profile.all_aliases())
        if burn_in_events:
            burn_in_distances = self._semantic_burn_in_distances(
                burn_in_events=burn_in_events,
                triage=triage,
                anonymizer=anonymizer,
                m0=m0,
                local_ok=local_ok,
            )
            if len(burn_in_distances) >= 2:
                calibration = list(burn_in_distances)
                while len(calibration) < 3:
                    calibration.append(max(0.0, calibration[-1] - 0.01))
                sem_det.seed(
                    calibration,
                    k_std_delta=self.config.ph_semantic_delta_std,
                    k_std_threshold=self.config.ph_semantic_threshold_std,
                )
        outcomes: list[EventOutcome] = []
        max_risk = 0.0
        peak_outcome: EventOutcome | None = None
        company_exposure = initial_exposure
        contributors = graph.top_risk_contributors(
            profile.company_node_id, beta=self.config.contagion_beta
        )
        has_cycle = graph.check_ownership_cycles(profile.company_node_id)
        total_events = min(len(news), limit)

        for index, event in enumerate(news[:limit], start=1):
            self.cost.events_seen += 1
            verdict = triage.is_relevant(f"{event.title} {event.summary}")
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
                    topology_signal=round(company_exposure, 4),
                    behavioral_signal=0.0,
                )
                outcomes.append(outcome)
                self._stream_log(
                    index,
                    total_events,
                    event.title,
                    semantic_distance=0.0,
                    contagion_score=company_exposure,
                    combined_risk=0.0,
                    trigger_fired=False,
                )
                continue

            self.cost.events_passed_triage += 1

            masked_title = anonymizer.mask_text(event.title)
            fact_text, used_fallback, entities = self._extract_fact(masked_title, local_ok)
            new_nodes = self._resolve_and_update_graph(
                entities=entities,
                resolver=resolver,
                registry=registry,
                graph=graph,
                anonymizer=anonymizer,
                company_node_id=profile.company_node_id,
                adverse_score=event.adverse_score,
                event_text=f"{event.title} {event.summary} {fact_text}",
            )
            event_text = f"{event.title} {event.summary} {fact_text}"
            if self._is_red_flag_event(event_text) and self._targets_client(
                event_text, profile.all_aliases()
            ):
                graph.set_intrinsic_risk(profile.company_node_id, 1.0)
                self._graph_mutation_log(
                    f"Direct client hit: {profile.company_node_id} marked with intrinsic_risk=1.0"
                )
            has_cycle = graph.check_ownership_cycles(profile.company_node_id)
            company_exposure = graph.exposure_of(
                profile.company_node_id, beta=self.config.contagion_beta
            )
            contributors = graph.top_risk_contributors(
                profile.company_node_id, beta=self.config.contagion_beta
            )

            sem_distance = self._semantic_distance(
                profile_text=profile_text,
                m0=m0,
                embed_text=fact_text,
                event=event,
                local_ok=local_ok,
            )
            tx_amount = tx_amounts[(index - 1) % len(tx_amounts)] if tx_amounts else 0.0
            tx_z = tx_stream.record_transaction(tx_amount)

            result = fusion.update(
                {
                    _SEMANTIC: sem_distance,
                    _TOPOLOGY: company_exposure,
                    _BEHAVIOURAL: tx_z,
                }
            )
            trigger_fired = result.combined_risk > self.config.combined_risk_threshold

            outcome = EventOutcome(
                title=event.title,
                masked_title=masked_title,
                extracted_fact=fact_text,
                semantic_distance=round(sem_distance, 4),
                combined_risk=round(result.combined_risk, 4),
                alarms=result.alarms,
                triaged_in=True,
                used_fallback=used_fallback,
                topology_signal=round(company_exposure, 4),
                behavioral_signal=round(tx_z, 4),
                stream_statistics=result.statistics,
                stream_ratios=result.ratios,
                new_graph_nodes=new_nodes,
            )
            outcomes.append(outcome)

            if result.combined_risk > max_risk:
                max_risk = result.combined_risk
                peak_outcome = outcome

            self._stream_log(
                index,
                total_events,
                event.title,
                semantic_distance=sem_distance,
                contagion_score=company_exposure,
                combined_risk=result.combined_risk,
                trigger_fired=trigger_fired,
            )

            if trigger_fired:
                print(
                    f"[EARLY STOP] Critical risk threshold breached "
                    f"({result.combined_risk:.4f}). Halting Layer-1 stream.",
                    file=sys.stderr,
                    flush=True,
                )
                break

        alarm_fired = max_risk > self.config.combined_risk_threshold

        # Phase 5 + 6: unmask trace, draft report, run governance ---------
        governance_payload = None
        report_md = None
        if alarm_fired and peak_outcome is not None:
            trace = self._build_anomaly_trace(
                profile, peak_outcome, company_exposure, contributors, has_cycle, max_risk
            )
            report_md = self._draft_report(trace, warnings)
            governance_payload = self._run_governance(profile, peak_outcome, max_risk).as_dict()

        return EngineReport(
            client=self._client_summary(profile),
            security={
                "masked_entities": anonymizer.registered_count,
                "company_token": company_token,
                "note": "All Layer-1 text is processed locally on masked tokens.",
            },
            topology={
                "company_exposure": round(company_exposure, 4),
                "circular_ownership_detected": has_cycle,
                "top_contributors": [
                    {
                        "name": c["label"],
                        "type": c["type"],
                        "relation": c["rel_type"],
                        "intrinsic_risk": round(c["intrinsic_risk"], 3),
                        "contributed": round(c["contributed"], 3),
                    }
                    for c in contributors[:5]
                ],
            },
            streams=self._stream_summary(fusion, sem_det, topo_det, tx_det, company_exposure),
            decision={
                "alarm_fired": alarm_fired,
                "max_combined_risk": round(max_risk, 4),
                "threshold": self.config.combined_risk_threshold,
                "triggering_event": peak_outcome.title if peak_outcome else None,
            },
            cost=self.cost.summary(),
            events=outcomes,
            governance=governance_payload,
            report_markdown=report_md,
            warnings=warnings,
        )

    # -- phase helpers -----------------------------------------------------

    @staticmethod
    def _chronological_events(events: list[NewsEvent]) -> list[NewsEvent]:
        """Return Layer-1 events in chronological order, oldest first."""
        return sorted(
            events,
            key=lambda event: event.published_at or dt.datetime.max,
        )

    @staticmethod
    def _event_timestamp_str(event: NewsEvent) -> str:
        """Return an ISO timestamp for chronological cache comparisons."""
        timestamp = event.published_at
        if timestamp is None:
            timestamp = dt.datetime.now(dt.timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=dt.timezone.utc)
        return timestamp.astimezone(dt.timezone.utc).isoformat()

    def _build_registry(self, profile: ClientProfile) -> EntityRegistry:
        registry = EntityRegistry()
        registry.add_entity(profile.company_node_id, [profile.legal_name, *profile.aliases], "company")
        for node in profile.nodes:
            registry.add_entity(node.node_id, [node.name], node.node_type.lower())
        return registry

    def _build_graph(self, profile: ClientProfile) -> ComplianceDirectedGraph:
        graph = ComplianceDirectedGraph()
        graph.add_node(profile.company_node_id, profile.legal_name, "company", 0.0)
        for node in profile.nodes:
            graph.add_node(node.node_id, node.name, node.node_type, node.intrinsic_risk)
        for edge in profile.edges:
            graph.add_edge(
                edge.source_node_id,
                edge.target_node_id,
                edge.rel_type,
                edge.control_weight,
            )
        return graph

    @staticmethod
    def _topo_baseline(exposure: float) -> list[float]:
        """Seed topology drift detection around the client's starting exposure.

        A minimum jitter band avoids false spikes when exposure starts near zero
        and later rises through weak associate edges (e.g. 0.0 -> 0.05).
        """
        span = max(0.01, exposure * 0.05 + 0.005)
        jitter = (-span, -span / 2, 0.0, span / 2, span)
        return [max(0.0, round(exposure + delta, 4)) for delta in jitter]

    def _apply_onboarding_topology(
        self, graph: ComplianceDirectedGraph, profile: ClientProfile
    ) -> None:
        """Historical replay must start from Layer-2 KYC, not today's OSINT screen."""
        onboarding = self._onboarding_risks_for(profile.legal_name, profile.aliases)
        for node in profile.nodes:
            graph.set_intrinsic_risk(node.node_id, onboarding.get(node.name, 0.0))

    @staticmethod
    def _onboarding_risks_for(legal_name: str, aliases: list[str]) -> dict[str, float]:
        from scripts.seed_kyc import BASELINE_COMPANIES

        names = {legal_name, *aliases}
        for company in BASELINE_COMPANIES:
            company_names = {company["legal_name"], *company.get("aliases", [])}
            if names & company_names:
                return {
                    entry["name"]: float(entry.get("at_onboarding_risk", 0.0))
                    for entry in company.get("topology", [])
                }
        return {}

    def _semantic_burn_in_distances(
        self,
        burn_in_events: list[NewsEvent],
        triage: RelevanceTriage,
        anonymizer: DataAnonymizer,
        m0: list[float] | None,
        local_ok: bool,
    ) -> list[float]:
        """Calibrate semantic drift from benign historical precursor events."""
        distances: list[float] = []
        for event in burn_in_events:
            if not triage.is_relevant(f"{event.title} {event.summary}").is_relevant:
                continue
            masked_title = anonymizer.mask_text(event.title)
            fact_text, _, _ = self._extract_fact(masked_title, local_ok)
            distances.append(
                self._semantic_distance(
                    profile_text="",
                    m0=m0,
                    embed_text=fact_text,
                    event=event,
                    local_ok=local_ok,
                )
            )
        return distances

    def _gen_synthetic_headlines(self, profile: ClientProfile, local_ok: bool) -> list[str]:
        """Cold-start burn-in texts for the semantic baseline.

        Deterministic in-profile variants by default (no chat-model cost); the
        LLM-generated burn-in is used only when explicitly enabled.
        """
        if self.config.use_llm_burn_in and local_ok:
            try:
                headlines = self.sentinel.synthetic_headlines(
                    profile.profile_text(), self.config.burn_in_size
                )
                self.cost.add_local(
                    self.ollama.last_usage.prompt_tokens,
                    self.ollama.last_usage.completion_tokens,
                    "synthetic_headlines",
                )
                if headlines:
                    return headlines
            except Exception:
                pass
        return self._deterministic_burn_in(profile)

    @staticmethod
    def _deterministic_burn_in(profile: ClientProfile) -> list[str]:
        """Tight set of on-topic statements describing the onboarding model.

        These are kept close in meaning (low embedding variance) so the
        baseline captures the client's "normal" semantic neighbourhood; genuine
        business-model drift then reads as a clear excursion away from it.
        """
        model = profile.expected_business_model or profile.legal_name
        activity = profile.expected_activity or model
        name = profile.legal_name
        variants = [
            model,
            activity,
            f"{name}: {model}",
            f"{name} core business activity",
            f"{name} provides {model}",
        ]
        return [v for v in variants if v]

    def _initialise_semantic_baseline(
        self,
        profile: ClientProfile,
        local_ok: bool,
        warnings: list[str],
    ) -> tuple[list[float] | None, list[float]]:
        """Calibrate the semantic detector before streaming Layer-1 events."""
        profile_text = profile.profile_text()
        rng = random.Random(len(profile_text))
        fallback_baseline = [round(0.08 + rng.uniform(0, 0.04), 4) for _ in range(5)]
        if not local_ok:
            return None, fallback_baseline

        try:
            m0 = self.ollama.embed(profile_text)
            self.cost.add_local(0, 0, "embedding_profile")
        except Exception as exc:
            warnings.append(f"Ollama embedding failed during baseline setup ({exc}); using lexical fallback.")
            return None, fallback_baseline

        baseline: list[float] = []
        for text in self._gen_synthetic_headlines(profile, local_ok):
            try:
                baseline.append(cosine_distance(self.ollama.embed(text), m0))
                self.cost.events_embedded += 1
            except Exception:
                continue
        return m0, baseline if len(baseline) >= 3 else fallback_baseline

    def _extract_fact(
        self, masked_title: str, local_ok: bool
    ) -> tuple[str, bool, list[dict]]:
        """Stage 2: atomic fact extraction on masked text (chat model)."""
        if not local_ok:
            return masked_title, True, []
        fact = self.sentinel.extract(masked_title)
        self.cost.add_local(
            self.ollama.last_usage.prompt_tokens,
            self.ollama.last_usage.completion_tokens,
            "sentinel_extract",
        )
        return fact.text_for_embedding, fact.used_fallback, fact.entities_involved

    def _semantic_distance(
        self,
        profile_text: str,
        m0: list[float] | None,
        embed_text: str,
        event: NewsEvent,
        local_ok: bool,
    ) -> float:
        """Embed one event text and measure its drift from onboarding."""
        del profile_text
        if local_ok and m0 is not None and embed_text:
            try:
                self.cost.events_embedded += 1
                return cosine_distance(self.ollama.embed(embed_text), m0)
            except Exception:
                pass
        return 0.10 + 0.6 * event.adverse_score

    def _resolve_and_update_graph(
        self,
        entities: list[dict],
        resolver: EntityResolver,
        registry: EntityRegistry,
        graph: ComplianceDirectedGraph,
        anonymizer: DataAnonymizer,
        company_node_id: str,
        adverse_score: float,
        event_text: str,
    ) -> list[dict[str, object]]:
        """Resolve extracted entities and mutate the live topology graph."""
        created: list[dict[str, object]] = []
        relation, control_weight = self._infer_graph_relation(event_text)
        is_red_flag = self._is_red_flag_event(event_text)
        for entity in entities:
            raw_name = str(entity.get("name") or "").strip()
            raw_type = str(entity.get("type") or "ENTITY").strip().upper()
            if raw_type not in {"PERSON", "COMPANY"} or not raw_name:
                continue

            real_name = anonymizer.unmask_text(raw_name).strip()
            if not real_name or real_name.startswith("MASKED_"):
                continue

            resolution = resolver.resolve(real_name)
            node_id = str(resolution.get("node_id") or "")
            was_new = bool(resolution.get("is_new"))
            if not was_new and not node_id:
                continue

            if was_new:
                node_id = self._dynamic_node_id(registry, raw_type)
                privacy_token = anonymizer.register_sensitive_entity(real_name, raw_type)
                registry.add_entity(node_id, [real_name], raw_type.lower())
                graph.add_node(node_id, real_name, raw_type, 0.0)
                self._graph_mutation_log(
                    f"New Entity Detected: '{real_name}' -> registered as {node_id} "
                    f"(GDPR token {privacy_token})"
                )
            else:
                privacy_token = anonymizer.token_for(real_name) or node_id

            if node_id == company_node_id:
                continue

            graph.add_edge(node_id, company_node_id, relation, control_weight)
            self._graph_mutation_log(
                f"Added Directed Edge: {node_id} --[{relation} (w={control_weight:.1f})]--> "
                f"{company_node_id}"
            )
            if self._should_close_circular_ownership(event_text, relation):
                graph.add_edge(company_node_id, node_id, "OWNS_MAJORITY", 1.0)
                self._graph_mutation_log(
                    f"Added Circular Ownership Edge: {company_node_id} "
                    f"--[OWNS_MAJORITY (w=1.0)]--> {node_id}"
                )

            if is_red_flag:
                graph.set_intrinsic_risk(node_id, 1.0)
                intrinsic_risk = 1.0
                self._graph_mutation_log(
                    f"Risk Injection: node {node_id} ({privacy_token}) marked with "
                    "intrinsic_risk=1.0"
                )
            else:
                intrinsic_risk = min(max(float(adverse_score or 0.0), 0.0), 1.0)
                if was_new:
                    graph.set_intrinsic_risk(node_id, intrinsic_risk)

            if was_new:
                created.append(
                    {
                        "node_id": node_id,
                        "name": real_name,
                        "type": raw_type,
                        "intrinsic_risk": round(intrinsic_risk, 4),
                        "relation": relation,
                        "control_weight": control_weight,
                    }
                )
        return created

    @staticmethod
    def _graph_mutation_log(message: str) -> None:
        print(
            f"[GRAPH MUTATION] {message}",
            file=sys.stderr,
            flush=True,
        )

    @staticmethod
    def _infer_graph_relation(event_text: str) -> tuple[str, float]:
        text = event_text.lower()
        legal_proceeding_terms = (
            "investigation",
            "fraud",
            "lawsuit",
            "legal action",
            "class action",
            "securities fraud",
            "shareholder alert",
            "litigation",
            "court",
            "fine",
            "fined",
        )
        director_terms = (
            "director",
            "directs",
            "chief executive",
            "ceo",
            "chairman",
            "board",
            "appointed",
            "assumes",
            "joins",
            "takes control",
        )
        ownership_terms = (
            "owns",
            "owner",
            "shareholder",
            "majority",
            "stake",
            "acquires",
            "acquisition",
            "subsidiary",
            "beneficial owner",
        )
        if any(term in text for term in legal_proceeding_terms):
            return "LEGAL_PROCEEDING", 0.75
        if any(term in text for term in director_terms):
            return "DIRECTS", 1.0
        if any(term in text for term in ownership_terms):
            return "OWNS_MAJORITY", 1.0
        return "ASSOCIATED_WITH", 0.1

    @staticmethod
    def _is_red_flag_event(event_text: str) -> bool:
        text = event_text.lower()
        red_flags = (
            "sanction",
            "sancionado",
            "ofac",
            "criminal investigation",
            "penal",
            "fraud",
            "money laundering",
            "aml",
            "terrorist financing",
            "default",
            "fine",
            "fined",
        )
        return any(flag in text for flag in red_flags)

    @staticmethod
    def _targets_client(event_text: str, aliases: list[str]) -> bool:
        lowered = event_text.lower()
        for alias in aliases:
            if alias and alias.strip().lower() in lowered:
                return True
        return False

    @staticmethod
    def _should_close_circular_ownership(event_text: str, relation: str) -> bool:
        if relation != "OWNS_MAJORITY":
            return False
        text = event_text.lower()
        circular_terms = (
            "circular ownership",
            "cross-owned",
            "cross ownership",
            "ownership loop",
            "loop",
            "layering",
        )
        return any(term in text for term in circular_terms)

    @staticmethod
    def _dynamic_node_id(registry: EntityRegistry, entity_type: str) -> str:
        prefix = "DYN_PERSON" if entity_type == "PERSON" else "DYN_COMPANY"
        index = 1
        while f"{prefix}_{index:03d}" in registry.canonical:
            index += 1
        return f"{prefix}_{index:03d}"

    @staticmethod
    def _stream_log(
        index: int,
        total: int,
        title: str,
        semantic_distance: float,
        contagion_score: float,
        combined_risk: float,
        trigger_fired: bool,
    ) -> None:
        safe_title = " ".join((title or "").split())[:140]
        print(
            f"[STREAMING EVENT {index}/{total}] "
            f"Title: {safe_title} | "
            f"Semantic Dist: {semantic_distance:.4f} | "
            f"Contagion Score: {contagion_score:.4f} | "
            f"Combined Risk: {combined_risk:.4f} "
            f"[TRIGGER FIRED: {str(trigger_fired).upper()}]",
            file=sys.stderr,
            flush=True,
        )

    def _simulate_transactions(self, profile: ClientProfile, inject_anomaly: bool = False):
        """Simulate an internal transaction stream (Layer 2, allowed by the brief).

        A deterministic baseline is derived from the expected monthly volume.
        When ``inject_anomaly`` is set, a large spike (dormancy break / layering
        signal) is appended to exercise the behavioural detector; otherwise the
        stream stays within normal bounds and the behavioural stream is quiet.
        Returns (amounts, baseline_z_scores).
        """
        monthly = profile.expected_monthly_volume_eur or 1_000_000.0
        per_tx = monthly / 20.0
        rng = random.Random(profile.id)

        baseline_amounts = [per_tx * (1 + rng.uniform(-0.08, 0.08)) for _ in range(12)]

        warm = QuantitativeTransactionStream()
        baseline_z = [warm.record_transaction(a) for a in baseline_amounts]
        baseline_z = [z for z in baseline_z if z > 0]

        amounts = [per_tx * (1 + rng.uniform(-0.1, 0.1)) for _ in range(6)]
        if inject_anomaly:
            amounts.append(per_tx * 12.0)  # dormancy-break / layering spike
        else:
            amounts.append(per_tx * (1 + rng.uniform(-0.1, 0.1)))
        return amounts, baseline_z

    def _build_anomaly_trace(
        self, profile, peak_outcome, company_exposure, contributors, has_cycle, max_risk
    ) -> dict:
        top = contributors[0] if contributors else None
        return {
            "alert_id": f"ALT_{profile.id:03d}",
            "client_profile": {
                "legal_name": profile.legal_name,
                "jurisdiction": profile.jurisdiction,
                "expected_business_model": profile.expected_business_model,
                "baseline_risk_rating": profile.baseline_risk_rating,
            },
            "triggering_event": {
                "headline": peak_outcome.title,
                "extracted_fact": peak_outcome.extracted_fact,
                "dynamic_graph_nodes": peak_outcome.new_graph_nodes,
            },
            "metrics": {
                "combined_risk": round(max_risk, 4),
                "semantic_cosine_distance": peak_outcome.semantic_distance,
                "topological_exposure": round(company_exposure, 4),
                "circular_ownership_detected": has_cycle,
                "alarms": peak_outcome.alarms,
            },
            "topology_driver": (
                {
                    "name": top["label"],
                    "relation": top["rel_type"],
                    "intrinsic_risk": round(top["intrinsic_risk"], 3),
                }
                if top
                else None
            ),
            "proposed_action": "FREEZE_ASSETS / ENHANCED_DUE_DILIGENCE",
        }

    def _draft_report(self, trace: dict, warnings: list[str]) -> str:
        if self.config.groq_enabled():
            try:
                groq = GroqClient(self.config.groq_api_key, self.config.groq_report_model)
                synthesizer = AMLSynthesizer(groq)
                report = synthesizer.synthesize(trace)
                self.cost.add_cloud(
                    groq.last_usage.prompt_tokens, groq.last_usage.completion_tokens
                )
                return report
            except Exception as exc:
                warnings.append(f"Groq report generation failed ({exc}); using local fallback.")
        else:
            warnings.append("GROQ_API_KEY not set; using local fallback report.")
        return self._fallback_report(trace)

    @staticmethod
    def _fallback_report(trace: dict) -> str:
        m = trace["metrics"]
        driver = trace.get("topology_driver")
        driver_line = (
            f"- Contagio Topologico: exposicion {m['topological_exposure']} impulsada por "
            f"{driver['name']} ({driver['relation']}, riesgo {driver['intrinsic_risk']})."
            if driver
            else "- Contagio Topologico: sin contribuidor dominante."
        )
        return (
            f"# REPORTE DE CUMPLIMIENTO AML - REGISTRO DE ALERTA {trace['alert_id']}\n\n"
            "## 1. RESUMEN EJECUTIVO\n"
            f"Se ha detectado una desviacion de KYC estadisticamente significativa para "
            f"{trace['client_profile']['legal_name']} (riesgo combinado "
            f"{m['combined_risk']}). Evento disparador: {trace['triggering_event']['headline']}.\n\n"
            "## 2. EXPLICACION OPERATIVA PARA COMITE DE RIESGO\n"
            f"- Que cambio en el perfil del cliente: el evento publico indica "
            f"{trace['triggering_event']['extracted_fact']}.\n"
            "- Por que importa para KYC/AML: el hecho altera el perfil esperado y "
            "genera una senal adversa que debe revisarse antes de seguir operando.\n"
            f"- Cual fue el trigger principal: alarmas activas {m['alarms']}.\n\n"
            "## 3. ANALISIS DE DERIVA DE KYC (KYC DRIFT) MULTICORRIENTE\n"
            f"- Desviacion Semantica: distancia de coseno {m['semantic_cosine_distance']} "
            f"respecto al modelo de negocio declarado.\n"
            f"{driver_line}\n"
            f"- Anomalia Transaccional: alarmas activas {m['alarms']}.\n\n"
            "## 4. TRAZA DE METRICAS AUDITABLES\n"
            f"```json\n{trace['metrics']}\n```\n\n"
            "## 5. ACCION DE GOBERNANZA RECOMENDADA\n"
            f"- {trace['proposed_action']}: justificada por la deriva multicorriente detectada.\n"
        )

    def _run_governance(self, profile, peak_outcome, max_risk) -> ComplianceAlert:
        alert = ComplianceAlert(
            alert_id=f"ALT_{profile.id:03d}",
            target_entity_id=profile.company_node_id,
            target_display_name=profile.legal_name,
            risk_score=max_risk,
            trigger_streams=[k for k, v in peak_outcome.alarms.items() if v],
        )
        wf = FourEyesWorkflow()
        alert.log_transition("Alert detected by drift fusion gateway", "system")
        wf.assign_to_analyst(alert, "analyst_clara")
        wf.propose_mitigation(alert, "FREEZE_ASSETS", "analyst_clara")
        wf.approve_mitigation(alert, "officer_marcus", escalate=False)
        return alert

    # -- summaries ---------------------------------------------------------

    @staticmethod
    def _client_summary(profile: ClientProfile) -> dict:
        return {
            "legal_name": profile.legal_name,
            "country": profile.country,
            "jurisdiction": profile.jurisdiction,
            "baseline_risk_rating": profile.baseline_risk_rating,
            "expected_business_model": profile.expected_business_model,
            "known_graph_nodes": len(profile.nodes),
        }

    @staticmethod
    def _stream_summary(fusion, sem_det, topo_det, tx_det, company_exposure) -> dict:
        return {
            "bonferroni_scale": round(fusion.bonferroni_scale, 4),
            "semantic": {
                "last_statistic": round(sem_det.last_statistic, 4),
                "threshold": round(sem_det.threshold, 4),
            },
            "topology": {
                "last_statistic": round(topo_det.last_statistic, 4),
                "threshold": round(topo_det.threshold, 4),
                "observed_exposure": round(company_exposure, 4),
            },
            "behavioral_tx": {
                "last_statistic": round(tx_det.last_statistic, 4),
                "threshold": round(tx_det.threshold, 4),
            },
        }
