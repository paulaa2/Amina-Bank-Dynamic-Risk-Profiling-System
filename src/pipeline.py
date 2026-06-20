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

import random
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
from .detectors.page_hinkley import generate_synthetic_baseline
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
    alarms: dict
    triaged_in: bool
    used_fallback: bool


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
    ) -> EngineReport:
        warnings: list[str] = []
        if simulate_tx_anomaly is None:
            simulate_tx_anomaly = self.config.simulate_tx_anomaly
        local_ok = self.ollama.available()
        if not local_ok:
            warnings.append(
                "Ollama is not reachable; semantic stage runs in lexical-fallback mode."
            )

        profile = self.repository.load_profile(name_substring, company_id)
        news = self.repository.load_news(
            profile.id, limit=max(self.config.max_events_per_run * 3, 30)
        )

        # Phase 1: masking proxy ------------------------------------------
        anonymizer = DataAnonymizer()
        company_token = anonymizer.register_sensitive_entity(profile.legal_name, "COMPANY")
        for node in profile.nodes:
            anonymizer.register_sensitive_entity(node.name, node.node_type)

        # Phase 2: entity resolution registry / control graph -------------
        registry = self._build_registry(profile)
        resolver = EntityResolver(registry)
        graph = self._build_graph(profile)
        contagion = graph.propagate_directed_contagion(beta=self.config.contagion_beta)
        company_exposure = contagion.get(profile.company_node_id, 0.0)
        contributors = graph.top_risk_contributors(
            profile.company_node_id, beta=self.config.contagion_beta
        )
        has_cycle = graph.check_ownership_cycles(profile.company_node_id)

        # Stage 1: triage every candidate event up front (cheap, local) ---
        triage = RelevanceTriage(profile.all_aliases())
        limit = max_events or self.config.max_events_per_run
        outcomes: list[EventOutcome] = []
        relevant: list[tuple[NewsEvent, str]] = []  # (event, masked_title)

        for event in news:
            if len(relevant) >= limit:
                break
            self.cost.events_seen += 1
            verdict = triage.is_relevant(f"{event.title} {event.summary}")
            if not verdict.is_relevant:
                outcomes.append(
                    EventOutcome(event.title, "", "", 0.0, 0.0, {}, False, False)
                )
                continue
            self.cost.events_passed_triage += 1
            relevant.append((event, anonymizer.mask_text(event.title)))

        # Stage 2: run ALL local extractions together so the chat model is
        # loaded into memory only once (avoids costly model swapping with the
        # embedding model on every event).
        profile_text = profile.profile_text()
        headlines = self._gen_synthetic_headlines(profile_text, local_ok)
        facts = [self._extract_fact(mt, local_ok) for (_, mt) in relevant]

        # Stage 3a: run ALL embeddings together so the embedding model is
        # loaded only once, immediately after the chat model is released.
        m0, sem_baseline, event_distances = self._embed_all(
            profile_text, headlines, [f for f, _ in facts], relevant, local_ok
        )

        # Stage 3b/3c: calibrate the statistical detectors ----------------
        sem_det = PageHinkleyDetector()
        sem_det.seed(
            sem_baseline,
            k_std_delta=self.config.ph_delta_std,
            k_std_threshold=self.config.ph_threshold_std,
        )
        topo_det = PageHinkleyDetector()
        topo_det.seed([0.01, 0.02, 0.01, 0.02, 0.015])

        tx_stream = QuantitativeTransactionStream()
        tx_amounts, tx_baseline_z = self._simulate_transactions(
            profile, inject_anomaly=simulate_tx_anomaly
        )
        tx_det = PageHinkleyDetector()
        tx_det.seed(tx_baseline_z if len(tx_baseline_z) >= 3 else [0.1, 0.2, 0.15, 0.25, 0.2])

        # Phase 4: fusion gateway -----------------------------------------
        fusion = DriftFusion(
            [
                StreamSignal(_SEMANTIC, sem_det, weight=1.0),
                StreamSignal(_TOPOLOGY, topo_det, weight=0.8),
                StreamSignal(_BEHAVIOURAL, tx_det, weight=0.9),
            ],
            target_fwer=self.config.target_fwer,
        )

        max_risk = 0.0
        peak_outcome: EventOutcome | None = None
        for i, (event, masked_title) in enumerate(relevant):
            fact_text, used_fallback = facts[i]
            sem_distance = event_distances[i]
            tx_amount = tx_amounts[(i + 1) % len(tx_amounts)] if tx_amounts else 0.0
            tx_z = tx_stream.record_transaction(tx_amount)

            result = fusion.update(
                {
                    _SEMANTIC: sem_distance,
                    _TOPOLOGY: company_exposure,
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
            )
            outcomes.append(outcome)

            if result.combined_risk > max_risk:
                max_risk = result.combined_risk
                peak_outcome = outcome

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

    def _gen_synthetic_headlines(self, profile_text: str, local_ok: bool) -> list[str]:
        """Stage 2 cold-start: generate in-profile routine statements (chat model)."""
        if not local_ok:
            return []
        try:
            headlines = self.sentinel.synthetic_headlines(
                profile_text, self.config.burn_in_size
            )
            self.cost.add_local(
                self.ollama.last_usage.prompt_tokens,
                self.ollama.last_usage.completion_tokens,
                "synthetic_headlines",
            )
            return headlines
        except Exception:
            return []

    def _extract_fact(self, masked_title: str, local_ok: bool):
        """Stage 2: atomic fact extraction on masked text (chat model)."""
        if not local_ok:
            return masked_title, True
        fact = self.sentinel.extract(masked_title)
        self.cost.add_local(
            self.ollama.last_usage.prompt_tokens,
            self.ollama.last_usage.completion_tokens,
            "sentinel_extract",
        )
        return fact.text_for_embedding, fact.used_fallback

    def _embed_all(
        self,
        profile_text: str,
        headlines: list[str],
        fact_texts: list[str],
        relevant: list[tuple],
        local_ok: bool,
    ):
        """Stage 3a: compute every embedding in one consecutive batch.

        Returns (m0, baseline_distances, event_distances). Keeping all embedding
        calls together means the embedding model is loaded into memory only
        once for the whole run.
        """
        rng = random.Random(len(profile_text))
        fallback_baseline = [round(0.08 + rng.uniform(0, 0.04), 4) for _ in range(5)]

        if local_ok:
            try:
                m0 = self.ollama.embed(profile_text)
                self.cost.add_local(
                    self.ollama.last_usage.prompt_tokens,
                    self.ollama.last_usage.completion_tokens,
                    "embedding",
                )
                baseline = []
                for text in headlines:
                    try:
                        baseline.append(cosine_distance(self.ollama.embed(text), m0))
                        self.cost.events_embedded += 1
                    except Exception:
                        continue

                event_distances = []
                for (event, _masked), fact in zip(relevant, fact_texts):
                    dist = None
                    if fact:
                        try:
                            dist = cosine_distance(self.ollama.embed(fact), m0)
                            self.cost.events_embedded += 1
                        except Exception:
                            dist = None
                    if dist is None:
                        dist = 0.10 + 0.6 * event.adverse_score
                    event_distances.append(dist)

                baseline = baseline if len(baseline) >= 3 else fallback_baseline
                return m0, baseline, event_distances
            except Exception:
                pass

        # Full lexical fallback when local inference is unavailable.
        event_distances = [0.10 + 0.6 * ev.adverse_score for (ev, _m) in relevant]
        return None, fallback_baseline, event_distances

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
            "## 2. ANALISIS DE DERIVA DE KYC (KYC DRIFT) MULTICORRIENTE\n"
            f"- Desviacion Semantica: distancia de coseno {m['semantic_cosine_distance']} "
            f"respecto al modelo de negocio declarado.\n"
            f"{driver_line}\n"
            f"- Anomalia Transaccional: alarmas activas {m['alarms']}.\n\n"
            "## 3. TRAZA DE METRICAS AUDITABLES\n"
            f"```json\n{trace['metrics']}\n```\n\n"
            "## 4. ACCION DE GOBERNANZA RECOMENDADA\n"
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
