# Ruby LLM Agent with Python Braintrust Evaluation

This example evaluates a Ruby LLM agent using Python and Braintrust. The Ruby agent ([agent.rb](evals/remote_evals/agent.rb)) uses `ruby_llm` to create a weather assistant with tool calling. Python ([remote_agent_eval.py](evals/remote_evals/remote_agent_eval.py)) runs the agent as a subprocess and evaluates responses using Factuality and Possible scorers.

In this example, we use a Python "shim" to facilitate remote evals for agents written in languages for which Braintrust SDKs do not yet support native remote evals. The same process would work with the Typescript SDK.

Video Demo: [Loom](https://www.loom.com/share/9a0626ea3b1244ebb09188509061a382)

What is a [remote eval?](https://www.braintrust.dev/docs/guides/remote-evals)

## Setup

1. Install dependencies:
```bash
mise install
source .venv/bin/activate
pip install -r requirements.txt
cd ruby && bundle install && cd ..
```

2. Configure environment variables:
```bash
cp .env.example .env
# (located in repo root dir)
# Edit .env with your API keys
```

Required:
- `BRAINTRUST_API_KEY`
- `BRAINTRUST_PARENT` (project name)
- `OPENAI_API_KEY` and/or `ANTHROPIC_API_KEY`

## Running the Evaluation

```bash
cd ruby/evals/remote_evals
source ../../../.venv/bin/activate
braintrust eval remote_agent_eval.py --dev
```

The default model is `gpt-4o-mini`. Modify [ModelParam](evals/remote_evals/remote_agent_eval.py:12) to use a different model.

## How It Works

1. Python invokes Ruby subprocess with model and location parameters
2. Ruby agent calls LLM with Weather tool (queries Open-Meteo API)
3. Agent outputs JSON result to stdout
4. Python evaluates response using Braintrust scorers

The evaluation uses a Braintrust dataset named "WeatherLocations" containing location strings.

## Troubleshooting

**ModuleNotFoundError: No module named 'openai'**
```bash
source .venv/bin/activate && pip install openai
```

**Ruby LoadError**
```bash
cd ruby && bundle install
```

**Must run from ruby/evals/remote_evals directory**

The evaluation script checks that you're in the correct directory before running.