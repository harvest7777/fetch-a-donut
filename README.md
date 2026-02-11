# Fetch-a-Donut

An interactive agent built with [uAgents](https://github.com/fetchai/uAgents) that hands out donut tickets at events. Tell the agent your favorite donut, get a unique coupon code and a fun AI-generated response powered by ASI:One.

## How It Works

1. A user starts a chat with the agent
2. The agent asks for their favorite donut
3. ASI:One generates a fun response and the agent issues a unique ticket code
4. One ticket per session — repeat messages return the existing coupon

## Prerequisites

- Python 3.12+
- An [ASI:One](https://asi1.ai) API key
- An Agentverse API key and seed phrase (for registration)

## Configuration

Copy the example env file and fill in your keys:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `ASI_ONE_API_KEY` | ASI:One API key | — |
| `AGENT_SEED_PHRASE` | Agent seed phrase | — |
| `ILABS_AGENTVERSE_API_KEY` | Agentverse API key | — |
| `AGENT_PORT` | Port the agent listens on | `8056` |

Event-specific settings (conference name, coupon prefix, etc.) live in `config.py`.

## Local Development

```bash
pip install -r requirements.txt
python3 app.py
```

The agent will start on `http://localhost:8056` (or whatever `AGENT_PORT` is set to).

## Docker

```bash
docker compose up --build
```

This builds the image, loads your `.env`, and exposes the agent on the configured port. The container restarts automatically unless stopped.
