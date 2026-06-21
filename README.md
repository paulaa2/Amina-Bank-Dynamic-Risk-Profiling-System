# AMINA Bank Dynamic Risk Profiling System

Hackathon project for the **AMINA Bank Dynamic Risk Profiling System - Real-Time Intelligence** challenge at **SwissHacks 2026**.

This repository implements a working **Perpetual KYC (pKYC)** engine and analyst dashboard. The system combines public intelligence signals with simulated internal KYC profiles to detect **KYC drift**: material changes in a client's activity, structure, counterparties, or risk context that invalidate the assumptions made at onboarding.

The core idea is simple: traditional KYC reviews are periodic, but risk does not wait for a calendar review. This project turns KYC into a continuous monitoring loop.

## What The System Does

The platform monitors corporate clients across three risk streams:

| Stream | What it detects | Example |
|---|---|---|
| Semantic drift | Public evidence that the client is no longer operating as described during onboarding | A software company becoming a Bitcoin treasury vehicle |
| Topological drift | New or changing graph relationships, ownership links, sanctioned directors, risky counterparties, and cross-client contagion | A bank inheriting sovereign risk through a shared state-linked entity |
| Behavioural drift | Transactional anomalies against the expected activity profile | Dormant entity activation or abnormal transfer volume |

Those streams are fused into a single **combined risk score** with auditable evidence, graph mutations, event-level explanations, and a human governance workflow.

## Why It Matters For The Challenge

The challenge asks for an AI system that is intelligent, cost-aware, explainable, secure, and usable by compliance teams. This implementation addresses those requirements directly:

| Judging area | Implementation response |
|---|---|
| AI intelligence quality | Multi-stage pKYC pipeline with event triage, semantic extraction, graph contagion, Page-Hinkley drift detection, and curated historical replay |
| Cost efficiency | Cheap local filtering first; local Ollama extraction and embeddings; cloud LLM report generation only after a confirmed alert |
| UX and explainability | Next.js dashboard with client dossiers, graph evolution, event replay, full evidence modal, global contagion visualization, and light/dark themes |
| Compliance and safety | Data separation, masking proxy, source citations, audit trail, four-eyes workflow, and deterministic fallback reports |
| Engineering and architecture | Modular Python engine, FastAPI integration layer, persistent API cache, reproducible scenario runners, and typed frontend API client |

## Demo Highlights

The best live demonstration flow is:

1. Start the backend and dashboard.
2. Open the dashboard.
3. Use **Demo Studio** to replay curated historical scenarios.
4. Step through the graph event by event.
5. Show how risk accumulates before the final insolvency, sanctions, or governance shock.
6. Run a **Network Contagion** demo to show cross-client propagation through shared entities.

Recommended scenarios:

| Demo | What it shows |
|---|---|
| Wirecard historical replay | Gradual accounting-risk drift before insolvency |
| FTX rapid deterioration | Fast-moving liquidity and governance collapse |
| MicroStrategy drift | Business model drift from enterprise software to Bitcoin treasury exposure |
| VTB and Gazprombank contagion | Sovereign and sanctions risk propagation through shared Russian-state exposure |
| FTX and OpenAI contagion | Shared investor exposure through Sequoia Capital |

## Repository Structure

```text
.
|-- README.md                         # Main delivery guide
|-- requirements.txt                  # Python dependencies
|-- .env.example                      # Environment template without secrets
|-- data/
|   |-- risk_profiling.db             # SQLite database used by the engine
|   |-- scenarios/                    # Curated historical replay timelines
|   |-- scenario_replay_*.json/csv    # Precomputed replay outputs for presentation
|   |-- scenario_microstrategy_*      # Single-scenario replay output
|   `-- ppt_figures/                  # Generated figures for slides
|-- dashboard/                        # Next.js analyst dashboard
|   |-- app/                          # Dashboard routes
|   |-- components/                   # UI components
|   |-- lib/api-client.ts             # Typed API client and browser persistence
|   `-- README.md                     # Frontend-specific instructions
|-- docu/
|   |-- info_challenge.md             # Challenge statement
|   |-- final_implementation.md       # Technical design notes
|   `-- prompts.md                    # Prompt and agent notes
|-- notebooks/                        # Evaluation notebooks
|-- scripts/                          # Data collection and DB construction layer
|   |-- collectors/                   # News, sanctions, registry, domain, funding collectors
|   |-- build_database.py             # Builds the SQLite database
|   |-- seed_kyc.py                   # Simulated internal KYC profiles
|   `-- export_dashboard_cache.py     # Optional cache export helper
`-- src/                              # pKYC engine and API
    |-- api.py                        # FastAPI backend
    |-- pipeline.py                   # Main pKYC orchestration pipeline
    |-- run_demo.py                   # Single-client CLI demo
    |-- run_scenario_demo.py          # Curated historical replay runner
    |-- run_global_demo.py            # Multi-client contagion runner
    |-- detectors/                    # Page-Hinkley, transaction anomaly, fusion
    |-- graph/                        # Directed contagion graph logic
    |-- governance/                   # Four-eyes workflow
    |-- llm/                          # Ollama and Groq agent clients
    |-- security/                     # Data masking
    |-- triage/                       # Low-cost local event filtering
    `-- ingestion/                    # Read-only repository access to the DB
```

The folder layout is intentionally kept stable for delivery. Python imports and Next.js routes depend on this structure, so no functional code has been moved.

## System Architecture

```text
Public intelligence layer                    Simulated bank layer
News, registries, sanctions, domains         Onboarding KYC, graph, expected activity
                  |                                         |
                  +------------------+----------------------+
                                     |
                              Masking proxy
                                     |
                          Entity and event triage
                                     |
                 +-------------------+-------------------+
                 |                   |                   |
          Semantic drift       Topology drift      Behaviour drift
          embeddings + PH      directed graph      z-score anomaly
                 |                   |                   |
                 +-------------------+-------------------+
                                     |
                        Multi-stream risk fusion
                                     |
                         Alert, report, governance
                                     |
                              Analyst dashboard
```

### Main Components

- **Data layer (`scripts/`)** builds the SQLite database from public sources and seeded KYC profiles.
- **Risk engine (`src/pipeline.py`)** runs the staged pKYC analysis.
- **API (`src/api.py`)** exposes health, company list, analysis, streaming analysis, curated scenario replay, global contagion demos, and governance actions.
- **Dashboard (`dashboard/`)** provides the analyst-facing UI.
- **Scenario runners (`src/run_scenario_demo.py`, `src/run_global_demo.py`)** make the strongest demos reproducible.

## Installation

### 1. Python Environment

```bash
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Local Models

The system uses Ollama for local extraction and embeddings.

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

### 3. Environment Variables

Create a local `.env` file from `.env.example`.

```bash
# macOS/Linux
cp .env.example .env

# Windows PowerShell
Copy-Item .env.example .env
```

Minimum configuration:

```env
OLLAMA_HOST=http://localhost:11434
OLLAMA_EXTRACTOR_MODEL=qwen3:8b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
GROQ_REPORT_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=
```

`GROQ_API_KEY` is optional for core detection. If it is missing, the system still runs and uses deterministic fallback reporting instead of cloud-generated EDD text.

### 4. Frontend Dependencies

```bash
cd dashboard
npm install
cd ..
```

## Running The Project

Use three terminals for the full demo.

### Terminal 1 - API

```bash
python -m src.api
```

Default API URL: `http://localhost:8000`

Useful health check:

```bash
curl http://localhost:8000/api/health
```

### Terminal 2 - Preload Curated Scenarios

```bash
python -m src.run_scenario_demo --all --push-to-api
```

This computes all curated replay scenarios and pushes them to the API cache for a faster dashboard demo.

### Terminal 3 - Dashboard

```bash
cd dashboard
npm run dev
```

Open:

```text
http://localhost:3000
```

Main routes:

| Route | Purpose |
|---|---|
| `/` | Overview and monitored entities |
| `/client` | Client list |
| `/client/[id]` | Analyst dossier for one client |
| `/demos` | Demo Studio: curated replays and global contagion |
| `/history` | Previously cached analyses |
| `/metrics` | Comparative evaluation and lead-time charts |
| `/efficiency` | Pipeline cost-efficiency simulator |

## CLI Demo Commands

### List Available Clients

```bash
python -m src.run_demo --list
```

### Single-Client Analysis

```bash
python -m src.run_demo --company "MicroStrategy" --max-events 7
python -m src.run_demo --company "Wirecard" --max-events 5
python -m src.run_demo --company "FTX" --max-events 5
python -m src.run_demo --company "VTB" --max-events 5
```

### Optional Transaction Anomaly Simulation

```bash
python -m src.run_demo --company "Wirecard" --max-events 5 --simulate-tx-anomaly
```

This flag injects a simulated behavioural anomaly into the transaction stream. It is useful to demonstrate the behavioural detector, but it is not real bank transaction data.

### Curated Historical Replay

```bash
python -m src.run_scenario_demo
python -m src.run_scenario_demo --all
python -m src.run_scenario_demo --all --push-to-api
```

Outputs:

```text
data/scenario_microstrategy_result.json
data/scenario_microstrategy_result.csv
data/scenario_replay_summary.json
data/scenario_replay_summary.csv
data/scenario_replay_events.csv
```

### Global Contagion Demo

```bash
python -m src.run_global_demo --companies VTB Gazprombank --max-events 5
python -m src.run_global_demo --companies FTX OpenAI --max-events 5
python -m src.run_global_demo --companies VTB Gazprombank Surgutneftegas --max-events 5
```

What to watch in the logs:

```text
[GLOBAL ORCHESTRATOR] Shared threat published ...
[GLOBAL ORCHESTRATOR] Cross-client threat inherited ...
[GLOBAL ORCHESTRATOR] Early stop ...
```

## API Overview

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | Backend health check |
| GET | `/api/companies` | List monitored companies |
| GET | `/api/cache` | Show cached analysis IDs |
| POST | `/api/analyze/{company_id}` | Run a full pKYC analysis |
| GET | `/api/analyze/{company_id}` | Return cached analysis |
| GET | `/api/analyze/{company_id}/stream` | Stream analysis milestones via SSE |
| POST | `/api/analyze/{company_id}/action` | Apply a governance action |
| DELETE | `/api/analyze/{company_id}` | Invalidate one cached analysis |
| GET | `/api/scenarios/replay` | List curated replay scenarios |
| POST | `/api/scenario-replay/{scenario_id}` | Run a curated scenario |
| GET | `/api/scenarios` | List global contagion scenarios |
| POST | `/api/global-demo/scenario/{scenario_id}` | Run a global contagion scenario |

## Dashboard Persistence

The dashboard and API are designed for live demos:

- Browser persistence uses `localStorage` for reports, curated scenarios, and global demos.
- Backend persistence uses `data/api_cache/` for API-side cache files.
- Cached results survive page refreshes, browser close/reopen, and API restarts.
- Re-running with `force_refresh` recomputes the result.
- `data/api_cache/` is ignored by git because it is runtime cache, not source code.

## Data, Reality, And Simulation Boundaries

This is a hackathon prototype. The boundaries are explicit:

| Real or evidence-backed | Simulated or engineered |
|---|---|
| Public company names used for demonstration | Simulated internal KYC profiles seeded in `scripts/seed_kyc.py` |
| Curated historical scenario events with source URLs | Simulated bank transaction stream |
| Public adverse-media style narratives | Curated subset of historical events, not a complete historical feed |
| OpenSanctions/GLEIF/news-style collector layer | Initial graph state approximates onboarding, not a legally complete as-of historical ownership database |
| Semantic, topology, and fusion calculations | Synthetic transaction anomaly option for detector demonstration |

There is **no real AMINA Bank customer data** in this repository.

## Security And Governance Design

The system includes:

- Separation between public intelligence and internal KYC profile data.
- Local masking proxy before LLM processing.
- Local inference for extraction and embeddings.
- Cloud LLM use only for final report drafting after confirmed alerts.
- Source citations and event-level evidence.
- Explainable risk stream metrics.
- Four-eyes governance workflow with audit trail.
- Persistent but local API cache for demo continuity.

## Cost-Aware AI Pipeline

The pipeline is staged to avoid unnecessary expensive model calls:

1. Cheap local triage removes irrelevant events.
2. Local extraction produces structured facts.
3. Local embeddings calculate semantic distance.
4. Statistical detectors evaluate drift.
5. Graph contagion updates topology risk.
6. Cloud report generation runs only if the fused risk crosses the alert threshold.

This matches the challenge requirement to demonstrate lightweight versus heavy model usage and estimate cost per workflow.

## Recommended Presentation Script

1. **Open with the problem:** periodic KYC misses slow business drift and public-domain warning signals.
2. **Show the dashboard overview:** monitored clients and current alert state.
3. **Open Demo Studio:** select Wirecard, FTX, or MicroStrategy.
4. **Step through events:** show how each public event changes the graph and risk curve.
5. **Open full evidence:** show source title, summary, extracted fact, URL, and risk effect.
6. **Show governance:** analyst decision is not automatic; the system proposes and records human actions.
7. **Run Network Contagion:** show one client publishing a threat and another inheriting it through a shared entity.
8. **Close with compliance:** explain masking, cost-aware routing, auditability, and clear real-vs-simulated boundaries.

## Validation Commands

```bash
python -m compileall -q src scripts

cd dashboard
npm run lint
npm run build
```

## Notes For Reviewers

- The most polished user-facing experience is the Next.js dashboard, especially `/demos`.
- The strongest technical evidence is in the scenario runners and graph-based contagion logic.
- The project is optimized for a live hackathon presentation, so curated replay scenarios are included to avoid depending on live news availability during judging.
- The backend can still run live analysis from the SQLite database and current event store.
