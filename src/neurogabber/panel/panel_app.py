import os, json, httpx, asyncio, re, panel as pn
from panel.chat import ChatInterface
from panel_neuroglancer import Neuroglancer

# get version from package metadata init
from importlib.metadata import version
version = version("neurogabber")
pn.config.theme = 'dark'
pn.extension()  # enable the neuroglancer extension
pn.extension(theme='dark')

BACKEND = os.environ.get("BACKEND", "http://127.0.0.1:8000")

viewer = Neuroglancer()
status = pn.pane.Markdown("Ready.")

# Track last loaded Neuroglancer URL (dedupe reloads)
last_loaded_url: str | None = None

# Tools that mutate the shared Neuroglancer state; if any run we should refresh viewer
MUTATING_TOOLS = {
    "ng_set_view",
    "ng_set_lut",
    "ng_annotations_add",
    "state_load",            # replaces entire state
    "data_ingest_csv_rois",  # may add an annotation layer
}

# Settings widgets
auto_load_checkbox = pn.widgets.Checkbox(name="Auto-load view", value=True)
latest_url = pn.widgets.TextInput(name="Latest NG URL", value="", disabled=True)

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
    """Return {'answer': str|None, 'url': str|None, 'masked': str|None, 'tools': [str]}.

    Execute tool calls then fetch current masked link via ng_state_link (no
    persistence). Include executed tool names so caller can decide whether to
    auto-load the viewer based on mutation.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        chat = {"messages": [{"role": "user", "content": prompt}]}
        resp = await client.post(f"{BACKEND}/agent/chat", json=chat)
        data = resp.json()

        answer = None
        tool_calls = []
        for choice in (data.get("choices") or []):
            msg = choice.get("message", {})
            if msg.get("content"):
                answer = msg["content"]
            for tc in (msg.get("tool_calls") or []):
                tool_calls.append(tc)

        if not tool_calls:
            # Conversational: no state change
            return {"answer": answer or "(no response)", "url": None, "masked": None}

        # Execute tool calls sequentially
        executed = []
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            await client.post(f"{BACKEND}/tools/{name}", json=args)
            executed.append(name)

        # Fetch current masked link (no persistence) after mutations BEFORE closing client
        link_resp = await client.post(f"{BACKEND}/tools/ng_state_link")
        link_data = link_resp.json()
        return {
            "answer": answer,
            "url": link_data.get("url"),
            "masked": link_data.get("masked_markdown"),
            "tools": executed,
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
    global last_loaded_url
    status.object = "Running…"
    try:
        result = await agent_call(contents)
        link = result.get("url")
        executed = set(result.get("tools") or [])
        mutated = bool(executed & MUTATING_TOOLS)
        safe_answer = _mask_client_side(result.get("answer")) if result.get("answer") else None

        if link:
            latest_url.value = link or ""
            masked = result.get("masked") or f"[Updated Neuroglancer view]({link})"
            if mutated:
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
            else:
                status.object = "Completed (no view change)."

            if safe_answer:
                return f"{safe_answer}\n\n{masked}"
            return masked
        else:
            status.object = "Done."
            return safe_answer if safe_answer else "(no response)"
    except Exception as e:
        status.object = f"Error: {e}"
        return f"Error: {e}"
    
# async def agent_call(prompt: str) -> str:
#     """Send prompt to FastAPI agent, execute tool calls, return final NG state URL."""
#     async with httpx.AsyncClient(timeout=60) as client:
#         # 1) Ask the agent for tool calls
#         chat = {"messages": [{"role": "user", "content": prompt}]}
#         resp = await client.post(f"{BACKEND}/agent/chat", json=chat)
#         data = resp.json()

#         # 2) Execute tool calls
#         for choice in (data.get("choices") or []):
#             msg = choice.get("message", {})
#             for tc in (msg.get("tool_calls") or []):
#                 name = tc["function"]["name"]
#                 args = json.loads(tc["function"]["arguments"] or "{}")
#                 await client.post(f"{BACKEND}/tools/{name}", json=args)

#         # 3) Save state and return URL
#         save = await client.post(f"{BACKEND}/tools/state_save", json={})
#         return save.json()["url"]

# async def respond(contents: str, user: str, **kwargs):
#     """Async callback works natively on Panel 1.7.5."""
#     status.object = "Running…"
#     try:
#         url = await agent_call(contents)
#         viewer.source = url
#         status.object = f"**Opened:** {url}"
#         return f"Updated Neuroglancer view.\n\n{url}"
#     except Exception as e:
#         status.object = f"Error: {e}"
#         return f"Error: {e}"

chat = ChatInterface(
    user="User",
    avatar="👤",
    callback_user="Agent",
    show_activity_dot=True,
    callback=respond,         # async callback
    height=1000,
    #buttons
    show_button_name=False,
    # chat ui
    show_avatar=False,
    show_reaction_icons=False,
    show_copy_icon=False,
    show_timestamp=False,
    widgets=[
        pn.chat.ChatAreaInput(placeholder="Enter some text to get a count!"),
        pn.widgets.FileInput(name="CSV File", accept=".csv"),
    ],
    # message styles
    message_params={   
         # .meta { display: none; }
         #             .avatar { display: none; }
         #center { min-height: 30px; background-color: lightgrey; }
         #.left { width: 2px; height: 2px; }
         #.avatar { width: 5px; height: 5px; min-width: 5px; min-height: 5px; }
         #.right{ background-color: red; }
         #.meta { display: none; height: 0px; }
        "stylesheets": [
            """
            .message {
                font-size: 1em;

                padding: 4px;
            }
            .name {
                font-size: 0.9em;
            }
            .timestamp {
                font-size: 0.9em;
            }
            
            
            """
        ]
     }
)

settings_card = pn.Card(
    pn.Column(auto_load_checkbox, latest_url, open_latest_btn, status),
    title="Settings",
    collapsed=False,
)


upload_card = pn.Card(
    pn.Column(
        pn.widgets.FileInput(name="CSV File", accept=".csv"),
        pn.widgets.Button(name="Upload", button_type="primary"),
    ),
    title="Upload",
    collapsed=True,
    # fill_space=True,
    width=450,
)


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