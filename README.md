# neurogabber

[![License](https://img.shields.io/badge/license-MIT-brightgreen)](LICENSE)
![Code Style](https://img.shields.io/badge/code%20style-black-black)
[![semantic-release: angular](https://img.shields.io/badge/semantic--release-angular-e10079?logo=semantic-release)](https://github.com/semantic-release/semantic-release)
![Interrogate](https://img.shields.io/badge/interrogate-13.7%25-red)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![Python](https://img.shields.io/badge/python->=3.10-blue?logo=python)

## To run
+ backend: `uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`
+ frontend:
    + `$env:BACKEND = "http://127.0.0.1:8000"`
    + panel: `uv run python -m panel serve panel\panel_app.py --autoreload --port 8006 --address 127.0.0.1`
    + panel chat:
        ```bash
            $env:BACKEND = "http://127.0.0.1:8000"
            uv run python -m panel serve panel\panel_app.py --autoreload --port 8006 --address 127.0.0.1 --allow-websocket-origin=127.0.0.1:8006 --allow-websocket-origin=localhost:8006
        ```
    + open browser: http://localhost:8006

+ tests
    + `uv run -m coverage run -m pytest`
    + `uv run -m coverage report`

## Level of Support
Please indicate a level of support:
 - [ ] Supported: We are releasing this code to the public as a tool we expect others to use. Issues are welcomed, and we expect to address them promptly; pull requests will be vetted by our staff before inclusion.
 - [ ] Occasional updates: We are planning on occasional updating this tool with no fixed schedule. Community involvement is encouraged through both issues and pull requests.
 - [ ] Unsupported: We are not currently supporting this code, but simply releasing it to the community AS IS but are not able to provide any guarantees of support. The community is welcome to submit issues, but you should not expect an active response.

## Release Status
GitHub's tags and Release features can be used to indicate a Release status.

 - Stable: v1.0.0 and above. Ready for production.
 - Beta:  v0.x.x or indicated in the tag. Ready for beta testers and early adopters.
 - Alpha: v0.x.x or indicated in the tag. Still in early development.

## Installation
To use the software, in the root directory, run
```bash
pip install -e .
```

To develop the code, run
```bash
pip install -e . --group dev
```
Note: --group flag is available only in pip versions >=25.1

Alternatively, if using `uv`, run
```bash
uv sync
```

## Features

* Chat-driven Neuroglancer view manipulation via tool calls
* Iterative server-side tool execution loop (model -> tools -> model) for grounded answers
* FastAPI backend with pluggable data & visualization tools (Polars-based dataframe utilities)
* Panel-based UI prototype embedding a Neuroglancer viewer
* Full Neuroglancer state retention (layers, transforms, shader controls, layout) with deterministic URL round‑trip
* Optional auto-load toggle for applying newly generated Neuroglancer views
* `data_info` tool for dataframe metadata (shape, columns, dtypes, sample rows)
* `data_sample` tool for quick unbiased random row sampling (optional seed)
* `data_ng_views_table` tool to generate ranked multi-view Neuroglancer links (top N by a metric)
* Tool execution trace returned with each chat + debug endpoint for recent full traces

## Neuroglancer State Handling

The backend now preserves the *entire* Neuroglancer JSON state parsed from any loaded URL (including complex multi-panel layouts, per-layer transforms, shader code/controls, etc.). Tool mutators (`ng_set_view`, `ng_set_lut`, `ng_annotations_add`) only touch the specific fields they need without pruning unrelated keys. Position updates preserve a 4th temporal component when present. A `zoom == "fit"` request recenters without altering the existing layout, helping maintain multi-panel arrangements.

Serialization (`state_save`) uses deterministic JSON ordering so round‑trip tests can assert `from_url(to_url(state)) == state` for typical viewer states.

## Auto‑Load Toggle

In the Panel UI a Settings card provides an "Auto-load view" checkbox (default ON). When disabled, generated URLs are shown in chat and placed in a read‑only "Latest NG URL" field; click "Open latest link" to manually apply. This affords manual inspection or batching of tool operations before updating the viewer.

## Sampling & Multi-View Workflow

Common exploration pattern:
1. Upload CSV of ROIs / detections.
2. Ask: "Show me a random sample of 5 rows from file XYZ" -> invokes `data_sample`.
3. Ask: "Create Neuroglancer views for the top 8 by mean_intensity" -> model calls `data_ng_views_table` with `sort_by=mean_intensity` and `top_n=8`.
4. Panel displays a table of rows (id + metric + masked link); the first view auto-loads (if enabled). Clicking other rows navigates without requiring new LLM calls.

`data_ng_views_table` returns both raw `link` and `masked_link` so advanced clients can decide how to render. A summary table (kind `ng_views`) is stored allowing follow-up queries like: "Filter the previous views summary where mean_intensity > 0.8 then regenerate views".

## Tool Trace

Each chat response includes a concise `tool_trace` listing executed tools, argument keys, and result keys. For deeper debugging hit `/debug/tool_trace?n=5` to retrieve recent full traces (in-memory, bounded). This aids reproducibility and performance analysis without inflating LLM context.
