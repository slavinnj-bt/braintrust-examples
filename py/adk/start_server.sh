#!/bin/bash
# Start the standard ADK web server with Braintrust tracing

set -e

echo "=================================================="
echo "Starting ADK Web Server with Braintrust Tracing"
echo "=================================================="
echo ""

# Activate virtual environment
source .venv/bin/activate

# Load environment variables from the agent's .env file
if [ -f "agents/weather_agent/.env" ]; then
    echo "Loading environment variables from agents/weather_agent/.env"
    set -a
    source agents/weather_agent/.env
    set +a
fi

# Check if API keys are set
if [ -z "$GOOGLE_GENAI_API_KEY" ] || [ "$GOOGLE_GENAI_API_KEY" = "your-api-key-here" ]; then
    echo ""
    echo "ERROR: GOOGLE_GENAI_API_KEY not configured"
    echo ""
    echo "Please configure it by either:"
    echo "  1. Edit agents/weather_agent/.env and set GOOGLE_GENAI_API_KEY=your-actual-key"
    echo "  2. Export it before running: export GOOGLE_GENAI_API_KEY='your-actual-key'"
    echo ""
    echo "Get your API key from: https://aistudio.google.com/apikey"
    echo ""
    exit 1
fi

if [ -z "$BRAINTRUST_API_KEY" ] || [ "$BRAINTRUST_API_KEY" = "your-braintrust-api-key-here" ]; then
    echo ""
    echo "WARNING: BRAINTRUST_API_KEY not configured"
    echo "Traces will NOT be sent to Braintrust"
    echo ""
    echo "To enable tracing, configure it by either:"
    echo "  1. Edit agents/weather_agent/.env and set BRAINTRUST_API_KEY=your-actual-key"
    echo "  2. Export it before running: export BRAINTRUST_API_KEY='your-actual-key'"
    echo ""
    echo "Get your API key from: https://www.braintrust.dev/app/settings"
    echo ""
    echo "Continuing without Braintrust tracing..."
    sleep 2
fi

echo ""
echo "Starting ADK server on http://localhost:3000"
echo "Press Ctrl+C to stop"
echo ""

# Start the ADK server
# Note: agents directory is a positional argument, not --agents-dir
adk web --port 3000 ./agents
