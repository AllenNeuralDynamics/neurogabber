import json, os, uuid
from typing import Dict
from urllib.parse import quote, unquote


#NEURO_BASE = os.getenv("NEUROGLANCER_BASE", "https://neuroglancer.github.io")
NEURO_BASE = os.getenv("NEUROGLANCER_BASE", "https://neuroglancer-demo.appspot.com")


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


def from_url(url_or_fragment: str) -> Dict:
    """Parse a Neuroglancer URL (or just its hash fragment) into a state dict.

    Accepts any of:
    - Full URL like https://host/#!%7B...%7D
    - Full URL like https://host/#%7B...%7D
    - Just the fragment starting with '#', '#!' or the percent-encoded JSON itself
    - A raw JSON string (for robustness)
    """
    s = url_or_fragment.strip()
    # Extract the fragment if a full URL was provided
    if '#' in s:
        s = s.split('#', 1)[1]
    # Drop the optional leading '!'
    if s.startswith('!'):
        s = s[1:]
    # If this looks like percent-encoded JSON, unquote it
    try:
        decoded = unquote(s)
        # If unquoting didn't change it and it's already JSON, keep as-is
        candidate = decoded if decoded else s
        return json.loads(candidate)
    except Exception:
        # Last resort: maybe it's already a JSON string without quoting
        return json.loads(s)