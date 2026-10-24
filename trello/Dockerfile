# Stdio connector; credentials are supplied at runtime and never baked in.
FROM python:3.15.1-slim-trixie@sha256:08275f764e022331c6d3e3ca55d8cce01fa4684b02111adf0445d71806fe7941
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8 USE_CLAUDE_APP=true TRELLO_READ_ONLY=true TRELLO_MCP_DB_PATH=/data/trello_cache.db
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.13.5 && uv sync --locked --no-dev --python 3.15.1
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY . .
RUN mkdir -p /data
CMD ["python", "main.py"]
