import os, json, httpx, panel as pn
from panel.chat import ChatInterface
from panel_neuroglancer import Neuroglancer

pn.extension('neuroglancer')  # enable the neuroglancer extension

BACKEND = os.environ.get("BACKEND", "http://127.0.0.1:8000")

viewer = Neuroglancer()
status = pn.pane.Markdown("Ready.")

async def agent_call(prompt: str) -> str:
    """Send prompt to FastAPI agent, execute tool calls, return final NG state URL."""
    async with httpx.AsyncClient(timeout=60) as client:
        # 1) Ask the agent for tool calls
        chat = {"messages": [{"role": "user", "content": prompt}]}
        resp = await client.post(f"{BACKEND}/agent/chat", json=chat)
        data = resp.json()

        # 2) Execute tool calls
        for choice in data.get("choices", []):
            msg = choice.get("message", {})
            for tc in msg.get("tool_calls", []):
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"] or "{}")
                await client.post(f"{BACKEND}/tools/{name}", json=args)

        # 3) Save state and return URL
        save = await client.post(f"{BACKEND}/tools/state.save", json={})
        return save.json()["url"]

async def respond(contents: str, user: str, **kwargs):
    """Async callback works natively on Panel 1.7.5."""
    status.object = "Running…"
    try:
        url = await agent_call(contents)
        viewer.source = url
        status.object = f"**Opened:** {url}"
        return f"Updated Neuroglancer view.\n\n{url}"
    except Exception as e:
        status.object = f"Error: {e}"
        return f"Error: {e}"

chat = ChatInterface(
    user="You",
    avatar="?",
    callback_user="Agent",
    callback=respond,         # async callback
    #show_avatars=True,
    height=360,
)

app = pn.Row(
    pn.Column(pn.pane.Markdown("# Neurogabber (Panel prototype)"), status, chat,
              sizing_mode="stretch_both"),
    pn.Column(viewer, sizing_mode="stretch_both"),
)

app.servable()