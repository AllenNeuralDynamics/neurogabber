import os, json
from typing import List, Dict
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are Neurogabber, a helpful assistant for Neuroglancer.

Decision rules:
- If the user only wants information answer directly from the provided 'Current viewer state summary' (no tools).
- If the user wants to modify the view/viewer (camera, LUTs, annotations, layers) call the corresponding tool(s).
- If unsure of layer names or ranges, call ng_state_summary first (detail='standard' unless user requests otherwise).
- After performing modifications, if the user requests a link or updated view, call ng_state_link (NOT state_save) to return a masked markdown hyperlink. Only call state_save when explicit persistence is requested (e.g. 'save', 'persist', 'store').
- Do not paste raw Neuroglancer URLs directly; always rely on ng_state_link for sharing the current view.

Dataframe rules:
- If the user wants a random sample, assume no seed, without replacement, and uniforming across all rows. Unless otherwise specificed. 
Keep answers concise. Provide brief rationale before tool calls when helpful. Avoid redundant summaries."""

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
    "type": "function",
    "function": {
      "name": "ng_add_layer",
      "description": "Add a new Neuroglancer layer (image, segmentation, or annotation). Idempotent if name exists.",
      "parameters": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "layer_type": {"type": "string", "enum": ["image","segmentation","annotation"], "default": "image"},
          "source": {"description": "Layer source spec (string or object, passed through)", "oneOf": [
            {"type": "string"},
            {"type": "object"},
            {"type": "null"}
          ]},
          "visible": {"type": "boolean", "default": True}
        },
        "required": ["name"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "ng_set_layer_visibility",
      "description": "Toggle visibility of an existing layer (adds 'visible' key if missing).",
      "parameters": {
        "type": "object",
        "properties": {
          "name": {"type": "string"},
          "visible": {"type": "boolean"}
        },
        "required": ["name","visible"]
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
  {"type":"function","function": {"name":"state_load","description":"Load state from a Neuroglancer URL or fragment","parameters":{"type":"object","properties":{"link":{"type":"string"}},"required":["link"]}}},
  {"type":"function","function": {"name":"ng_state_summary","description":"Get structured summary of current Neuroglancer state for reasoning. Use before modifications if unsure of layer names or ranges.","parameters":{"type":"object","properties":{"detail":{"type":"string","enum":["minimal","standard","full"],"default":"standard"}}}}},
  {"type":"function","function": {"name":"ng_state_link","description":"Return current state Neuroglancer link plus masked markdown hyperlink (use after modifications when user requests link).","parameters":{"type":"object","properties":{}}}}
]

# Data tools appended
DATA_TOOLS = [
  {
    "type": "function",
    "function": {
      "name": "data_list_files",
      "description": "List uploaded CSV files with metadata (ids, columns).",
      "parameters": {"type": "object", "properties": {}}
    }
  },
  {
    "type": "function",
    "function": {
      "name": "data_sample",
      "description": "Return a random sample of rows from a dataframe (without replacement by default). Use to inspect a subset before analysis.",
      "parameters": {
        "type": "object",
        "properties": {
          "file_id": {"type": "string"},
          "n": {"type": "integer", "default": 5, "minimum": 1, "maximum": 1000},
          "seed": {"type": ["integer", "null"], "description": "Optional seed for reproducibility"},
          "replace": {"type": "boolean", "default": False}
        },
        "required": ["file_id"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "data_ng_views_table",
      "description": "Generate multiple Neuroglancer view links from a dataframe (e.g., top N by a metric) returning a table of id + metrics + links. Mutates state to first view.",
      "parameters": {
        "type": "object",
        "properties": {
          "file_id": {"type": "string", "description": "Source file id (provide either file_id OR summary_id)"},
          "summary_id": {"type": "string", "description": "Existing summary/derived table id (mutually exclusive with file_id)"},
          "sort_by": {"type": "string"},
          "descending": {"type": "boolean", "default": True},
          "top_n": {"type": "integer", "default": 5, "minimum": 1, "maximum": 50},
          "id_column": {"type": "string", "default": "cell_id"},
          "center_columns": {"type": "array", "items": {"type": "string"}, "default": ["x","y","z"]},
          "include_columns": {"type": "array", "items": {"type": "string"}},
          "lut": {"type": "object", "properties": {"layer": {"type": "string"}, "min": {"type": "number"}, "max": {"type": "number"}}},
          "annotations": {"type": "boolean", "default": False},
          "link_label_column": {"type": "string"}
        },
        # Note: cannot express mutual exclusivity without oneOf (disallowed by OpenAI);
        # model should infer to supply only one of file_id or summary_id.
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "data_info",
      "description": "Return dataframe metadata (rows, cols, columns, dtypes, head sample). Call before asking questions about the dataset.",
      "parameters": {
        "type": "object",
        "properties": {
          "file_id": {"type": "string"},
          "sample_rows": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20}
        },
        "required": ["file_id"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "data_preview",
      "description": "Preview first N rows of a file.",
      "parameters": {
        "type": "object",
        "properties": {
          "file_id": {"type": "string"},
          "n": {"type": "integer", "default": 10, "minimum": 1, "maximum": 100}
        },
        "required": ["file_id"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "data_describe",
      "description": "Compute numeric summary statistics for a file.",
      "parameters": {
        "type": "object",
        "properties": {
          "file_id": {"type": "string"}
        },
        "required": ["file_id"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "data_select",
      "description": "Select subset of columns and filtered rows; stores as summary table.",
      "parameters": {
        "type": "object",
        "properties": {
          "file_id": {"type": "string"},
          "columns": {"type": "array", "items": {"type": "string"}},
          "filters": {
            "type": "array",
            "items": {
              "type": "object",
              "properties": {
                "column": {"type": "string"},
                "op": {"type": "string", "enum": ["==","!=",">","<",">=","<="]},
                "value": {}
              },
              "required": ["column", "op", "value"]
            }
          },
          "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 500}
        },
        "required": ["file_id"]
      }
    }
  },
  {
    "type": "function",
    "function": {
      "name": "data_list_summaries",
      "description": "List previously created summary / derived tables.",
      "parameters": {"type": "object", "properties": {}}
    }
  },
]

TOOLS = TOOLS + DATA_TOOLS


def run_chat(messages: List[Dict]) -> Dict:
    resp = client.chat.completions.create(
        #model="gpt-4o-mini",  # any tool-capable model
        model="gpt-5-nano",  # any tool-capable model
        messages=messages,
        tools=TOOLS,
        tool_choice="auto"
    )
    return resp.model_dump()