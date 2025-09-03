# neurogabber

[![License](https://img.shields.io/badge/license-MIT-brightgreen)](LICENSE)
![Code Style](https://img.shields.io/badge/code%20style-black-black)
[![semantic-release: angular](https://img.shields.io/badge/semantic--release-angular-e10079?logo=semantic-release)](https://github.com/semantic-release/semantic-release)
![Interrogate](https://img.shields.io/badge/interrogate-%25-yellow)
![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)
![Python](https://img.shields.io/badge/python->=3.10-blue?logo=python)

## To run
+ backend: `uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000`
+ frontend:
    + `$env:BACKEND = "http://127.0.0.1:8000"`
    + panel: `uv run python -m panel serve panel\panel_app.py --autoreload --port 8006 --address 127.0.0.1`
    + panel chat:
        ```bash
            uv run python -m panel serve panel\panel_app.py `
            --autoreload --port 8006 --address 127.0.0.1 `
            --allow-websocket-origin=127.0.0.1:8006 `
            --allow-websocket-origin=localhost:8006
        ```
    + open browser: http://localhost:8006

+ tests
    + `uv run -m coverage run -m pytest`
    + `uv run -m coverage report`

## Level of Support
Please indicate a level of support:
 - [ ] Supported: We are releasing this code to the public as a tool we expect others to use. Issues are welcomed, and we expect to address them promptly; pull requests will be vetted by our staff before inclusion.
 - [ ] Occasional updates: We are planning on occasional updating this tool with no fixed schedule. Community involvement is encouraged through both issues and pull requests.
 - [ ] Unsupported: We are not currently supporting this code, but simply releasing it to the community AS IS but are not able to provide any guarantees of support. The community is welcome to submit issues, but you should not expect an active response.

## Release Status
GitHub's tags and Release features can be used to indicate a Release status.

 - Stable: v1.0.0 and above. Ready for production.
 - Beta:  v0.x.x or indicated in the tag. Ready for beta testers and early adopters.
 - Alpha: v0.x.x or indicated in the tag. Still in early development.

## Installation
To use the software, in the root directory, run
```bash
pip install -e .
```

To develop the code, run
```bash
pip install -e . --group dev
```
Note: --group flag is available only in pip versions >=25.1

Alternatively, if using `uv`, run
```bash
uv sync
```
