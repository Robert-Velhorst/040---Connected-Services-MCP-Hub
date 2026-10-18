# Stdio connector; credentials are supplied at runtime and never baked in.
FROM python:3.15.0-slim-bookworm@sha256:122756f3fe72c4f5d3d71897888204ee85774bc79de952555b8a474e1d0a5d53
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8 USE_CLAUDE_APP=true TRELLO_READ_ONLY=true TRELLO_MCP_DB_PATH=/data/trello_cache.db
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.13.1 && uv sync --locked --no-dev --python 3.15.0
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY . .
RUN mkdir -p /data
CMD ["python", "main.py"]
