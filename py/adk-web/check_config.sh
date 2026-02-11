#!/bin/bash

# Configuration verification script
# Checks that all required API keys are configured

set -e

echo "================================================"
echo "Configuration Check"
echo "================================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if .env file exists
ENV_FILE="agents/research_agent/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo "✗ Error: .env file not found at $ENV_FILE"
    echo ""
    echo "  Run ./setup.sh first to create the .env file"
    exit 1
fi

# Source the .env file
source "$ENV_FILE"

# Check GOOGLE_GENAI_API_KEY
echo "→ Checking GOOGLE_GENAI_API_KEY..."
if [ -z "$GOOGLE_GENAI_API_KEY" ]; then
    echo "  ✗ GOOGLE_GENAI_API_KEY is not set"
    echo "    Get your API key from: https://aistudio.google.com/apikey"
    EXIT_CODE=1
else
    # Show last 8 characters
    MASKED_KEY="${GOOGLE_GENAI_API_KEY: -8}"
    echo "  ✓ GOOGLE_GENAI_API_KEY is set: ...$MASKED_KEY"
fi

# Check BRAINTRUST_API_KEY
echo ""
echo "→ Checking BRAINTRUST_API_KEY..."
if [ -z "$BRAINTRUST_API_KEY" ]; then
    echo "  ✗ BRAINTRUST_API_KEY is not set"
    echo "    Get your API key from: https://www.braintrust.dev/app/settings"
    EXIT_CODE=1
else
    # Show last 8 characters
    MASKED_KEY="${BRAINTRUST_API_KEY: -8}"
    echo "  ✓ BRAINTRUST_API_KEY is set: ...$MASKED_KEY"
fi

echo ""
if [ -z "$EXIT_CODE" ]; then
    echo "================================================"
    echo "✓ All API keys are configured!"
    echo "================================================"
    echo ""
    echo "You're ready to run: ./start_server.sh"
    echo ""
else
    echo "================================================"
    echo "✗ Configuration incomplete"
    echo "================================================"
    echo ""
    echo "Please edit $ENV_FILE and add the missing API keys"
    echo ""
    exit 1
fi
