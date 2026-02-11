#!/bin/bash

# Setup script for ADK Web Research Agent example
# This script creates a virtualenv and installs all required dependencies

set -e  # Exit on error

echo "================================================"
echo "ADK Web Research Agent - Setup"
echo "================================================"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check Python version
echo "→ Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "  Found Python $PYTHON_VERSION"

# Create virtualenv if it doesn't exist
if [ ! -d ".venv" ]; then
    echo ""
    echo "→ Creating virtual environment..."
    python3 -m venv .venv
    echo "  ✓ Virtual environment created"
else
    echo ""
    echo "→ Virtual environment already exists"
fi

# Activate virtualenv
echo ""
echo "→ Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo ""
echo "→ Upgrading pip..."
pip install --upgrade pip --quiet

# Install requirements
echo ""
echo "→ Installing dependencies from requirements.txt..."
pip install -r requirements.txt --quiet
echo "  ✓ Dependencies installed"

# Create .env file if it doesn't exist
if [ ! -f "agents/research_agent/.env" ]; then
    echo ""
    echo "→ Creating .env file from template..."
    cp agents/research_agent/.env.example agents/research_agent/.env
    echo "  ✓ .env file created at agents/research_agent/.env"
    echo ""
    echo "  ⚠  IMPORTANT: Edit agents/research_agent/.env and add your API keys:"
    echo "     - GOOGLE_GENAI_API_KEY (required)"
    echo "     - BRAINTRUST_API_KEY (required for tracing)"
else
    echo ""
    echo "→ .env file already exists at agents/research_agent/.env"
fi

echo ""
echo "================================================"
echo "Setup Complete!"
echo "================================================"
echo ""
echo "Next steps:"
echo "  1. Edit agents/research_agent/.env with your API keys"
echo "  2. Run ./check_config.sh to verify your configuration"
echo "  3. Run ./start_server.sh to start the ADK web server"
echo "  4. Open http://localhost:3000/dev-ui/ in your browser"
echo ""
