import os, json
from typing import List, Dict
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """You are Neurogabber, a helpful assistant for Neuroglancer.
Decide whether to take action with tools or just answer:
- If the user asks for information you can answer from the provided 'Current viewer state summary' or general knowledge, respond directly with text. Do NOT call tools.
- If the user asks to change the view, layers, LUTs, or data, call the appropriate tool(s).
- If you need data not in the state summary (e.g., a computation), call a tool.
Always keep answers concise. If you call tools, you may include a brief explanation first."""

# Define available tools (schemas must match your Pydantic models)
TOOLS = [
  {
    "type": "function",
    "function": {
      "name": "ng_set_view",
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
      "name":"ng_set_lut",
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
      "name":"ng_annotations_add",
      "description":"Add annotations to a layer",
      "parameters": {
        "type": "object",
        "properties": {
          "layer": {"type": "string"},
          "items": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "id": {"type": "string"},
                "type": {"type": "string", "enum": ["point", "box", "ellipsoid"]},
                "center": {
                  "type": "object",
                  "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number"}
                  },
                  "required": ["x", "y", "z"]
                },
                "size": {
                  "type": "object",
                  "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "z": {"type": "number"}
                  }
                }
              },
              "required": ["type", "center"]
            }
          }
        },
        "required": ["layer", "items"]
      }
    }
  },
  {
    "type":"function",
    "function": {
      "name":"data_plot_histogram",
      "description":"Compute intensity histogram from layer/roi",
      "parameters": {"type":"object","properties": {"layer":{"type":"string"},"roi":{"type":"object"}},"required":["layer"]}
    }
  },
  {
    "type":"function",
    "function": {
      "name":"data_ingest_csv_rois",
      "description":"Load CSV of ROIs and build canonical table",
      "parameters": {"type":"object","properties": {"file_id":{"type":"string"}},"required":["file_id"]}
    }
  },
  {"type":"function","function": {"name":"state_save","description":"Save and return NG state URL","parameters":{"type":"object","properties":{}}}},
  {"type":"function","function": {"name":"state_load","description":"Load state from a Neuroglancer URL or fragment","parameters":{"type":"object","properties":{"link":{"type":"string"}},"required":["link"]}}}
]


def run_chat(messages: List[Dict]) -> Dict:
    resp = client.chat.completions.create(
        model="gpt-4o-mini",  # any tool-capable model
        messages=messages,
        tools=TOOLS,
        tool_choice="auto"
    )
    return resp.model_dump()