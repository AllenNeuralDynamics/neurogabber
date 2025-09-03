# Neurogabber — Architecture (MVP)

Concise overview of the current repo, data flow, and roadmap. Use this as system/context for LLMs.

## Goal
Chat-driven navigation of massive neuroimaging data in **Neuroglancer** with optional plots and context from user-supplied data (e.g., CSV of ROIs). Start with **state links**, later support **same-origin embedding**.

## Components
- **Backend (FastAPI, Python)**
  - Tool endpoints to mutate Neuroglancer **state JSON** and compute plots.
  - LLM adapter for **tool-calling** (OpenAI-compatible).
  - Minimal state store (in‑memory → DB later).
- **Frontends**
  - **Panel (Python)**: `ChatInterface` + `panel-neuroglancer` widget (embedded NG).
  - **React/Next.js**: chat UI returning tool-calls; opens NG state links.
- **Data layer**
  - Volumes in S3 (**precomputed**); **CloudVolume** for sampling (stubbed → real).
- **Neuroglancer hosting**
  - MVP: public NG host via **state URLs**.
  - v1: **same-origin** NG build for reliable embed + postMessage/state sync.

## Repo structure (current)
```
backend/
  main.py                 # FastAPI app & tool endpoints
  models.py               # Pydantic schemas (Vec3, SetView, ...)
  tools/
    neuroglancer_state.py # state helpers (set_view, set_lut, add_annotations, to_url)
    io.py                 # CSV ingest (top_n_rois)
    plots.py              # histogram sampling (stub)
  adapters/
    llm.py                # tool-calling adapter
  storage/
    states.py             # in-memory state persistence
panel/
  panel_app.py            # ChatInterface + panel-neuroglancer
frontend/
  app/
    page.tsx             # minimal chat page
    api/chat/route.ts    # proxy to /agent/chat
```

## Data flow (prompt → view)
1. **UI** sends user text → **POST** `/agent/chat`.
2. **LLM** responds with `tool_calls`.
3. UI (or server helper) **executes tools** in order via `/tools/*`.
4. UI calls **`/tools/state_save`** → receives **Neuroglancer URL**.
5. UI shows the URL (open in a tab) or sets `viewer.source` (Panel embed).

## Tool surface (HTTP endpoints)
- `POST /tools/ng_set_view` → center/zoom/orientation.
- `POST /tools/ng_set_lut` → LUT range per image layer.
- `POST /tools/ng_annotations_add` → add points/boxes/ellipsoids.
- `POST /tools/data_plot_histogram` → returns histogram bins/edges.
- `POST /tools/data_ingest_csv_rois` → returns canonical ROI table (top‑N).
- `POST /tools/state_save` → returns `{ sid, url }` for the current state.

## Current features
- Prompt → **navigate**, **zoom to fit**, **toggle/add annotations**, **set LUT**.
- **CSV ingest** stub: compute top‑20 ROIs and (optionally) create annotation layer.
- **Histogram** stub: random sampling; endpoint + return shape defined.
- **Panel app** with **ChatInterface** driving the backend and updating an embedded NG viewer.
- **React** minimal chat that returns tool-calls (exec orchestration TBD on client/server).

## Planned (near‑term)
- Real **CloudVolume** sampling (ROI support, multiscale); caching.
- Layer registry + validation; clearer shader/value-range handling by layer type.
- **ROI cycling**: generate per‑ROI state links & next/prev.
- Persist states per user/session (**Postgres/Redis**); later a **shared state store**.
- Same-origin NG hosting + **postMessage** bridge for bidirectional sync.
- Auth: JWT/OIDC; S3 access via signed URLs/STS.
- Plots beyond histograms (per‑segment stats, ROI intensity, QC panels).
- Observability: tracing (Langfuse/OTel), rate limits, retries.

## Ops / environment
- **Python** managed with **uv** (`uv venv`, `uv add`, `uv run`).
- Key env vars: `OPENAI_API_KEY`, `NEUROGLANCER_BASE`, `S3_BUCKET` (see MVP draft).
- Dev ports: FastAPI **:8000**, Panel **:8006**, Next.js **:3000**.
- CORS for dev: allow `localhost:3000`, `localhost/127.0.0.1:8006`.

## Run (quick)
- **Backend**: `uv run uvicorn backend.main:app --reload --port 8000`
- **Panel**: `BACKEND=http://127.0.0.1:8000 uv run python -m panel serve panel/panel_app.py --port 8006 --address 127.0.0.1 --allow-websocket-origin=127.0.0.1:8006 --allow-websocket-origin=localhost:8006`
- **Next.js** (optional): `npm run dev` (proxy to `/agent/chat`).

## Risks & mitigations
- **Cross-origin embed**: use **same-origin** NG to avoid CSP/frame and control limits.
- **TB-scale data**: sample at lower mip levels; limit voxel reads; cache.
- **Windows policy** (org machines): prefer system Python; avoid `%APPDATA%` executables.

## Open questions
- Exact **CSV schema** for ROIs/annotations (columns, coordinate frames).
- Target **auth** provider and roles (viewer/editor/admin).
- Priority of **Panel vs React** for the production UI.

