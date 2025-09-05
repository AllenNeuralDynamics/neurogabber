import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), '.env'))

from fastapi import FastAPI, UploadFile, Body, Query
from .models import ChatRequest, SetView, SetLUT, AddAnnotations, HistogramReq, IngestCSV, SaveState
from .tools.neuroglancer_state import new_state, set_view as _set_view, set_lut as _set_lut, add_annotations as _add_ann, to_url, from_url
from .tools.plots import sample_voxels, histogram
from .tools.io import load_csv, top_n_rois
from .storage.states import save_state, load_state
from .adapters.llm import run_chat, SYSTEM_PROMPT

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# In-memory working state per session (MVP). Replace with DB keyed by user/session.
CURRENT_STATE = new_state()



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
    # Optionally also add an annotation layer from rows here
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


# @app.post("/agent/chat")
# def chat(req: ChatRequest):
#     # Pass-through to LLM; client will call tool endpoints when tool calls arrive
#     out = run_chat([m.model_dump() for m in req.messages])
#     return out

@app.post("/agent/chat")
def chat(req: ChatRequest):
    # Build augmented prompt with routing guidance + state summary
    state_summary = _summarize_state(CURRENT_STATE)
    preface = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": f"Current viewer state summary:\n{state_summary}"},
    ]
    logger.debug("Preface:\n%s", preface)
    logger.debug("State summary:\n%s", state_summary)
    out = run_chat(preface + [m.model_dump() for m in req.messages])
    logger.debug("LLM response:%s", out)
    logger.info("CHATTER HERE") # debug
    # Post-process assistant message content to mask raw Neuroglancer URLs.
    try:
        choices = out.get("choices") or []
   
        for ch in choices:
            msg = ch.get("message") or {}
            logger.debug(msg.get("role"))
            if msg.get("role") == "assistant":
                content = msg.get("content")
                tool_calls = msg.get("tool_calls") or []
                # Synthesize content if missing and we have tool calls
                if (content is None or (isinstance(content, str) and not content.strip())) and tool_calls:
                    msg["content"] = _synthesize_tool_call_message(tool_calls)
                # Mask any raw NG URLs in (original or synthesized) content
                if isinstance(msg.get("content"), str):
                    msg["content"] = _mask_ng_urls(msg["content"])
    except Exception:  # pragma: no cover (defensive)
        logger.exception("Failed masking Neuroglancer URLs")
    return out


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