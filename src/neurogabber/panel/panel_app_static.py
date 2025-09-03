import os, json, httpx, panel as pn
from panel_neuroglancer import Neuroglancer
from ng_example import ng_link
#pn.extension()

BACKEND = os.environ.get("BACKEND", "http://127.0.0.1:8000")

prompt = pn.widgets.TextAreaInput(name="Prompt", height=140,
                                  placeholder="Show me the middle, zoom to fit, hide all annotations")
run_btn = pn.widgets.Button(name="Run", button_type="primary")
status = pn.pane.Markdown("Ready.")
#viewer = Neuroglancer(source="https://aind-neuroglancer-sauujisjxq-uw.a.run.app/#!s3://aind-open-data/HCR_794300-10_2025-08-14_13-00-00/raw_data.json")  # starts empty; we'll set .source to a state URL

viewer = Neuroglancer(source=ng_link)

async def init_backend_state_from_demo():
    # Push the demo link into the backend so CURRENT_STATE matches the viewer
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            await client.post(f"{BACKEND}/tools/state_load", json={"link": ng_link})
        except Exception:
            pass

# Schedule background init on app load
pn.state.onload(lambda: pn.state.run_async(init_backend_state_from_demo()))

async def run(_):
    status.object = "Running…"
    async with httpx.AsyncClient(timeout=60) as client:
        # 1) Ask the agent for tool calls
        chat = {"messages": [{"role":"user","content": prompt.value}]}
        resp = await client.post(f"{BACKEND}/agent/chat", json=chat)
        data = resp.json()
        # 2) Execute any tool calls
        for choice in data.get("choices", []):
            msg = choice.get("message", {})
            for tc in msg.get("tool_calls", []):
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"] or "{}")
                await client.post(f"{BACKEND}/tools/{name}", json=args)
        # 3) Save state and open the URL in the embedded NG widget
    save = await client.post(f"{BACKEND}/tools/state_save", json={})
        url = save.json()["url"]
        viewer.source = url
        status.object = f"**Opened:** {url}"

run_btn.on_click(lambda e: pn.state.run_async(run(e)))

app = pn.Column(
    pn.pane.Markdown("# Neurogabber (Panel prototype)"),
    prompt, run_btn, status, viewer,
    sizing_mode="stretch_width",
)
app.servable()