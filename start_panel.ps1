# Start neurogabber panel frontend only (for development)
# Usage: .\start_panel.ps1

Write-Host "Starting neurogabber panel frontend..." -ForegroundColor Cyan

# Set backend URL
$env:BACKEND = "http://127.0.0.1:8000"

# Change to panel directory
Set-Location "$PSScriptRoot\src\neurogabber"

# Start panel in foreground
Write-Host ""
Write-Host "Starting panel frontend on http://127.0.0.1:8006..." -ForegroundColor Green
Write-Host "Open http://localhost:8006 in your browser" -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

uv run python -m panel serve panel/panel_app.py --autoreload --port 8006 --address 127.0.0.1 --allow-websocket-origin=127.0.0.1:8006 --allow-websocket-origin=localhost:8006
