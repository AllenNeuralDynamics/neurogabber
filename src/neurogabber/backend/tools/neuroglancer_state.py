import json, os, uuid
from typing import Dict
from urllib.parse import quote


NEURO_BASE = os.getenv("NEUROGLANCER_BASE", "https://neuroglancer.github.io")


# Minimal state object; extend with layers, shader params, annotations, etc.
def new_state() -> Dict:
    return {
    "dimensions": {"x": [1e-9, "m"], "y": [1e-9, "m"], "z": [1e-9, "m"]},
    "position": [0,0,0],
    "crossSectionScale": 1.0,
    "projectionScale": 1024,
    "layers": [],
    "layout": "xy"
    }


# Utility mutators
def set_view(state: Dict, center, zoom, orientation):
    state["position"] = [center["x"], center["y"], center["z"]]
    if zoom == "fit":
        state["crossSectionScale"] = 1.0 # placeholder; tune per dataset size
    else:
        state["crossSectionScale"] = float(zoom)
        state["layout"] = orientation
    return state


def set_lut(state: Dict, layer_name: str, vmin: float, vmax: float):
    for L in state.get("layers", []):
        if L.get("name") == layer_name:
            # Neuroglancer uses shaderControls / channel ranges depending on layer type
            L.setdefault("shaderControls", {})["normalizedRange"] = [vmin, vmax]
    return state


def add_annotations(state: Dict, layer: str, items):
    # Ensure annotation layer exists
    ann = next((L for L in state.get("layers", []) if L.get("type")=="annotation" and L.get("name")==layer), None)
    if not ann:
        ann = {"type":"annotation", "name":layer, "source":{"annotations":[]}}
        state["layers"].append(ann)
    # Always append new items
    ann["source"].setdefault("annotations", []).extend(items)
    return state


def to_url(state: Dict) -> str:
    # State is encoded in the URL hash; simplest path: json → urlencoded
    state_str = json.dumps(state, separators=(",", ":"))
    return f"{NEURO_BASE}#%7B{quote(state_str)[3:]}" # quick-and-dirty encoding