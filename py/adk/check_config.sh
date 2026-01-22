#!/bin/bash
# Check if API keys are configured

echo "=================================================="
echo "Configuration Check"
echo "=================================================="
echo ""

# Load environment variables
if [ -f "agents/weather_agent/.env" ]; then
    set -a
    source agents/weather_agent/.env
    set +a
fi

# Check Google API Key
echo "Checking GOOGLE_GENAI_API_KEY..."
if [ -z "$GOOGLE_GENAI_API_KEY" ] || [ "$GOOGLE_GENAI_API_KEY" = "your-api-key-here" ]; then
    echo "  ❌ NOT CONFIGURED"
    echo "     Edit agents/weather_agent/.env and set your Google AI API key"
    echo "     Get it from: https://aistudio.google.com/apikey"
    GOOGLE_OK=0
else
    echo "  ✅ Configured (length: ${#GOOGLE_GENAI_API_KEY} chars)"
    GOOGLE_OK=1
fi

echo ""

# Check Braintrust API Key
echo "Checking BRAINTRUST_API_KEY..."
if [ -z "$BRAINTRUST_API_KEY" ] || [ "$BRAINTRUST_API_KEY" = "your-braintrust-api-key-here" ]; then
    echo "  ❌ NOT CONFIGURED"
    echo "     Edit agents/weather_agent/.env and set your Braintrust API key"
    echo "     Get it from: https://www.braintrust.dev/app/settings"
    echo "     WARNING: Traces will NOT be sent to Braintrust without this!"
    BRAINTRUST_OK=0
else
    echo "  ✅ Configured (length: ${#BRAINTRUST_API_KEY} chars)"
    BRAINTRUST_OK=1
fi

echo ""
echo "=================================================="

if [ $GOOGLE_OK -eq 1 ] && [ $BRAINTRUST_OK -eq 1 ]; then
    echo "✅ All API keys configured!"
    echo "   Run: ./start_server.sh"
elif [ $GOOGLE_OK -eq 1 ]; then
    echo "⚠️  Google API key configured, but Braintrust key missing"
    echo "   Server will work, but NO TRACES will be sent to Braintrust"
    echo "   This means you won't be able to reproduce the tracing issue!"
else
    echo "❌ Google API key missing - server will NOT work"
    echo "   Please configure your API keys in agents/weather_agent/.env"
fi

echo "=================================================="
