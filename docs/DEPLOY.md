# Deployment

> Deployment is **not required** for capstone judging, but LedgerLens is built
> to be deployable. This documents the two supported paths so the "Deployability"
> concept is reproducible.

The agent is exposed for ADK tooling via [`deployment/agent.py`](../deployment/agent.py),
which sets a module-level `root_agent`. The live agent spawns the MCP server as
a stdio subprocess inside the same runtime, so a single container ships both.

## Prerequisites

```bash
pip install -e ".[adk]"
export GOOGLE_API_KEY=...          # runtime only — never committed
```

## Option A — one command to Cloud Run (recommended)

ADK ships a Cloud Run deployer. Point it at the `deployment` package:

```bash
gcloud auth login
adk deploy cloud_run \
  --project "$GOOGLE_CLOUD_PROJECT" \
  --region  us-central1 \
  --service_name ledgerlens \
  deployment
```

Set `GOOGLE_API_KEY` as a Cloud Run environment variable / secret (do **not**
bake it into the image).

## Option B — container + `gcloud run deploy`

The provided [`Dockerfile`](../Dockerfile) serves the agent with
`adk api_server deployment` on `$PORT`:

```bash
gcloud run deploy ledgerlens \
  --source . \
  --region us-central1 \
  --set-env-vars LEDGERLENS_MODEL=gemini-2.0-flash \
  --set-secrets GOOGLE_API_KEY=ledgerlens-gemini-key:latest \
  --allow-unauthenticated
```

## Run locally the same way

```bash
adk web deployment          # local dev UI at http://localhost:8000
# or
adk api_server deployment   # local HTTP API
```

## The MCP server on its own

The MCP server is independently deployable / connectable by any MCP host
(Claude Desktop, `mcp dev`, another ADK app):

```bash
python -m ledgerlens.mcp_server        # stdio
mcp dev src/ledgerlens/mcp_server.py   # MCP Inspector
```
