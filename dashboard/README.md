# AMINA pKYC Dashboard

Next.js analyst dashboard for the AMINA Bank Dynamic Risk Profiling System.

The dashboard is designed for the hackathon demo: it connects to the FastAPI backend, visualizes pKYC risk analysis, replays curated historical scenarios step by step, and shows network contagion across related clients.

## Requirements

- Node.js compatible with Next.js 16
- Python API running at `http://localhost:8000` unless `NEXT_PUBLIC_API_URL` is set

## Setup

```bash
npm install
```

Optional environment override:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Development

```bash
npm run dev
```

Open:

```text
http://localhost:3000
```

## Production Build

```bash
npm run lint
npm run build
npm run start
```

## Main Routes

| Route | Purpose |
|---|---|
| `/` | Monitoring overview |
| `/client` | Company list |
| `/client/[id]` | Client dossier with graph, drift metrics, evidence, and governance |
| `/demos` | Demo Studio for curated replays and network contagion |
| `/history` | Cached analysis history |
| `/metrics` | Comparative evaluation and lead-time analytics |
| `/efficiency` | Cost-efficiency and scaling simulator |

## Persistence

The frontend stores reports, curated scenario replays, and global contagion results in browser `localStorage`. This means closing and reopening the page does not force recomputation.

The backend also persists API-side cache files under `data/api_cache/`, so demos survive API restarts as well.

Use the dashboard refresh/re-run controls or backend `force_refresh` options when you intentionally want to recompute.
