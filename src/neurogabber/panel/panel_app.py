import os, json, httpx, asyncio, re, panel as pn, io
from datetime import datetime
from panel.chat import ChatInterface
from panel_neuroglancer import Neuroglancer

# get version from package metadata init
from importlib.metadata import version
version = version("neurogabber")
pn.config.theme = 'dark'
pn.extension()  # enable the neuroglancer extension
pn.extension(theme='dark')
pn.extension('tabulator')
pn.extension('filedropper')

BACKEND = os.environ.get("BACKEND", "http://127.0.0.1:8000")

viewer = Neuroglancer()
status = pn.pane.Markdown("Ready.")

# Track last loaded Neuroglancer URL (dedupe reloads)
last_loaded_url: str | None = None

# Mutation detection now handled server-side; state link returned directly when mutated.

# Settings widgets
auto_load_checkbox = pn.widgets.Checkbox(name="Auto-load view", value=True)
latest_url = pn.widgets.TextInput(name="Latest NG URL", value="", disabled=True)
trace_history_checkbox = pn.widgets.Checkbox(name="Trace history", value=False)
trace_history_length = pn.widgets.IntInput(name="History N", value=5)
trace_download = pn.widgets.FileDownload(label="Download traces", filename="trace_history.json", button_type="primary", disabled=True)
_trace_history: list[dict] = []

def _open_latest(_):
    if latest_url.value:
        viewer.url = latest_url.value

open_latest_btn = pn.widgets.Button(name="Open latest link", button_type="primary")
open_latest_btn.on_click(_open_latest)

async def _notify_backend_state_load(url: str):
    """Inform backend that the widget loaded a new NG URL so CURRENT_STATE is in sync."""
    try:
        status.object = "Syncing state to backend…"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(f"{BACKEND}/tools/state_load", json={"link": url})
            data = resp.json()
            if not data.get("ok"):
                status.object = f"Error syncing link: {data.get('error', 'unknown error')}"
                return
        status.object = f"**Opened:** {url}"
    except Exception as e:
        status.object = f"Error syncing: {e}"

def _on_url_change(event):
    # Called when the widget loads Demo or a user URL, or when we set viewer.url
    new_url = event.new
    if not new_url:
        return
    asyncio.create_task(_notify_backend_state_load(new_url))

# Watch the Neuroglancer widget URL; use its built-in Demo/Load buttons
viewer.param.watch(_on_url_change, 'url')
async def agent_call(prompt: str) -> dict:
    """Call backend iterative chat once; backend executes tools.

    Returns:
      answer: final assistant message
      mutated: bool indicating any mutating tool executed server-side
      url/masked: Neuroglancer link info if mutated (present only when mutated)
    """
    async with httpx.AsyncClient(timeout=120) as client:
        chat_payload = {"messages": [{"role": "user", "content": prompt}]}
        resp = await client.post(f"{BACKEND}/agent/chat", json=chat_payload)
        data = resp.json()
        answer = None
        if data.get("choices"):
            msg = data["choices"][0].get("message", {})
            answer = msg.get("content")
        mutated = bool(data.get("mutated"))
        state_link = data.get("state_link") or {}
        tool_trace = data.get("tool_trace") or []
        return {
            "answer": answer or "(no response)",
            "mutated": mutated,
            "url": state_link.get("url"),
            "masked": state_link.get("masked_markdown"),
            "tool_trace": tool_trace,
        }

def _mask_client_side(text: str) -> str:
    """Safety net masking on frontend: collapse raw Neuroglancer URLs.

    Mirrors backend labeling but simpler (does not number multiple distinct URLs).
    """
    if not text:
        return text
    url_pattern = re.compile(r"https?://[^\s)]+")
    def repl(m):
        u = m.group(0)
        if 'neuroglancer' in u:
            return f"[Updated Neuroglancer view]({u})"
        return u
    return url_pattern.sub(repl, text)


async def respond(contents: str, user: str, **kwargs):
    global last_loaded_url, _trace_history
    status.object = "Running…"
    try:
        result = await agent_call(contents)
        link = result.get("url")
        mutated = bool(result.get("mutated"))
        safe_answer = _mask_client_side(result.get("answer")) if result.get("answer") else None
        trace = result.get("tool_trace") or []
        if trace:
            # Build concise status line of executed tool names in order
            tool_names = [t.get("tool") or t.get("name") for t in trace if t]
            if tool_names:
                status.object = f"Tools: {' → '.join(tool_names)}"

        # Optional trace history retrieval
        if trace_history_checkbox.value:
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    hist_resp = await client.get(f"{BACKEND}/debug/tool_trace", params={"n": trace_history_length.value})
                hist_data = hist_resp.json()
                _trace_history = hist_data.get("traces", [])
                if _trace_history:
                    def _payload():
                        payload = {
                            "exported_at": datetime.utcnow().isoformat() + 'Z',
                            "count": len(_trace_history),
                            "traces": _trace_history,
                        }
                        return io.BytesIO(json.dumps(payload, indent=2).encode('utf-8'))
                    trace_download.callback = _payload
                    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                    trace_download.filename = f"trace_history_{ts}.json"
                    trace_download.disabled = False
            except Exception as e:  # pragma: no cover
                status.object += f" | Trace err: {e}"

        if mutated and link:
            latest_url.value = link
            masked = result.get("masked") or f"[Updated Neuroglancer view]({link})"
            if link != last_loaded_url:
                if auto_load_checkbox.value:
                    viewer.url = link
                    viewer._load_url()
                    last_loaded_url = link
                    status.object = f"**Opened:** {link}"
                else:
                    status.object = "New link generated (auto-load off)."
            else:
                status.object = "State updated (no link change)."
            if safe_answer:
                return f"{safe_answer}\n\n{masked}"
            return masked
        else:
            if not trace:
                status.object = "Done (no view change)."
            return safe_answer if safe_answer else "(no response)"
    except Exception as e:
        status.object = f"Error: {e}"
        return f"Error: {e}"

# ---------------- Chat UI ----------------
chat = ChatInterface(
    user="User",
    avatar="👤",
    callback_user="Agent",
    show_activity_dot=True,
    callback=respond,         # async callback
    height=1000,
    show_button_name=False,
    show_avatar=False,
    show_reaction_icons=False,
    show_copy_icon=False,
    show_timestamp=False,
    widgets=[
        pn.chat.ChatAreaInput(placeholder="Ask a question or issue a command..."),
    ],
    message_params={
        "stylesheets": [
            """
            .message {
                font-size: 1em;
                padding: 4px;
            }
            .name { font-size: 0.9em; }
            .timestamp { font-size: 0.9em; }
            """
        ]
     }
)

# ---------------- Settings UI ----------------
settings_card = pn.Card(
    pn.Column(auto_load_checkbox, latest_url, open_latest_btn, trace_history_checkbox, trace_history_length, trace_download, status),
    title="Settings",
    collapsed=False,
)

# ---------------- Data Upload & Summaries UI ----------------
# NOTE: We keep upload + table refresh synchronous to avoid early event-loop timing issues
# during Panel server warm start on some platforms (Windows). Async is still used for
# LLM/chat + state sync, but simple data listing uses blocking httpx calls.
file_drop = pn.widgets.FileDropper(name="Drop CSV files here", multiple=True, accepted_filetypes=["text/csv", ".csv"])
upload_notice = pn.pane.Markdown("")
try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None

if pd is not None:
    uploaded_table = pn.widgets.Tabulator(pd.DataFrame(columns=["file_id","name","size","n_rows","n_cols"]), height=210, disabled=True)
    summaries_table = pn.widgets.Tabulator(pd.DataFrame(columns=["summary_id","source_file_id","kind","n_rows","n_cols"]), height=210, disabled=True)
else:
    uploaded_table = pn.pane.Markdown("pandas not available")
    summaries_table = pn.pane.Markdown("pandas not available")

def _refresh_files():
    if pd is None:
        return
    try:
        with httpx.Client(timeout=30) as client:
            lst = client.post(f"{BACKEND}/tools/data_list_files")
            data = lst.json().get("files", [])
        if data:
            uploaded_table.value = pd.DataFrame(data)
        else:
            uploaded_table.value = pd.DataFrame(columns=uploaded_table.value.columns)
    except Exception as e:  # pragma: no cover
        upload_notice.object = f"File list error: {e}"

def _refresh_summaries():
    if pd is None:
        return
    try:
        with httpx.Client(timeout=30) as client:
            lst = client.post(f"{BACKEND}/tools/data_list_summaries")
            data = lst.json().get("summaries", [])
        if data:
            summaries_table.value = pd.DataFrame(data)
        else:
            summaries_table.value = pd.DataFrame(columns=summaries_table.value.columns)
    except Exception as e:  # pragma: no cover
        upload_notice.object = f"Summary list error: {e}"

def _handle_file_upload(evt):
    files = evt.new or {}
    if not files:
        return
    msgs: list[str] = []
    # FileDropper provides mapping name -> bytes
    with httpx.Client(timeout=60) as client:
        for name, raw in files.items():
            try:
                # Some widgets may give dicts with 'content' or 'body'
                if isinstance(raw, dict):
                    raw_bytes = raw.get("content") or raw.get("body") or b""
                else:
                    raw_bytes = raw
                resp = client.post(
                    f"{BACKEND}/upload_file",
                    files={"file": (name, raw_bytes, "text/csv")},
                )
                rj = resp.json()
                if rj.get("ok"):
                    msgs.append(f"✅ {name} → {rj['file']['file_id']}")
                else:
                    msgs.append(f"❌ {name} error: {rj.get('error')}")
            except Exception as e:  # pragma: no cover
                msgs.append(f"❌ {name} exception: {e}")
    upload_notice.object = "\n".join(msgs)
    _refresh_files()
    _refresh_summaries()

file_drop.param.watch(_handle_file_upload, "value")

def _initial_refresh():
    _refresh_files()
    _refresh_summaries()

upload_card = pn.Card(
    pn.Column(
        file_drop,
        upload_notice,
        pn.pane.Markdown("**Uploaded Files**"),
        uploaded_table,
        pn.pane.Markdown("**Summaries**"),
        summaries_table,
    ),
    title="Data Upload & Summaries",
    collapsed=False,
    width=450,
)

# ---------------- Assemble App ----------------
# Main app with sidebar upload + chat, right sidebar settings, main viewer
app = pn.template.FastListTemplate(
    title=f"Neurogabber v {version}",
    sidebar=[upload_card,chat],
    right_sidebar=settings_card,
    collapsed_right_sidebar = True,
    main=[viewer],
    sidebar_width=450,
    theme="dark",
)

app.servable()


# prompt inject example
# pn.state.onload(_initial_refresh)

# prompt_btn = pn.widgets.Button(name="Draft prompt for first file", button_type="primary")

# def _inject_prompt(_):
#     if pd is None: return
#     if hasattr(uploaded_table, 'value') and not uploaded_table.value.empty:
#         fid = uploaded_table.value.iloc[0]["file_id"]
#         chat.send(f"Preview file {fid}")

# prompt_btn.on_click(_inject_prompt)