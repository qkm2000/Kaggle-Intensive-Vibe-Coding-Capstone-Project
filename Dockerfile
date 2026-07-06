# Container for the live ADK agent (also bundles the MCP server, which the
# agent spawns as a stdio subprocess in-container).
FROM python:3.12-slim

WORKDIR /app
COPY . .

# Install the package with the ADK extra. The MCP server is a base dependency.
RUN pip install --no-cache-dir -e ".[adk]"

ENV LEDGERLENS_MODEL=gemini-2.0-flash \
    PYTHONUNBUFFERED=1

# Cloud Run provides $PORT. `adk api_server` serves the agent(s) under
# ./deployment over HTTP. GOOGLE_API_KEY is injected at runtime (never baked in).
CMD ["sh", "-c", "adk api_server deployment --host 0.0.0.0 --port ${PORT:-8080}"]
