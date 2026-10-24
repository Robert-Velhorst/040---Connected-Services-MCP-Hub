# Freshdesk MCP connector

The connector provides its existing eight account, search, ticket and ping tools.
Python 3.15.1 and the complete runtime/dev/build graph are frozen in `uv.lock`.
Direct runtime selections are FastMCP 4.1.3, Requests 2.34.2, python-dotenv 1.2.4,
colorama 0.4.6 and typing-extensions 4.16.0. `requirements.txt` is the full hashed
runtime export, preserving the existing pip installation entry point.

## Installation and configuration

Use Python 3.15.1 and uv 0.13.5 in a new isolated environment, preserving any
existing installation. PyYAML 6.0.3 has no CPython 3.15 wheels; a supported C
compiler and LibYAML development headers must already be available. This source
does not install an operator SDK. Ubuntu CI builds with the current hashed
Cython/setuptools/wheel tools. Windows source-build acceptance remains separate.

```sh
uv venv --python 3.15.1
uv pip install --python .venv/bin/python --require-hashes --only-binary=:all: -r requirements-build.lock
PYYAML_FORCE_CYTHON=1 PYYAML_FORCE_LIBYAML=1 uv sync --frozen --all-groups --no-build-isolation-package pyyaml
```

Set `FRESHDESK_DOMAIN` and `FRESHDESK_API_KEY` through the intended runtime's
secret store or a private `.env` beside `main.py`; never commit credentials.
Environment variables take precedence. SSE stays on port 8001, binding to
127.0.0.1 by default. An operator may explicitly set `FRESHDESK_MCP_HOST` only
with reviewed authentication, TLS and network controls. This draft does not
start or expose a service. It does not activate a Freshdesk account or tool call.

Logs go to stderr. Optional `FRESHDESK_LOG_FILE` enables an explicit UTF-8 file.
Transport failures log their type and retry count rather than potentially
sensitive request URLs or query strings. HTTP failure status codes remain logged.

## Evidence and remaining work

The PyYAML 6.0.3 static dependency metadata is taken from its public PyPI release:
Python >=3.8 and no runtime dependencies. It lets uv resolve that source-only
release without executing its build backend just to determine metadata. CI must
still build and inspect the actual native extension; this is not a wheel or SDK
availability claim.

CI preserves the existing four mocked cases, compiles/lints source, records
actual Python/PyYAML/LibYAML versions and audits the complete frozen graph with
no advisory exclusions. No test cases are added, removed or relaxed. Preparation
runs no local application suite, native build, server or provider operation.
Full image/native currency, Windows installation, real Freshdesk authentication,
MCP transport/operator acceptance and Hetzner deployment remain unverified.
The repository-wide Hetzner deployment directive continues to apply.
