# Stdio connector; credentials are supplied at runtime and never baked in.
FROM python:3.15.1-slim-bookworm@sha256:575f8bc12ec26542e0678bc6b60e385218248019d433157ec327264a78c3a853
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 PYTHONIOENCODING=utf-8 USE_CLAUDE_APP=true TRELLO_READ_ONLY=true TRELLO_MCP_DB_PATH=/data/trello_cache.db
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.13.5 && uv sync --locked --no-dev --python 3.15.1
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
COPY . .
RUN mkdir -p /data
CMD ["python", "main.py"]
