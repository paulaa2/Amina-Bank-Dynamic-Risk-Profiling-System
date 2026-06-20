"""FastAPI HTTP wrapper around the pKYC pipeline.

Run from the project root with the virtual environment active:

    uvicorn src.api:app --reload --port 8000

Or directly:

    python -m src.api
"""

from __future__ import annotations

import datetime as dt
import io
import json
import logging
import re
import sys
import threading
from contextlib import asynccontextmanager
from typing import Any, Generator, Optional

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .config import load_config
from .detectors import DriftFusion, PageHinkleyDetector, QuantitativeTransactionStream, StreamSignal
from .entities import EntityResolver
from .ingestion import ClientProfileRepository
from .pipeline import EventOutcome, PerpetualKYCPipeline
from .run_demo import _report_to_dict
from .run_global_demo import run_global_demo as _run_global_demo
from .run_scenario_demo import list_replay_scenarios, replay_scenario_for_api
from .security import DataAnonymizer
from .triage import RelevanceTriage

logger = logging.getLogger(__name__)

# ── Shared state ──────────────────────────────────────────────────────────────

_config = load_config()
_cache:  dict[str, dict]  = {}   # str(company_id) → full report dict
_lock = threading.Lock()

# Scheduler bookkeeping
_last_scheduled_run:   dt.datetime | None = None
_scheduled_run_active: bool               = False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_governance_to_pending(result: dict) -> None:
    """
    The pipeline simulation auto-resolves the full four-eyes workflow so that
    every demo run looks complete.  Before serving the report we strip that
    back to ``DETECTED`` so the operator must approve or dismiss themselves.
    """
    gov = result.get("governance")
    if not gov:
        return

    first_entry = next(
        (e for e in gov.get("audit_trail", []) if e.get("resulting_status") == "DETECTED"),
        {
            "timestamp":        dt.datetime.now(dt.timezone.utc).isoformat(),
            "user":             "system",
            "action":           "Alert detected by drift fusion gateway",
            "resulting_status": "DETECTED",
        },
    )

    gov["status"]                     = "DETECTED"
    gov["audit_trail"]                = [first_entry]
    gov["assigned_analyst"]           = None
    gov["proposed_mitigation_action"] = None
    gov["compliance_approver"]        = None


def _run_analysis_for(
    company_id: int,
    max_events: int = 5,
    simulate_tx_anomaly: bool = False,
) -> dict:
    """Run the pKYC pipeline for one company and return the serialisable result."""
    pipeline = PerpetualKYCPipeline(_config)
    report   = pipeline.run(
        company_id=company_id,
        max_events=max_events,
        simulate_tx_anomaly=simulate_tx_anomaly,
    )
    result   = _report_to_dict(report)
    result["id"] = str(company_id)
    _reset_governance_to_pending(result)
    return result


# ── Streaming analysis constants ──────────────────────────────────────────────

_SEMANTIC    = "semantic"
_TOPOLOGY    = "topology"
_BEHAVIOURAL = "behavioral_tx"


def _analyze_company_streaming(
    company_id: int,
    max_events: int = 5,
    simulate_tx_anomaly: bool = False,
) -> Generator[dict, None, None]:
    """
    Generator that mirrors PerpetualKYCPipeline.run() but yields SSE event
    dicts at each processing milestone so the frontend can render progressively.

    Events emitted (in order):
        baseline         → initial topology, client profile
        extraction       → new graph nodes discovered by Sentinel LLM
        risk_calculated  → live risk scores after each news event
        report_generating→ fired just before the Groq AML report is drafted
        complete         → full LiveReport (also written to cache)
    """
    pipeline  = PerpetualKYCPipeline(_config)
    warnings: list[str] = []

    local_ok = pipeline.ollama.available()
    if not local_ok:
        warnings.append(
            "Ollama is not reachable; semantic stage runs in lexical-fallback mode."
        )

    profile = pipeline.repository.load_profile(company_id=company_id)

    # ── Phase 1: masking + graph setup ────────────────────────────────────────
    anonymizer    = DataAnonymizer()
    company_token = anonymizer.register_sensitive_entity(profile.legal_name, "COMPANY")
    for node in profile.nodes:
        anonymizer.register_sensitive_entity(node.name, node.node_type)

    registry = pipeline._build_registry(profile)
    graph    = pipeline._build_graph(profile)

    company_exposure = graph.exposure_of(
        profile.company_node_id, beta=pipeline.config.contagion_beta
    )
    contributors = graph.top_risk_contributors(
        profile.company_node_id, beta=pipeline.config.contagion_beta
    )
    has_cycle = graph.check_ownership_cycles(profile.company_node_id)

    # ── Phase 2: detector setup (before baseline so thresholds go in it) ────────
    profile_text     = profile.profile_text()
    m0, sem_baseline = pipeline._initialise_semantic_baseline(profile, local_ok, warnings)

    sem_det = PageHinkleyDetector()
    sem_det.seed(
        sem_baseline,
        k_std_delta=pipeline.config.ph_semantic_delta_std,
        k_std_threshold=pipeline.config.ph_semantic_threshold_std,
    )
    topo_baseline = pipeline._topo_baseline(company_exposure)
    topo_det = PageHinkleyDetector()
    topo_det.seed(topo_baseline)

    tx_stream             = QuantitativeTransactionStream()
    tx_amounts, tx_baseline_z = pipeline._simulate_transactions(
        profile, inject_anomaly=simulate_tx_anomaly
    )
    tx_det = PageHinkleyDetector()
    tx_det.seed(tx_baseline_z if len(tx_baseline_z) >= 3 else [0.1, 0.2, 0.15, 0.25, 0.2])

    fusion = DriftFusion(
        [
            StreamSignal(_SEMANTIC,    sem_det,  weight=1.0),
            StreamSignal(_TOPOLOGY,    topo_det, weight=0.8),
            StreamSignal(_BEHAVIOURAL, tx_det,   weight=0.9),
        ],
        target_fwer=pipeline.config.target_fwer,
    )

    # ── Event 1: baseline (now includes calibrated detector thresholds) ──────
    yield {
        "event": "baseline",
        "data": {
            "id":     str(company_id),
            "client": pipeline._client_summary(profile),
            "security": {
                "masked_entities": anonymizer.registered_count,
                "company_token":   company_token,
                "note":            "All Layer-1 text is processed locally on masked tokens.",
            },
            "topology": {
                "company_exposure":            round(company_exposure, 4),
                "circular_ownership_detected": has_cycle,
                "top_contributors": [
                    {
                        "name":           c["label"],
                        "type":           c["type"],
                        "relation":       c["rel_type"],
                        "intrinsic_risk": round(c["intrinsic_risk"], 3),
                        "contributed":    round(c["contributed"], 3),
                    }
                    for c in contributors
                ],
            },
            "stream_thresholds": {
                "bonferroni_scale": round(fusion.bonferroni_scale, 4),
                "semantic":      round(sem_det.threshold, 4),
                "topology":      round(topo_det.threshold, 4),
                "behavioral_tx": round(tx_det.threshold, 4),
            },
        },
    }

    triage   = RelevanceTriage(profile.all_aliases())
    resolver = EntityResolver(registry)

    news = pipeline._chronological_events(
        pipeline.repository.load_news(profile.id, limit=max(max_events * 3, 30))
    )[:max_events]

    # ── Phase 3: event loop ───────────────────────────────────────────────────
    outcomes:     list[EventOutcome] = []
    max_risk:     float              = 0.0
    peak_outcome: EventOutcome | None = None

    for index, event in enumerate(news, start=1):
        pipeline.cost.events_seen += 1
        verdict = triage.is_relevant(f"{event.title} {event.summary}")
        if not verdict.is_relevant:
            outcomes.append(EventOutcome(event.title, "", "", 0.0, 0.0, {}, False, False))
            continue

        pipeline.cost.events_passed_triage += 1
        masked_title = anonymizer.mask_text(event.title)
        fact_text, used_fallback, entities = pipeline._extract_fact(masked_title, local_ok)

        new_nodes = pipeline._resolve_and_update_graph(
            entities=entities,
            resolver=resolver,
            registry=registry,
            graph=graph,
            anonymizer=anonymizer,
            company_node_id=profile.company_node_id,
            adverse_score=event.adverse_score,
            event_text=f"{event.title} {event.summary} {fact_text}",
        )

        # ── Event 2: extraction (fires for every article) ────────────────────
        yield {
            "event": "extraction",
            "data": {
                "event_title":   event.title[:120],
                "source":        event.source or "Unknown source",
                "adverse_score": round(event.adverse_score, 2),
                "new_nodes":     new_nodes,  # may be empty list
            },
        }

        has_cycle        = graph.check_ownership_cycles(profile.company_node_id)
        company_exposure = graph.exposure_of(
            profile.company_node_id, beta=pipeline.config.contagion_beta
        )
        contributors = graph.top_risk_contributors(
            profile.company_node_id, beta=pipeline.config.contagion_beta
        )

        sem_distance = pipeline._semantic_distance(
            profile_text=profile_text,
            m0=m0,
            embed_text=fact_text,
            event=event,
            local_ok=local_ok,
        )
        tx_amount = tx_amounts[(index - 1) % len(tx_amounts)] if tx_amounts else 0.0
        tx_z      = tx_stream.record_transaction(tx_amount)

        result = fusion.update(
            {
                _SEMANTIC:    sem_distance,
                _TOPOLOGY:    company_exposure,
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
            new_graph_nodes=new_nodes,
        )
        outcomes.append(outcome)

        if result.combined_risk > max_risk:
            max_risk     = result.combined_risk
            peak_outcome = outcome

        # ── Event 3: risk_calculated ──────────────────────────────────────────
        yield {
            "event": "risk_calculated",
            "data": {
                "event_title":   event.title[:120],
                "semantic":      round(sem_distance, 4),
                "topology":      round(company_exposure, 4),
                "behavioral_tx": round(tx_z, 4),
                "r_combined":    round(result.combined_risk, 4),
                "alarms":        result.alarms,
                "contributors": [
                    {
                        "name":           c["label"],
                        "type":           c["type"],
                        "relation":       c["rel_type"],
                        "intrinsic_risk": round(c["intrinsic_risk"], 3),
                        "contributed":    round(c["contributed"], 3),
                    }
                    for c in contributors
                ],
            },
        }

        if result.combined_risk > pipeline.config.combined_risk_threshold:
            break

    alarm_fired = max_risk > pipeline.config.combined_risk_threshold

    # ── Phase 4: report generation ────────────────────────────────────────────
    report_md:        str | None  = None
    governance_dict:  dict | None = None

    if alarm_fired and peak_outcome is not None:
        # ── Event 4: report_generating ────────────────────────────────────────
        yield {"event": "report_generating", "data": {}}

        trace     = pipeline._build_anomaly_trace(
            profile, peak_outcome, company_exposure, contributors, has_cycle, max_risk
        )
        report_md       = pipeline._draft_report(trace, warnings)
        governance_dict = pipeline._run_governance(profile, peak_outcome, max_risk).as_dict()

    # ── Phase 5: assemble and cache the final result ──────────────────────────
    result_dict: dict[str, Any] = {
        "id":     str(company_id),
        "client": pipeline._client_summary(profile),
        "security": {
            "masked_entities": anonymizer.registered_count,
            "company_token":   company_token,
            "note":            "All Layer-1 text is processed locally on masked tokens.",
        },
        "topology": {
            "company_exposure":            round(company_exposure, 4),
            "circular_ownership_detected": has_cycle,
            "top_contributors": [
                {
                    "name":           c["label"],
                    "type":           c["type"],
                    "relation":       c["rel_type"],
                    "intrinsic_risk": round(c["intrinsic_risk"], 3),
                    "contributed":    round(c["contributed"], 3),
                }
                for c in contributors
            ],
        },
        "streams": pipeline._stream_summary(
            fusion, sem_det, topo_det, tx_det, company_exposure
        ),
        "decision": {
            "alarm_fired":       alarm_fired,
            "max_combined_risk": round(max_risk, 4),
            "threshold":         pipeline.config.combined_risk_threshold,
            "triggering_event":  peak_outcome.title if peak_outcome else None,
        },
        "cost": pipeline.cost.summary(),
        "events": [
            {
                "title":            o.title,
                "masked_title":     o.masked_title,
                "extracted_fact":   o.extracted_fact,
                "triaged_in":       o.triaged_in,
                "semantic_distance": o.semantic_distance,
                "combined_risk":    o.combined_risk,
                "alarms":           o.alarms,
                "new_graph_nodes":  o.new_graph_nodes,
            }
            for o in outcomes
        ],
        "governance":      governance_dict,
        "report_markdown": report_md,
        "warnings":        warnings,
    }

    _reset_governance_to_pending(result_dict)

    with _lock:
        _cache[str(company_id)] = result_dict

    # ── Event 5: complete ─────────────────────────────────────────────────────
    yield {"event": "complete", "data": result_dict}


def _scheduled_analyses() -> None:
    """
    Biweekly job: re-run the full pKYC pipeline on every monitored entity and
    refresh the cache.  Only companies whose alert has already been resolved
    (RESOLVED_MITIGATED / RESOLVED_FALSE_POSITIVE) will have their cache entry
    overwritten; pending alerts are left untouched so operators can still act.
    """
    global _last_scheduled_run, _scheduled_run_active

    _scheduled_run_active = True
    logger.info("Scheduled pKYC analysis started at %s", dt.datetime.now(dt.timezone.utc))

    try:
        repo      = ClientProfileRepository(_config.database_url)
        companies = repo.list_companies()

        for company in companies:
            cid = company["id"]
            key = str(cid)

            # Skip companies with a pending operator decision
            with _lock:
                existing = _cache.get(key)
            if existing:
                gov    = existing.get("governance") or {}
                status = gov.get("status", "")
                if status in ("DETECTED", "UNDER_REVIEW", "FOUR_EYES_PENDING"):
                    logger.info("Skipping company %s — pending operator action (%s)", cid, status)
                    continue

            try:
                result = _run_analysis_for(cid)
                result["_scheduled_refresh"] = True
                with _lock:
                    _cache[key] = result
                logger.info("Scheduled analysis complete for company %s", cid)
            except Exception as exc:
                logger.error("Scheduled analysis failed for company %s: %s", cid, exc)

        _last_scheduled_run = dt.datetime.now(dt.timezone.utc)
        logger.info("Scheduled pKYC analysis finished at %s", _last_scheduled_run)

    finally:
        _scheduled_run_active = False



# ── Pre-defined contagion scenarios (from README demos) ───────────────────────

SCENARIOS: dict[str, dict[str, Any]] = {
    "russian_sovereign": {
        "id":          "russian_sovereign",
        "name":        "Russian Sovereign Cluster",
        "description": (
            "VTB sanctions trigger cross-client contagion: "
            "Gazprombank inherits 'Government of Russia' risk (0.15 → 0.90) "
            "before processing its own news events."
        ),
        "companies":          ["VTB", "Gazprombank"],
        "expected_contagion": "Government of Russia → Gazprombank",
        "max_events":         5,
    },
    "vc_contagion": {
        "id":          "vc_contagion",
        "name":        "VC Investor Contagion",
        "description": (
            "FTX collapse publishes Sequoia Capital (risk 0.53). "
            "OpenAI, which shares the same institutional investor, "
            "inherits elevated Sequoia risk and enters alarm."
        ),
        "companies":          ["FTX", "OpenAI"],
        "expected_contagion": "Sequoia Capital → OpenAI",
        "max_events":         5,
    },
    "russian_triple": {
        "id":          "russian_triple",
        "name":        "Full Russian Triple Cluster",
        "description": (
            "VTB and Gazprombank both alarm; Surgutneftegas inherits "
            "'Government of Russia' from the shared threat memory but its "
            "own news events fail triage — demonstrating partial propagation."
        ),
        "companies":          ["VTB", "Gazprombank", "Surgutneftegas"],
        "expected_contagion": "Government of Russia → Gazprombank, Surgutneftegas",
        "max_events":         5,
    },
}

# Cache for global demo results (keyed by scenario_id)
_global_cache: dict[str, dict] = {}


def _parse_contagion_log(log: str) -> list[dict[str, Any]]:
    """Parse the stderr stream from run_global_demo into structured events."""
    events: list[dict[str, Any]] = []
    for line in log.splitlines():
        m = re.search(
            r"Cross-client threat inherited target=(\S+) entity=(.+?) risk=([\d.]+)", line
        )
        if m:
            events.append({
                "type":   "inherited",
                "target": m.group(1),
                "entity": m.group(2).strip(),
                "risk":   float(m.group(3)),
            })
            continue

        m = re.search(
            r"Shared threat published source=(\S+) entity=(.+?) risk=([\d.]+)", line
        )
        if m:
            events.append({
                "type":   "published",
                "source": m.group(1),
                "entity": m.group(2).strip(),
                "risk":   float(m.group(3)),
            })
            continue

        m = re.search(r"Early stop target=(\S+) risk=([\d.]+)", line)
        if m:
            events.append({
                "type":   "frozen",
                "target": m.group(1),
                "risk":   float(m.group(2)),
            })
            continue

        m = re.search(
            r"\[GLOBAL EVENT \d+/\d+\] target=(\S+) .*?risk=([\d.]+).*?trigger=(TRUE|FALSE) title=(.+)$",
            line,
        )
        if m:
            events.append({
                "type":    "event",
                "target":  m.group(1),
                "risk":    float(m.group(2)),
                "trigger": m.group(3) == "TRUE",
                "title":   m.group(4).strip()[:120],
            })
    return events


# ── Scheduler setup ───────────────────────────────────────────────────────────

_scheduler = BackgroundScheduler(timezone="UTC")
_scheduler.add_job(
    _scheduled_analyses,
    # Every two weeks on Monday at 04:00 UTC
    CronTrigger(day_of_week="mon", hour=4, minute=0, week="*/2", timezone="UTC"),
    id="biweekly_kyc_refresh",
    replace_existing=True,
    misfire_grace_time=3600,   # allow up to 1 h late start
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _scheduler.start()
    logger.info(
        "Biweekly pKYC scheduler started — next run: %s",
        _scheduler.get_job("biweekly_kyc_refresh").next_run_time,
    )
    yield
    _scheduler.shutdown(wait=False)


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AMINA Bank pKYC Engine",
    description="Dynamic Risk Profiling API — KYC Drift Detection & AML Compliance",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "engine": "AMINA Bank pKYC v1.0"}


@app.get("/api/companies")
def list_companies():
    """Return the list of all seeded companies from the SQLite database (fast)."""
    repo = ClientProfileRepository(_config.database_url)
    return repo.list_companies()


@app.get("/api/cache")
def get_cache_status():
    """Return which company IDs already have completed analyses cached."""
    with _lock:
        return {"cached_ids": list(_cache.keys()), "count": len(_cache)}


# ── Scheduler endpoints ───────────────────────────────────────────────────────

@app.get("/api/scheduler/status")
def scheduler_status():
    """Return the current scheduling configuration and timing information."""
    job      = _scheduler.get_job("biweekly_kyc_refresh")
    next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
    return {
        "running":          _scheduler.running,
        "schedule":         "Every 2 weeks · Monday 04:00 UTC",
        "next_run":         next_run,
        "last_run":         _last_scheduled_run.isoformat() if _last_scheduled_run else None,
        "run_in_progress":  _scheduled_run_active,
        "cached_companies": len(_cache),
    }


@app.post("/api/scheduler/run-now")
def trigger_run_now(background_tasks: BackgroundTasks):
    """
    Immediately trigger the scheduled analysis outside of the cron schedule.
    Useful for demos and manual compliance sweeps.
    Returns immediately; the analysis runs in a background thread.
    """
    if _scheduled_run_active:
        raise HTTPException(status_code=409, detail="A scheduled run is already in progress.")
    background_tasks.add_task(_scheduled_analyses)
    return {
        "status":  "triggered",
        "message": "Full compliance sweep started in background — check /api/scheduler/status for progress.",
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


# ── Analysis endpoints ────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    max_events:         Optional[int] = 5
    simulate_tx_anomaly: bool         = False
    force_refresh:       bool         = False


@app.post("/api/analyze/{company_id}")
def analyze_company(company_id: int, req: AnalyzeRequest = AnalyzeRequest()):
    """
    Run the full pKYC pipeline for one company.  Results are cached; pass
    force_refresh=true to invalidate.  Expect 15–60 s on first call.
    """
    cache_key = str(company_id)

    with _lock:
        if not req.force_refresh and not req.simulate_tx_anomaly and cache_key in _cache:
            return _cache[cache_key]

    try:
        result = _run_analysis_for(
            company_id,
            max_events=req.max_events or 5,
            simulate_tx_anomaly=req.simulate_tx_anomaly,
        )
        if not req.simulate_tx_anomaly:
            with _lock:
                _cache[cache_key] = result
        return result

    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/analyze/{company_id}")
def get_cached_analysis(company_id: int):
    """Return the cached analysis if it exists, 404 otherwise."""
    with _lock:
        result = _cache.get(str(company_id))
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="No cached analysis — call POST /api/analyze/{id} first.",
        )
    return result


@app.get("/api/analyze/{company_id}/stream")
def stream_analysis(
    company_id:    int,
    max_events:    int  = 5,
    force_refresh: bool = False,
    simulate_tx_anomaly: bool = False,
):
    """
    Stream the pKYC analysis as Server-Sent Events.

    Yields JSON milestone events separated by ``\\n\\n``:
        baseline, extraction, risk_calculated, report_generating, complete

    If the company is already cached (and force_refresh is false) a single
    ``complete`` event is returned immediately so the UI renders instantly.
    """
    cache_key = str(company_id)

    if not force_refresh and not simulate_tx_anomaly:
        with _lock:
            cached = _cache.get(cache_key)
        if cached:
            def _cached():
                yield (
                    "data: "
                    + json.dumps({"event": "complete", "data": cached}, default=str)
                    + "\n\n"
                )
            return StreamingResponse(
                _cached(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

    def _live():
        try:
            for evt in _analyze_company_streaming(
                company_id,
                max_events,
                simulate_tx_anomaly=simulate_tx_anomaly,
            ):
                yield "data: " + json.dumps(evt, default=str) + "\n\n"
        except LookupError as exc:
            yield (
                "data: "
                + json.dumps({"event": "error", "data": {"message": str(exc)}}, default=str)
                + "\n\n"
            )
        except Exception as exc:
            logger.exception("SSE analysis failed for company %d", company_id)
            yield (
                "data: "
                + json.dumps({"event": "error", "data": {"message": str(exc)}}, default=str)
                + "\n\n"
            )

    return StreamingResponse(
        _live(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class ActionRequest(BaseModel):
    action:   str = "APPROVE_FREEZE"   # APPROVE_FREEZE | APPROVE_ENHANCED_DD | DISMISS_FALSE_POSITIVE
    operator: str = "compliance_operator"


@app.post("/api/analyze/{company_id}/action")
def take_governance_action(company_id: int, req: ActionRequest):
    """
    Record a real operator governance decision.
    Appends an audit-trail entry and advances the status.
    """
    cache_key = str(company_id)
    with _lock:
        result = _cache.get(cache_key)

    if result is None:
        raise HTTPException(status_code=404, detail="No analysis cached for this company.")
    gov = result.get("governance")
    if gov is None:
        raise HTTPException(status_code=400, detail="No active governance record for this alert.")

    now = dt.datetime.now(dt.timezone.utc).isoformat()

    match req.action:
        case "APPROVE_FREEZE":
            action_text = "Asset freeze approved and executed by operator"
            new_status  = "RESOLVED_MITIGATED"
            gov["proposed_mitigation_action"] = "FREEZE_ASSETS"
        case "APPROVE_ENHANCED_DD":
            action_text = "Enhanced Due Diligence requested by operator"
            new_status  = "FOUR_EYES_PENDING"
            gov["proposed_mitigation_action"] = "ENHANCED_DUE_DILIGENCE"
        case "DISMISS_FALSE_POSITIVE":
            action_text = "Alert dismissed as false positive by operator"
            new_status  = "RESOLVED_FALSE_POSITIVE"
        case _:
            raise HTTPException(status_code=400, detail=f"Unknown action '{req.action}'.")

    gov["audit_trail"].append(
        {
            "timestamp":        now,
            "user":             req.operator,
            "action":           action_text,
            "resulting_status": new_status,
        }
    )
    gov["status"]             = new_status
    gov["assigned_analyst"]   = req.operator
    gov["compliance_approver"] = req.operator if new_status == "RESOLVED_MITIGATED" else None

    with _lock:
        _cache[cache_key] = result

    return result


@app.delete("/api/analyze/{company_id}")
def invalidate_cache(company_id: int):
    """Evict a single company from the cache so it will be re-analysed on next call."""
    with _lock:
        evicted = _cache.pop(str(company_id), None)
    return {"evicted": evicted is not None, "company_id": company_id}


# ── Curated scenario replay (historical timelines for dashboard) ───────────────

_scenario_cache: dict[str, dict] = {}


@app.get("/api/scenarios/replay")
def list_curated_scenarios():
    """Return curated historical replay scenarios (same timelines as run_scenario_demo)."""
    repo = ClientProfileRepository(_config.database_url)
    companies = repo.list_companies()
    scenarios = list_replay_scenarios()
    for scenario in scenarios:
        client = scenario["client"].lower()
        scenario["company_id"] = next(
            (
                row["id"]
                for row in companies
                if client in row["legal_name"].lower()
                or row["legal_name"].lower() in client
            ),
            None,
        )
    return scenarios


@app.post("/api/scenario-replay/{scenario_id}")
def run_curated_scenario(scenario_id: str, force_refresh: bool = False):
    """
    Replay a curated evidence-backed scenario and return a dashboard-compatible
    LiveReport (includes ``events[].new_graph_nodes`` for the corporate graph).
    """
    with _lock:
        if not force_refresh and scenario_id in _scenario_cache:
            return _scenario_cache[scenario_id]

    try:
        result = replay_scenario_for_api(scenario_id, _config.database_url)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    _reset_governance_to_pending(result)
    with _lock:
        _scenario_cache[scenario_id] = result
        if result.get("id"):
            _cache[str(result["id"])] = result
    return result


# ── Global demo / contagion endpoints ─────────────────────────────────────────

@app.get("/api/scenarios")
def list_scenarios():
    """Return the pre-defined multi-client contagion demonstration scenarios."""
    return list(SCENARIOS.values())


class ScenarioRunRequest(BaseModel):
    max_events: Optional[int] = None
    force_refresh: bool = False


@app.post("/api/global-demo/scenario/{scenario_id}")
def run_scenario(scenario_id: str, req: ScenarioRunRequest = ScenarioRunRequest()):
    """
    Run a pre-defined cross-client contagion scenario.

    Captures the global orchestrator's stderr output to build a structured
    contagion trace (published / inherited / frozen events).  Results are
    cached by scenario_id.  Expect 1–3 min on first call (multiple Ollama runs).
    """
    if scenario_id not in SCENARIOS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario '{scenario_id}'. "
                   f"Available: {list(SCENARIOS.keys())}",
        )
    scenario = SCENARIOS[scenario_id]

    with _lock:
        if not req.force_refresh and scenario_id in _global_cache:
            return _global_cache[scenario_id]

    max_events = req.max_events or scenario["max_events"]
    companies  = scenario["companies"]

    # Capture stderr so we can extract the structured contagion log
    old_stderr = sys.stderr
    sys.stderr  = stderr_buf = io.StringIO()
    try:
        raw = _run_global_demo(
            companies=companies,
            max_events_per_client=max_events,
            simulate_tx_anomaly=False,
        )
    finally:
        sys.stderr = old_stderr
    log_text = stderr_buf.getvalue()

    # Look up numeric IDs for each company name so the frontend can link dossiers
    repo = ClientProfileRepository(_config.database_url)
    all_companies = {c["legal_name"]: c["id"] for c in repo.list_companies()}

    # Enrich each client report
    company_ids: dict[str, int] = {}
    for name, report in raw["clients"].items():
        _reset_governance_to_pending(report)
        # Find numeric ID by substring match (same logic as the DB query)
        matched_id = next(
            (cid for legal, cid in all_companies.items()
             if name.lower() in legal.lower() or legal.lower() in name.lower()),
            None,
        )
        if matched_id:
            report["id"] = str(matched_id)
            company_ids[name] = matched_id

    result = {
        "scenario_id":          scenario_id,
        "scenario_name":        scenario["name"],
        "scenario_description": scenario["description"],
        "expected_contagion":   scenario["expected_contagion"],
        "companies":            companies,
        "company_ids":          company_ids,
        "shared_threat_memory": raw["shared_threat_memory"],
        "contagion_events":     _parse_contagion_log(log_text),
        "clients":              raw["clients"],
    }

    with _lock:
        _global_cache[scenario_id] = result

    return result


# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("src.api:app", host="0.0.0.0", port=8000, reload=False)
