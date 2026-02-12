# LangChain + Braintrust Examples

This directory contains examples of using LangChain with Braintrust for evaluation and observability.

## Chainlit Chatbot

A Chainlit application supporting OpenAI and Anthropic AI providers with RAG and web search.

### Quick Start

```bash
# Use the parent directory's venv
source ../.venv/bin/activate

# Set API keys
export OPENAI_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
export TAVILY_API_KEY="your-key"
export BRAINTRUST_API_KEY="your-key"

# Run the app
chainlit run app.py
```

### Features
- PDF document upload and RAG
- Web search via Tavily
- Conversation tracking
- Braintrust logging
- Streaming responses

## Remote Eval for Chatbots

A flexible evaluation framework for testing chatbots with different AI providers and models.

### Quick Start

```bash
# Install dependencies
pip install braintrust openai anthropic python-dotenv autoevals

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Create sample dataset
python create_sample_dataset.py

# Start eval server
braintrust eval remote_chatbot_eval.py --dev
```

### Configuration

Set defaults in `.env`:
```bash
AI_PROVIDER=openai  # or anthropic
AI_MODEL=gpt-4o-mini  # or claude-sonnet-4-5-20250929
```

### Using in Braintrust

1. Register endpoint at `http://localhost:8300` in Braintrust → Configuration → Remote evals
2. Open Playground and select your remote eval
3. Configure provider, model, system prompt via UI
4. Run evaluations on your dataset

For more details, see the individual script files and comments.

