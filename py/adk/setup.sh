#!/bin/bash
# Setup script for ADK-Web Braintrust tracing example

set -e

echo "=================================================="
echo "ADK-Web Braintrust Tracing Example Setup"
echo "=================================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv .venv

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=================================================="
echo "Setup complete!"
echo "=================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Configure your API keys:"
echo "   Edit agents/weather_agent/.env and add:"
echo "   - GOOGLE_GENAI_API_KEY (from https://aistudio.google.com/apikey)"
echo "   - BRAINTRUST_API_KEY (from https://www.braintrust.dev/app/settings)"
echo ""
echo "   OR export them as environment variables:"
echo "   export GOOGLE_GENAI_API_KEY='your-key'"
echo "   export BRAINTRUST_API_KEY='your-key'"
echo ""
echo "2. Start the ADK-Web server:"
echo "   source .venv/bin/activate"
echo "   python server.py"
echo ""
echo "3. In another terminal, run the test client:"
echo "   source .venv/bin/activate"
echo "   python test_client.py"
echo ""
echo "4. Check Braintrust dashboard:"
echo "   https://www.braintrust.dev/"
echo "   Project: adk-web-tracing-test"
echo ""
echo "See README.md for detailed instructions."
echo "=================================================="
