import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), '.env'))

from fastapi import FastAPI, UploadFile, Body, Query, File
from .models import ChatRequest, SetView, SetLUT, AddAnnotations, HistogramReq, IngestCSV, SaveState
from .tools.neuroglancer_state import new_state, set_view as _set_view, set_lut as _set_lut, add_annotations as _add_ann, to_url, from_url
from .tools.plots import sample_voxels, histogram
from .tools.io import load_csv, top_n_rois
from .storage.states import save_state, load_state
from .adapters.llm import run_chat, SYSTEM_PROMPT
from .tools.constants import is_mutating_tool
from .storage.data import DataMemory, InteractionMemory
import polars as pl

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# In-memory working state per session (MVP). Replace with DB keyed by user/session.
CURRENT_STATE = new_state()
DATA_MEMORY = DataMemory()
INTERACTION_MEMORY = InteractionMemory()
_TRACE_HISTORY: list[dict] = []  # store recent full traces (in-memory, capped)
_TRACE_HISTORY_MAX = 50


@app.post("/tools/ng_set_view")
def t_set_view(args: SetView):
    global CURRENT_STATE
    CURRENT_STATE = _set_view(CURRENT_STATE, args.center.model_dump(), args.zoom, args.orientation)
    return {"ok": True}

@app.post("/tools/ng_set_lut")
def t_set_lut(args: SetLUT):
    global CURRENT_STATE
    CURRENT_STATE = _set_lut(CURRENT_STATE, args.layer, args.vmin, args.vmax)
    return {"ok": True}

@app.post("/tools/ng_annotations_add")
def t_add_annotations(args: AddAnnotations):
    global CURRENT_STATE
    items = []
    for a in args.items:
        if a.type == "point":
            items.append({"point": [a.center.x, a.center.y, a.center.z], "id": a.id or None})
        elif a.type == "box":
            items.append({"type":"box", "point": [a.center.x, a.center.y, a.center.z],
                          "size": [a.size.x, a.size.y, a.size.z], "id": a.id or None})
        elif a.type == "ellipsoid":
            items.append({"type":"ellipsoid", "center": [a.center.x, a.center.y, a.center.z],
                          "radii": [a.size.x/2, a.size.y/2, a.size.z/2], "id": a.id or None})
    CURRENT_STATE = _add_ann(CURRENT_STATE, args.layer, items)
    return {"ok": True}

@app.post("/tools/data_plot_histogram")
def t_hist(args: HistogramReq):
    vox = sample_voxels(args.layer, args.roi)
    hist, edges = histogram(vox)
    return {"hist": hist.tolist(), "edges": edges.tolist()}

@app.post("/tools/data_ingest_csv_rois")
def t_csv(args: IngestCSV):
    df = load_csv(args.file_id)
    rows = top_n_rois(df)
    return {"rows": rows}

@app.post("/tools/state_save")
def t_save_state(_: SaveState, mask: bool = Query(False, description="Return masked markdown link label instead of raw URL")):
    """Persist current state and return its ID and URL.

    If mask=true, also include 'masked_markdown' with a concise hyperlink label.
    We do masking here (where state is definitively updated) instead of during
    synthetic assistant message generation to avoid presenting stale links.
    """
    sid = save_state(CURRENT_STATE)
    url = to_url(CURRENT_STATE)
    if mask:
        masked = _mask_ng_urls(url)
        # If masking logic chooses not to transform (unlikely since it's a NG URL), fall back to manual label.
        if masked == url:
            masked = f"[Updated Neuroglancer view]({url})"
        return {"sid": sid, "url": url, "masked_markdown": masked}
    return {"sid": sid, "url": url}


@app.post("/tools/state_load")
def t_state_load(link: str = Body(..., embed=True)):
    """Load state from a Neuroglancer URL or fragment and set CURRENT_STATE."""
    global CURRENT_STATE
    try:
        CURRENT_STATE = from_url(link)
        return {"ok": True}
    except Exception as e:
        logger.exception("Failed to load state from link")
        return {"ok": False, "error": str(e)}


@app.post("/tools/demo_load")
def t_demo_load(link: str = Body(..., embed=True)):
    """Convenience: same as state_load, named for demos."""
    return t_state_load(link)

# TODO
#Optional (alternative path): if you prefer “read-only” to still be tool-based, 
#add a tiny GET tool like ng_list_layers to the toolset. But since you asked for “no tool” for 
#that query, the state-summary + system prompt approach above fits better.
def _summarize_state(state: dict) -> str:
    # Keep it short and deterministic. Expand as needed later.
    layers = state.get("layers", [])
    lines = []
    lines.append(f"Layout: {state.get('layout','xy')}")
    pos = state.get("position", [0,0,0])
    lines.append(f"Position: {pos}")
    if layers:
        lines.append("Layers:")
        for L in layers:
            name = L.get("name","(unnamed)")
            ltype = L.get("type","unknown")
            lines.append(f"- {name} ({ltype})")
    else:
        lines.append("Layers: (none)")
    return "\n".join(lines)


def _data_context_block(max_files: int = 10, max_summaries: int = 10) -> str:
    files = DATA_MEMORY.list_files()[:max_files]
    sums = DATA_MEMORY.list_summaries()[:max_summaries]
    parts = ["Data context:"]
    if files:
        parts.append("Files:")
        for f in files:
            parts.append(f"- {f['file_id']} {f['name']} rows={f['n_rows']} cols={f['n_cols']} cols={f['columns'][:6]}...")
    else:
        parts.append("Files: (none)")
    if sums:
        parts.append("Summaries:")
        for s in sums:
            parts.append(f"- {s['summary_id']} from {s['source_file_id']} kind={s['kind']} rows={s['n_rows']} cols={s['n_cols']}")
    else:
        parts.append("Summaries: (none)")
    mem = INTERACTION_MEMORY.recall()
    if mem:
        parts.append(f"Recent interactions: {mem}")
    return "\n".join(parts)


@app.post("/agent/chat")
def chat(req: ChatRequest):
    """Iterative chat with server-side tool execution.

    Loop:
      model -> (tool calls?) -> execute tools -> append tool messages -> model ...
    Stops when model returns no tool calls or max iterations reached.
    Returns the final model response (with intermediate tool messages NOT included
    to keep client payload small) plus optional `state_link` if a mutating tool ran.
    """
    state_summary = _summarize_state(CURRENT_STATE)
    data_context = _data_context_block()
    base_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Current viewer state summary:\n{state_summary}"},
        {"role": "system", "content": data_context},
    ]
    conversation = base_messages + [m.model_dump() for m in req.messages]
    max_iters = 3
    overall_mutated = False
    tool_execution_records = []  # truncated records for response
    full_trace_steps = []  # full detail trace retained server-side

    for iteration in range(max_iters):
        out = run_chat(conversation)
        choices = out.get("choices") or []
        if not choices:
            break
        msg = choices[0].get("message") or {}
        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content")
        # If there are no tool calls we're done
        if not tool_calls:
            # Final masking before return
            if isinstance(content, str):
                msg["content"] = _mask_ng_urls(content)
            conversation.append(msg)
            break

        # Synthesize placeholder content if empty
        if (content is None or (isinstance(content, str) and not content.strip())) and tool_calls:
            msg["content"] = _synthesize_tool_call_message(tool_calls)
        conversation.append(msg)  # assistant with tool calls

        # Execute each tool call
        import json as _json
        for tc in tool_calls:
            fn = (tc.get("function") or {}).get("name")
            raw_args = (tc.get("function") or {}).get("arguments") or "{}"
            try:
                args = _json.loads(raw_args)
            except Exception:
                args = {}
            result_payload = _execute_tool_by_name(fn, args)
            if is_mutating_tool(fn):
                overall_mutated = True
            # Truncate large structures for token safety
            truncated = _truncate_tool_output(result_payload)
            # Store minimal trace info (avoid huge payloads)
            tool_execution_records.append({
                "tool": fn,
                "args": {k: (v if isinstance(v, (int, float, str, bool)) else str(v)[:120]) for k, v in (args or {}).items()},
                "result_keys": list(result_payload.keys())[:12],
            })
            full_trace_steps.append({
                "tool": fn,
                "raw_args": args,
                "full_result": result_payload,
            })
            conversation.append({
                "role": "tool",
                "tool_call_id": tc.get("id"),
                "name": fn,
                "content": truncated,
            })
        # Continue loop for next model reasoning pass
    # After loop, optionally append state link if mutated and user likely wants it
    state_link_block = None
    if overall_mutated:
        try:
            url = to_url(CURRENT_STATE)
            masked = _mask_ng_urls(url)
            state_link_block = {"url": url, "masked_markdown": masked}
        except Exception:  # pragma: no cover
            logger.exception("Failed generating state link")

    # Update interaction memory (store last user + final assistant short snippet)
    try:
        user_last = next((m.content for m in reversed(req.messages) if m.role == "user"), None)
        if user_last:
            INTERACTION_MEMORY.remember(f"User:{(user_last or '')[:120]}")
        # Find last assistant message in conversation
        for cm in reversed(conversation):
            if cm.get("role") == "assistant" and cm.get("content"):
                INTERACTION_MEMORY.remember(f"Assistant:{cm['content'][:300]}")
                break
    except Exception:  # pragma: no cover
        logger.exception("Failed to update interaction memory")

    # Prepare final response shaped like OpenAI response with extra fields
    final_assistant = None
    for cm in reversed(conversation):
        if cm.get("role") == "assistant":
            final_assistant = cm
            break
    if final_assistant is None:
        final_assistant = {"role": "assistant", "content": "(no response)"}

    # Persist full trace (bounded)
    try:
        _TRACE_HISTORY.append({
            "mutated": overall_mutated,
            "final_message": final_assistant,
            "steps": full_trace_steps,
        })
        if len(_TRACE_HISTORY) > _TRACE_HISTORY_MAX:
            del _TRACE_HISTORY[:-_TRACE_HISTORY_MAX]
    except Exception:  # pragma: no cover
        logger.exception("Failed storing trace history")

    return {
        "model": "iterative",
        "choices": [{"index": 0, "message": final_assistant, "finish_reason": "stop"}],
        "usage": {},
        "mutated": overall_mutated,
        "state_link": state_link_block,
        "tool_trace": tool_execution_records,
    }


@app.get("/debug/tool_trace")
def debug_tool_trace(n: int = 1):
    """Return the last n full tool traces (untruncated)."""
    n = max(1, min(n, 10))
    return {"traces": _TRACE_HISTORY[-n:]}


def _truncate_tool_output(obj, max_chars: int = 4000):
    import json as _json
    try:
        s = _json.dumps(obj)[:max_chars]
        return s
    except Exception:
        return str(obj)[:max_chars]


def _execute_tool_by_name(name: str, args: dict):
    """Dispatcher for internal tool execution (server-side)."""
    # Directly call the endpoint functions; replicate FastAPI parameter handling
    try:
        if name == "ng_set_view":
            from .models import SetView
            return t_set_view(SetView(**args))
        if name == "ng_set_lut":
            from .models import SetLUT
            return t_set_lut(SetLUT(**args))
        if name == "ng_annotations_add":
            from .models import AddAnnotations
            return t_add_annotations(AddAnnotations(**args))
        if name == "data_plot_histogram":
            from .models import HistogramReq
            return t_hist(HistogramReq(**args))
        if name == "data_ingest_csv_rois":
            from .models import IngestCSV
            return t_csv(IngestCSV(**args))
        if name == "state_save":
            from .models import SaveState
            return t_save_state(SaveState())
        if name == "state_load":
            link = args.get("link")
            return t_state_load(link)
        if name == "ng_state_summary":
            detail = args.get("detail", "standard")
            return t_state_summary(detail)
        if name == "ng_state_link":
            return t_state_link()
        if name == "data_list_files":
            return t_data_list_files()
        if name == "data_preview":
            return t_data_preview(**args)
        if name == "data_describe":
            return t_data_describe(**args)
        if name == "data_select":
            return t_data_select(**args)
        if name == "data_list_summaries":
            return t_data_list_summaries()
        if name == "data_info":
            return t_data_info(**args)
        if name == "data_sample":
            return t_data_sample(**args)
    except Exception as e:  # pragma: no cover
        logger.exception("Tool execution error")
        return {"error": str(e)}
    return {"error": f"Unknown tool {name}"}


def _mask_ng_urls(text: str) -> str:
    """Replace full Neuroglancer URLs with a concise markdown hyperlink.

    Each distinct URL is collapsed to the label 'Updated Neuroglancer view'. If
    multiple different URLs appear, they will receive a numeric suffix to
    differentiate: 'Updated Neuroglancer view (2)', etc.
    """
    logger.info(f"{text}")
    import re
    url_pattern = re.compile(r"https?://[^\s)]+")
    candidates = url_pattern.findall(text)
    urls = [u for u in candidates if 'neuroglancer' in u]
    # Also detect tokens missing scheme but containing neuroglancer + fragment (#!%7B)
    if 'neuroglancer' in text and '#!%7B' in text:
        tokens = re.split(r"\s+", text)
        for tok in tokens:
            if 'neuroglancer' in tok and '#!%7B' in tok and 'http' not in tok:
                urls.append(tok)
    if not urls:
        return text
    ordered = []
    seen = set()
    for u in urls:
        if u not in seen:
            ordered.append(u)
            seen.add(u)
    label_map = {}
    for idx, u in enumerate(ordered):
        base = "Updated Neuroglancer view" if idx == 0 else f"Updated Neuroglancer view ({idx+1})"
        label_map[u] = f"[{base}]({u})"
    for raw_url, repl in label_map.items():
        text = text.replace(raw_url, repl)
    return text


@app.post("/tools/ng_state_link")
def t_state_link():
    """Return current state link and masked markdown without persisting a new save id."""
    url = to_url(CURRENT_STATE)
    masked = _mask_ng_urls(url)
    if masked == url:
        masked = f"[Updated Neuroglancer view]({url})"
    return {"url": url, "masked_markdown": masked}


def _synthesize_tool_call_message(tool_calls) -> str:
    """Create a concise assistant message summarizing tool calls (no link).

    We intentionally do NOT embed a Neuroglancer state URL here because at this
    point the client has not yet executed the tool calls; embedding a link
    would show a stale pre-mutation state. The client can separately call
    /tools/state_save (optionally with masking) AFTER applying tools to obtain
    the authoritative updated link.
    """
    try:
        names = []
        for tc in tool_calls:
            fn = (tc.get("function") or {}).get("name") or tc.get("type") or "tool"
            names.append(fn)
        tool_list = ", ".join(names)
        return f"Applied tools: {tool_list}."
    except Exception:
        return "Applied tools."  # fallback


def summarize_state_struct(state: dict, detail: str = "standard") -> dict:
    """Produce a structured summary for LLM inspection.

    detail levels:
      - minimal: only layer name & type
      - standard: adds counts & ranges
      - full: adds shader length and source kinds
    """
    layers_out = []
    for L in state.get("layers", []):
        base = {"name": L.get("name"), "type": L.get("type")}
        ltype = L.get("type")
        if detail in ("standard", "full"):
            if ltype == "image":
                src = L.get("source")
                if isinstance(src, list):
                    base["num_sources"] = len(src)
                    kinds = []
                    for s in src:
                        if isinstance(s, dict):
                            url = s.get("url", "")
                            if "://" in url:
                                kinds.append(url.split("://",1)[0])
                    if kinds:
                        base["source_kinds"] = sorted(set(kinds))
                rng = (L.get("shaderControls") or {}).get("normalized", {}).get("range")
                if rng:
                    base["normalized_range"] = rng
            elif ltype == "annotation":
                anns = (L.get("source") or {}).get("annotations") or []
                base["annotation_count"] = len(anns)
        if detail == "full":
            shader = L.get("shader")
            if shader:
                base["shader_len"] = len(shader)
        layers_out.append(base)

    annotation_layers = []
    for L in state.get("layers", []):
        if L.get("type") == "annotation":
            anns = (L.get("source") or {}).get("annotations") or []
            types = set()
            for a in anns:
                t = a.get("type") or ("point" if "point" in a else None)
                if t:
                    types.add(t)
            annotation_layers.append({
                "name": L.get("name"),
                "count": len(anns),
                "types": sorted(types)
            })

    return {
        "layout": state.get("layout"),
        "position": state.get("position"),
        "dimensions": state.get("dimensions"),
        "layers": layers_out,
        "annotation_layers": annotation_layers,
        "flags": {
            "showAxisLines": state.get("showAxisLines"),
            "showScaleBar": state.get("showScaleBar"),
        },
        "version": 1,
        "detail": detail,
    }


@app.post("/tools/ng_state_summary")
def t_state_summary(detail: str = Body("standard", embed=True)):
    return summarize_state_struct(CURRENT_STATE, detail=detail)

# ------------------- Data tool endpoints -------------------

@app.post("/upload_file")
async def upload_file(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        meta = DATA_MEMORY.add_file(file.filename, raw)
        return {"ok": True, "file": meta}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.post("/tools/data_list_files")
def t_data_list_files():
    return {"files": DATA_MEMORY.list_files()}

@app.post("/tools/data_info")
def t_data_info(file_id: str = Body(..., embed=True), sample_rows: int = Body(5, embed=True)):
    try:
        df = DATA_MEMORY.get_df(file_id)
        sample_rows = max(1, min(sample_rows, 20))
        sample = df.head(sample_rows).to_dicts()
        dtypes = {c: str(dt) for c, dt in zip(df.columns, df.dtypes)}
        return {
            "file_id": file_id,
            "n_rows": df.height,
            "n_cols": df.width,
            "columns": df.columns,
            "dtypes": dtypes,
            "sample": sample,
        }
    except Exception as e:
        return {"error": str(e)}

@app.post("/tools/data_preview")
def t_data_preview(file_id: str = Body(..., embed=True), n: int = Body(10, embed=True)):
    try:
        df = DATA_MEMORY.get_df(file_id)
        n = max(1, min(n, 100))
        return {"file_id": file_id, "rows": df.head(n).to_dicts(), "columns": df.columns}
    except Exception as e:
        return {"error": str(e)}

@app.post("/tools/data_describe")
def t_data_describe(file_id: str = Body(..., embed=True)):
    try:
        df = DATA_MEMORY.get_df(file_id)
        desc = df.describe()
        meta = DATA_MEMORY.add_summary(file_id, "describe", desc, note="numeric describe")
        return {"summary": meta, "rows": desc.to_dicts()}
    except Exception as e:
        return {"error": str(e)}

@app.post("/tools/data_select")
def t_data_select(
    file_id: str = Body(..., embed=True),
    columns: list[str] | None = Body(None, embed=True),
    filters: list[dict] | None = Body(None, embed=True),
    limit: int = Body(20, embed=True),
):
    try:
        df = DATA_MEMORY.get_df(file_id)
        if columns:
            missing = [c for c in columns if c not in df.columns]
            if missing:
                return {"error": f"Unknown columns: {missing}"}
            df = df.select(columns)
        if filters:
            exprs = []
            for f in filters:
                col = f.get("column")
                op = f.get("op")
                val = f.get("value")
                if col not in df.columns:
                    return {"error": f"Filter column not in dataframe: {col}"}
                col_expr = pl.col(col)
                if op == "==":
                    exprs.append(col_expr == val)
                elif op == "!=":
                    exprs.append(col_expr != val)
                elif op == ">":
                    exprs.append(col_expr > val)
                elif op == "<":
                    exprs.append(col_expr < val)
                elif op == ">=":
                    exprs.append(col_expr >= val)
                elif op == "<=":
                    exprs.append(col_expr <= val)
                else:
                    return {"error": f"Unsupported op {op}"}
            if exprs:
                import functools, operator
                combined = functools.reduce(operator.and_, exprs)
                df = df.filter(combined)
        limit = max(1, min(limit, 500))
        subset = df.head(limit)
        meta = DATA_MEMORY.add_summary(file_id, "select", subset, note="filtered/select preview")
        return {"summary": meta, "preview_rows": subset.to_dicts()}
    except Exception as e:
        return {"error": str(e)}

@app.post("/tools/data_list_summaries")
def t_data_list_summaries():
    return {"summaries": DATA_MEMORY.list_summaries()}


@app.post("/tools/data_sample")
def t_data_sample(
    file_id: str = Body(..., embed=True),
    n: int = Body(5, embed=True),
    seed: int | None = Body(None, embed=True),
    replace: bool = Body(False, embed=True),
):
    """Return a random sample of rows from a dataframe (without replacement by default).

    Parameters:
      file_id: ID of uploaded file
      n: number of rows to sample (default 5, bounded 1..1000)
      seed: optional integer seed for reproducibility (None => random)
      replace: sample with replacement (default False)
    """
    try:
        df = DATA_MEMORY.get_df(file_id)
        n = max(1, min(n, 1000))
        if not replace and n > df.height:
            n = df.height
        # polars sample: shuffle=True ensures random order even when n==height
        sampled = df.sample(n=n, with_replacement=replace, shuffle=True, seed=seed)
        return {
            "file_id": file_id,
            "requested": n,
            "returned": sampled.height,
            "with_replacement": replace,
            "seed": seed,
            "rows": sampled.to_dicts(),
            "columns": sampled.columns,
        }
    except KeyError:
        return {"error": f"Unknown file_id {file_id}"}
    except Exception as e:
        return {"error": str(e)}