# Start neurogabber backend only (for development)
# Usage: .\start_backend.ps1 [-Timing]

param(
    [switch]$Timing
)

Write-Host "Starting neurogabber backend..." -ForegroundColor Cyan

# Set backend URL for frontend
$env:BACKEND = "http://127.0.0.1:8000"

# Check for timing mode flag
if ($Timing) {
    $env:TIMING_MODE = "true"
    Write-Host "Timing mode ENABLED - performance metrics will be logged to ./logs/agent_timing.jsonl" -ForegroundColor Yellow
} else {
    $env:TIMING_MODE = "false"
}

# Change to backend directory
Set-Location "$PSScriptRoot\src\neurogabber"

# Start backend in foreground
Write-Host ""
Write-Host "Starting backend on http://127.0.0.1:8000..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
