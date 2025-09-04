import os, json, httpx, asyncio, panel as pn
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
    """Return {'answer': str|None, 'url': str|None}."""
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
            return {"answer": answer or "(no response)", "url": None}

        # Execute tool calls
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            await client.post(f"{BACKEND}/tools/{name}", json=args)

        # Save state and return URL
        save = await client.post(f"{BACKEND}/tools/state_save", json={})
        return {"answer": answer, "url": save.json()["url"]}

async def respond(contents: str, user: str, **kwargs):
    status.object = "Running…"
    try:
        result = await agent_call(contents)
        if result["url"]:
            viewer.url = result["url"]
            status.object = f"**Opened:** {result['url']}"
            if result["answer"]:
                return f"{result['answer']}\n\n{result['url']}"
            return f"Updated Neuroglancer view.\n\n{result['url']}"
        else:
            status.object = "Done."
            return result["answer"]
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

app = pn.template.FastListTemplate(
    title=f"Neurogabber v {version}",
    sidebar=[chat],
    main=[viewer],
    sidebar_width=450,
    theme = "dark"
)

# # layout 2
# app = pn.Row(
#     pn.Column(
#         pn.pane.Markdown("# Neurogabber (Panel prototype)"),
#         #status, shows full NG link
#         chat,
#         width=420,
#     ),
#     pn.Column(viewer, sizing_mode="stretch_both"),
# )

# old layoout
# app = pn.Column(
#     pn.pane.Markdown("# Neurogabber (Panel prototype)"),
#     status,
#     chat,
#     viewer,
#     sizing_mode="stretch_both"
# )

app.servable()