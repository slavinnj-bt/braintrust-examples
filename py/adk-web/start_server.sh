#!/bin/bash

# Start the custom ADK web server with session-level Braintrust tracing

set -e

echo "================================================"
echo "Starting ADK Web Server (Multi-Turn Tracing)"
echo "================================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtualenv exists
if [ ! -d ".venv" ]; then
    echo "ERROR: Virtual environment not found"
    echo "Run ./setup.sh first"
    exit 1
fi

# Activate virtualenv
echo "Activating virtual environment..."
source .venv/bin/activate

# Start the custom server with session-level tracing
echo ""
echo "Starting ADK server with Braintrust multi-turn tracing"
echo "Server: http://localhost:3000"
echo "Web UI: http://localhost:3000/dev-ui/"
echo ""
echo "Features:"
echo "  - Session-level tracing enabled"
echo "  - All turns grouped under session span"
echo "  - Server restart detection (forces new sessions)"
echo "  - Prevents duplicate/orphaned traces"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""
echo "================================================"
echo ""

# Run the custom FastAPI server using uvicorn
uvicorn unified_tracing:app --host 0.0.0.0 --port 3000
