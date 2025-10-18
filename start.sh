#!/bin/bash
# Start neurogabber backend and frontend
# Usage: ./start.sh [--timing] [--no-streaming]

set -e

echo "Starting neurogabber..."
echo "======================"

# Set backend URL for frontend
export BACKEND="http://127.0.0.1:8000"

# Check for timing mode flag
TIMING_MODE="false"
USE_STREAMING="true"

for arg in "$@"; do
    if [[ "$arg" == "--timing" ]]; then
        TIMING_MODE="true"
        echo "Timing mode ENABLED - performance metrics will be logged to ./logs/agent_timing.jsonl"
    elif [[ "$arg" == "--no-streaming" ]]; then
        USE_STREAMING="false"
        echo "Streaming mode DISABLED - using non-streaming chat endpoint"
    fi
done

export TIMING_MODE
export USE_STREAMING

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "Error: uv is not installed. Please install it first."
    exit 1
fi

# Function to cleanup background processes on exit
cleanup() {
    echo ""
    echo "Shutting down services..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start backend
echo "Starting backend on http://127.0.0.1:8000..."
cd src/neurogabber
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
cd ../..

# Wait for backend to be ready
echo "Waiting for backend to start..."
sleep 3

# Start panel frontend
echo "Starting panel frontend on http://127.0.0.1:8006..."
cd src/neurogabber
uv run python -m panel serve panel/panel_app.py --autoreload --port 8006 --address 127.0.0.1 --allow-websocket-origin=127.0.0.1:8006 --allow-websocket-origin=localhost:8006 &
PANEL_PID=$!
cd ../..

# Wait a moment for panel to start
sleep 2

echo ""
echo "======================"
echo "✓ Backend running at: http://127.0.0.1:8000"
echo "✓ Panel frontend at:  http://localhost:8006"
echo "✓ API docs at:        http://127.0.0.1:8000/docs"
echo "======================"
echo "Press Ctrl+C to stop all services"

# Wait for background processes
wait
