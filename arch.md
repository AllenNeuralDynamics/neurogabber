# Neurogabber — Architecture (Enhanced MVP)

Concise overview of the current repo, data flow, in‑memory data/memory model, and roadmap. Updated after adding ephemeral CSV upload support, dataframe tools (Polars), and conversational memory.

## Goal
Chat-driven navigation of massive neuroimaging data in **Neuroglancer** plus lightweight in-session analysis of user-supplied tabular data (e.g., ROIs CSV). Start with **state links**, move toward **same-origin embedding**.

## Components
### Backend (FastAPI)
* Tool endpoints mutate Neuroglancer **state JSON**, compute plots, ingest & transform CSV data.
* LLM adapter for **tool-calling** (OpenAI-compatible) — custom lightweight layer (no LangChain yet) with explicit tool schema list.
* In‑memory stores:
  * `CURRENT_STATE` (viewer state JSON)
  * `DataMemory` — uploaded CSVs + derived summary tables (Polars DataFrames) by short IDs
  * `InteractionMemory` — rolling window of recent exchanges (trimmed by count and total chars)

### Frontends
* **Panel**: `ChatInterface` + `panel-neuroglancer` widget; drag‑and‑drop CSV upload; tables of uploaded files & summaries; helper prompt button; conditional auto-load of new Neuroglancer state links.
* **React/Next.js**: minimal chat prototype (execution orchestration pattern shared).

### Data layer
* Volumes / imagery: S3 **precomputed**; **CloudVolume** calls still stubbed (will power histogram & ROI queries).

### Neuroglancer hosting
* MVP: remote/public NG host via state URLs.
* v1: same-origin NG bundle for stable embed + bidirectional sync (`postMessage`).

### Memory Layer
* Data context = summary of uploaded files (name, size, row/column counts, first few column names) + derived summaries.
* Interaction memory = compact joined strings ("User: ...", "Assistant: ...").
* Injected each request as system messages: system prompt, state summary, data context.
* Truncation ensures bounded prompt size (configurable caps per list/type).

## Repo structure (current)
```
backend/
  main.py                 # FastAPI app, tool & data endpoints, prompt augmentation
  models.py               # Pydantic schemas (Vec3, SetView, ...)
  tools/
    neuroglancer_state.py # state helpers (set_view, set_lut, add_annotations, to_url)
    io.py                 # CSV ingest (top_n_rois)
    plots.py              # histogram sampling (stub)
  adapters/
    llm.py                # tool-calling adapter (system prompt + tool schemas)
  storage/
    states.py             # in-memory NG state persistence
    data.py               # DataMemory (uploads/summaries) & InteractionMemory
panel/
  panel_app.py            # ChatInterface + upload UI + embedded Neuroglancer
frontend/
  app/
    page.tsx              # minimal chat page
    api/chat/route.ts     # proxy to /agent/chat
tests/
  test_llm_tools.py       # validates exposed tool names
  test_data_tools.py      # covers upload, preview, describe, select flows
```

## Data flow (prompt → view + data)
1. UI sends user text → `POST /agent/chat`.
2. Backend builds system preface messages:
   * Core system guidance.
   * Neuroglancer state summary (layers, layout, position).
   * Data context block (uploaded files + summaries + recent interaction memory snapshot).
3. Backend performs iterative tool execution loop (up to 3 passes):
  * Model proposes tool calls.
  * Server executes each tool (Polars ops, state mutators, etc.).
  * Tool outputs are truncated JSON strings appended as `role=tool` messages.
  * Model is called again until no further tool calls.
4. Final assistant message plus `mutated` flag and (if any mutation) `state_link` object `{url, masked_markdown}` returned to client.
5. Panel displays answer; if `mutated` and auto-load enabled it loads the returned Neuroglancer URL.
6. CSV uploads: Panel posts each file to `/upload_file`, then refreshes file & summary tables via list endpoints.
7. CSV uploads: Panel posts each file to `/upload_file`, then refreshes file & summary tables via list endpoints.
8. Persistence only when user explicitly asks (`/tools/state_save`).

### Mermaid: Chat + Data + Memory Flow

```mermaid
flowchart TD
  subgraph Client[Panel Client]
    U[User Prompt]
    ChatUI[ChatInterface]
    Upload[CSV Drag & Drop]
    Viewer[Neuroglancer Widget]
    FilesTable[Files Table]
    SummariesTable[Summaries Table]
  end

  subgraph Backend[FastAPI Backend]
    ChatEP[/POST /agent/chat/]
    Tools[/POST /tools/*/]
    StateLink[/POST /tools/ng_state_link/]
    UploadEP[/POST /upload_file/]
    subgraph Memory[In‑Memory Stores]
      CurrentState[(CURRENT_STATE)]
      DataMem[(DataMemory\n(Polars DFs+Summaries))]
      InterMem[(InteractionMemory)]
    end
    LLM[LLM Adapter\n(OpenAI chat+tools)]
    Executor[Iterative Tool Loop]
  end

  U --> ChatUI --> ChatEP
  Upload --> UploadEP --> DataMem
  ChatEP -->|Augment prompt with| InterMem
  ChatEP -->|Augment prompt with| DataMem
  ChatEP -->|Augment prompt with| CurrentState
  ChatEP --> LLM -->|tool_calls| Executor --> Tools
  Executor -->|tool outputs (tool messages)| LLM
  Tools -->|mutate| CurrentState
  Tools -->|read/write| DataMem
  Tools -->|log interactions| InterMem
  Tools --> StateLink --> ChatUI
  ChatUI -->|if mutated & auto-load| Viewer
  UploadEP --> FilesTable
  UploadEP --> SummariesTable
  Tools --> DataMem --> SummariesTable
  DataMem --> FilesTable
  InterMem --> ChatEP
```

## Tool surface (HTTP endpoints)
Neuroglancer / visualization:
* `POST /tools/ng_set_view` — center/zoom/orientation (mutating)
* `POST /tools/ng_set_lut` — LUT range (mutating)
* `POST /tools/ng_annotations_add` — add annotations (mutating)
* `POST /tools/ng_state_summary` — structured snapshot (read-only)
* `POST /tools/ng_state_link` — URL + masked markdown (read-only)
* `POST /tools/state_save` — persist snapshot (explicit)
* `POST /tools/state_load` / `POST /tools/demo_load` — load link (mutating)

Data (Polars):
* `POST /upload_file` — multipart CSV upload (validated, size capped)
* `POST /tools/data_list_files` — list uploaded file metadata
* `POST /tools/data_preview` — first N rows
* `POST /tools/data_info` — rows/cols, columns, dtypes, head sample
* `POST /tools/data_describe` — numeric stats (stored as summary)
* `POST /tools/data_select` — column subset + simple filters (stores preview summary)
* `POST /tools/data_list_summaries` — list derived tables
* `POST /tools/data_ingest_csv_rois` — legacy ROI ingest (top‑N)
* `POST /tools/data_plot_histogram` — histogram (stub)

## Current features
* Prompt-driven navigation: set view, set LUT, add annotations.
* CSV drag & drop → in-memory Polars DataFrames with short IDs.
* Data tools: list, preview, describe, select, list summaries.
* Interaction memory: rolling context appended to system messages.
* Histogram + ROI ingest stubs.
* Server-side orchestration of multi-step tool calls + conditional NG auto-load.
* `data_info` tool for quick dataframe metadata used in reasoning.
* Masking of raw Neuroglancer URLs (backend + frontend fallback).

## Planned (near‑term)
* Real CloudVolume sampling (ROI support, multiscale) + caching.
* Layer registry, shader/value-range normalization, validation.
* ROI cycling / bookmarking flows.
* Session scoping & persistence for DataMemory (Redis/Postgres + temp object storage).
* Same-origin NG hosting + bidirectional messaging.
* Additional data tools: joins, stratified sampling, per-column value counts.
* Observability: tracing (OTel / Langfuse), structured tool logs, rate limits.
* Memory summarization / condensation (semantic compression) for long chats.

## Ops / environment
* Python managed with **uv** (`uv run`, `uv add`).
* Key env vars: `OPENAI_API_KEY`, `NEUROGLANCER_BASE`, `S3_BUCKET` (future), optional panel `BACKEND` override.
* Dev ports: FastAPI **:8000**, Panel **:8006**, Next.js **:3000**.
* CORS (dev): allow `localhost` origins for UI embedding.

## Run (quick)
* Backend: `uv run uvicorn backend.main:app --reload --port 8000`
* Panel: `BACKEND=http://127.0.0.1:8000 uv run python -m panel serve panel/panel_app.py --port 8006 --address 127.0.0.1 --allow-websocket-origin=127.0.0.1:8006 --allow-websocket-origin=localhost:8006`
* Next.js (optional): `npm run dev`

## Risks & mitigations
| Risk | Mitigation |
|------|------------|
| Global in-process DataMemory (no user scoping) | Introduce session/user keys; TTL or LRU eviction |
| Memory growth with many uploads | 20 MB/file cap + future eviction & lazy scan_csv |
| Prompt bloat from data/interaction context | Hard caps on counts + char trimming |
| Tool mis-selection by LLM | Explicit system rules; non-overlapping tool semantics |
| Cross-origin embed limitations | Same-origin NG bundle + message channel |
| Large CSV parse latency | Use `pl.scan_csv` + lazy operations when needed |
| Cloud volume egress cost | Mip-level sampling, ROI bounding, caching |

## Why not LangChain (yet)?
Current scope: small tool surface (<20), single round tool selection, explicit prompt assembly. A custom adapter keeps dependency / cognitive load low and debugging transparent. Re-evaluate when we need multi-step planning loops, tool parallelism, retrieval pipelines, or pluggable memory summarizers. Existing separation (one `TOOLS` list + system preface builder) makes migration straightforward later.

## Open questions
* CSV/ROI schema standardization (coordinate frame, units, metadata columns?)
* Session & auth model: per-user isolation vs collaborative sessions.
* Priority order for React feature parity.
* Strategy for summarizing or vectorizing historical interaction memory.
* Persistence / export of derived summaries (download endpoints?).

---
Last updated: after data tools & memory integration.

