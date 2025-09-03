import os, json
from typing import List, Dict
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Define available tools (schemas must match your Pydantic models)
TOOLS = [
  {
    "type": "function",
    "function": {
      "name": "ng.set_view",
      "description": "Set camera center/zoom/orientation",
      "parameters": {
        "type": "object",
        "properties": {
          "center": {"type":"object","properties":{"x":{"type":"number"},"y":{"type":"number"},"z":{"type":"number"}},"required":["x","y","z"]},
          "zoom": {"oneOf":[{"type":"number"},{"type":"string","enum":["fit"]}]},
          "orientation": {"type":"string","enum":["xy","yz","xz","3d"]}
        },
        "required": ["center"]
      }
    }
  },
  {
    "type":"function",
    "function": {
      "name":"ng.set_lut",
      "description":"Set value range for an image layer",
      "parameters": {
        "type":"object",
        "properties": {"layer":{"type":"string"},"vmin":{"type":"number"},"vmax":{"type":"number"}},
        "required":["layer","vmin","vmax"]
      }
    }
  },
  {
    "type":"function",
    "function": {
      "name":"ng.annotations.add",
      "description":"Add annotations to a layer",
      "parameters": {"type":"object","properties": {"layer":{"type":"string"},"items":{"type":"array"}},"required":["layer","items"]}
    }
  },
  {
    "type":"function",
    "function": {
      "name":"data.plot.histogram",
      "description":"Compute intensity histogram from layer/roi",
      "parameters": {"type":"object","properties": {"layer":{"type":"string"},"roi":{"type":"object"}},"required":["layer"]}
    }
  },
  {
    "type":"function",
    "function": {
      "name":"data.ingest.csv_rois",
      "description":"Load CSV of ROIs and build canonical table",
      "parameters": {"type":"object","properties": {"file_id":{"type":"string"}},"required":["file_id"]}
    }
  },
  {"type":"function","function": {"name":"state.save","description":"Save and return NG state URL","parameters":{"type":"object","properties":{}}}}
]


def run_chat(messages: List[Dict]) -> Dict:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",  # any tool-capable model
        messages=messages,
        tools=TOOLS,
        tool_choice="auto"
    )
    return resp.model_dump()