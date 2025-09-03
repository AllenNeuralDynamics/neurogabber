import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), '.env'))

from fastapi import FastAPI, UploadFile, Body
from .models import ChatRequest, SetView, SetLUT, AddAnnotations, HistogramReq, IngestCSV, SaveState
from .tools.neuroglancer_state import new_state, set_view as _set_view, set_lut as _set_lut, add_annotations as _add_ann, to_url
from .tools.plots import sample_voxels, histogram
from .tools.io import load_csv, top_n_rois
from .storage.states import save_state, load_state
from .adapters.llm import run_chat

app = FastAPI()

# In-memory working state per session (MVP). Replace with DB keyed by user/session.
CURRENT_STATE = new_state()

@app.post("/agent/chat")
def chat(req: ChatRequest):
    # Pass-through to LLM; client will call tool endpoints when tool calls arrive
    out = run_chat([m.model_dump() for m in req.messages])
    return out

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
def t_save_state(_: SaveState):
    sid = save_state(CURRENT_STATE)
    url = to_url(CURRENT_STATE)
    return {"sid": sid, "url": url}