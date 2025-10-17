# Start neurogabber backend and frontend
# Usage: .\start.ps1 [-Timing]

param(
    [switch]$Timing
)

Write-Host "Starting neurogabber..." -ForegroundColor Cyan
Write-Host "======================" -ForegroundColor Cyan

# Set backend URL for frontend
$env:BACKEND = "http://127.0.0.1:8000"

# Check for timing mode flag
if ($Timing) {
    $env:TIMING_MODE = "true"
    Write-Host "Timing mode ENABLED - performance metrics will be logged to ./logs/agent_timing.jsonl" -ForegroundColor Yellow
} else {
    $env:TIMING_MODE = "false"
}

# Check if uv is available
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Error: uv is not installed. Please install it first." -ForegroundColor Red
    exit 1
}

# Function to cleanup processes on exit
function Cleanup {
    Write-Host ""
    Write-Host "Shutting down services..." -ForegroundColor Yellow
    if ($BackendJob) { Stop-Job -Job $BackendJob; Remove-Job -Job $BackendJob }
    if ($PanelJob) { Stop-Job -Job $PanelJob; Remove-Job -Job $PanelJob }
    exit 0
}

# Register cleanup on Ctrl+C
Register-EngineEvent -SourceIdentifier PowerShell.Exiting -Action { Cleanup }

try {
    # Start backend
    Write-Host "Starting backend on http://127.0.0.1:8000..." -ForegroundColor Green
    $BackendJob = Start-Job -ScriptBlock {
        Set-Location $using:PWD
        uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
    }

    # Wait for backend to be ready
    Write-Host "Waiting for backend to start..." -ForegroundColor Yellow
    Start-Sleep -Seconds 3

    # Start panel frontend
    Write-Host "Starting panel frontend on http://127.0.0.1:8006..." -ForegroundColor Green
    $PanelJob = Start-Job -ScriptBlock {
        Set-Location $using:PWD
        $env:BACKEND = "http://127.0.0.1:8000"
        uv run python -m panel serve panel/panel_app.py --autoreload --port 8006 --address 127.0.0.1 --allow-websocket-origin=127.0.0.1:8006 --allow-websocket-origin=localhost:8006
    }

    # Wait a moment for panel to start
    Start-Sleep -Seconds 2

    Write-Host ""
    Write-Host "======================" -ForegroundColor Cyan
    Write-Host "✓ Backend running at: http://127.0.0.1:8000" -ForegroundColor Green
    Write-Host "✓ Panel frontend at:  http://localhost:8006" -ForegroundColor Green
    Write-Host "✓ API docs at:        http://127.0.0.1:8000/docs" -ForegroundColor Green
    Write-Host "======================" -ForegroundColor Cyan
    Write-Host "Press Ctrl+C to stop all services" -ForegroundColor Yellow
    Write-Host ""

    # Monitor jobs and show output
    while ($true) {
        # Check if jobs are still running
        if ($BackendJob.State -ne "Running" -or $PanelJob.State -ne "Running") {
            Write-Host "One or more services stopped unexpectedly." -ForegroundColor Red
            Receive-Job -Job $BackendJob
            Receive-Job -Job $PanelJob
            break
        }
        Start-Sleep -Seconds 1
    }
}
finally {
    Cleanup
}
