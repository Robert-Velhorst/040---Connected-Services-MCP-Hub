FROM python:3.15.0-slim-bookworm@sha256:122756f3fe72c4f5d3d71897888204ee85774bc79de952555b8a474e1d0a5d53

WORKDIR /app

# Install the project tools and locked runtime dependencies for Python 3.15.
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.13.1 && \
    uv sync --locked --no-dev --python 3.15.0

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Copy application code
COPY . .

# Expose port
ENV MCP_SERVER_PORT=8000
EXPOSE ${MCP_SERVER_PORT}

# Run the application
CMD ["python", "main.py"]
