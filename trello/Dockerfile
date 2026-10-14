# Trello MCP connector - stdio image for the ChatGPT desktop app / Codex.
#
# The app launches this with `docker run --rm -i`, so the container's stdout
# IS the MCP protocol channel. Nothing may ever be printed there except
# JSON-RPC; all logging in this project goes to stderr for that reason.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1 \
    PYTHONIOENCODING=utf-8 \
    # stdio transport (not the HTTP server)
    USE_CLAUDE_APP=true \
    # hard read-only boundary: no mutation tool is registered
    TRELLO_READ_ONLY=true \
    # local mirror lives on a mounted volume so it survives container restarts;
    # without this the connector would re-crawl all 85 boards on every launch
    TRELLO_MCP_DB_PATH=/data/trello_cache.db

WORKDIR /app

# Dependencies first so source edits do not invalidate this layer.
# mcp is capped below 2.0: that release removed mcp.server.fastmcp, which
# every tool module imports.
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir \
      "httpx>=0.28.1" \
      "mcp[cli]>=1.17.0,<2" \
      "python-dotenv>=1.0.0" \
      "uvicorn>=0.30.0"

COPY server/ ./server/
COPY main.py selftest.py status.py resync.py verify.py try.py ./

RUN mkdir -p /data

# Mount a named volume here to persist the index:
#   -v trello-mcp-data:/data
CMD ["python", "main.py"]
