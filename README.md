# Connected Services MCP Hub

This private MCP hub connects ChatGPT to business systems and operational
data. Each service is independently configured so credentials and access
boundaries stay scoped to the external system.

## Services

| Service | Directory | Default port | Required environment variables |
| --- | --- | --- | --- |
| Freshdesk | `freshdesk/` | 8001 | `FRESHDESK_DOMAIN`, `FRESHDESK_API_KEY` |
| Trello | `trello/` | 8000 | `TRELLO_API_KEY`, `TRELLO_TOKEN` |

The Trello service is the canonical, full-featured implementation. It
consolidates the former lightweight connector and enhanced Trello server in
one location. The lightweight `overview`, `search`, `fetch`, and `move_card`
tool names remain available as compatibility aliases; use the typed Trello
tools for all new integrations.

## Run Freshdesk

```powershell
cd freshdesk
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Fill in the service credentials in .env, then:
python main.py
```

## Run Trello

The Trello server includes board, list, card, checklist, collaboration,
analytics, export, and automation tools. It is derived from
[m0xai/trello-mcp-server](https://github.com/m0xai/trello-mcp-server), retained
under its Apache-2.0 license, and incorporates upstream PRs #11, #20, #21,
#23, and #27 plus the current upstream checkitem fix.

```powershell
cd trello
Copy-Item .env.example .env
# Set TRELLO_API_KEY and TRELLO_TOKEN in .env.
# For a ChatGPT read/fetch connector, also set:
# TRELLO_READ_ONLY=true
# For a network MCP connection, set:
# USE_CLAUDE_APP=false
uv sync --locked --python 3.15
uv run --python 3.15 python main.py
```

`TRELLO_READ_ONLY=true` is a server-side access boundary: mutation tools are
not registered or exposed to the client. The server uses Streamable HTTP in
network mode; connect your MCP client to the externally exposed endpoint
(normally `/mcp`). Do not commit `.env` files, generated logs, board exports,
or Trello credentials.

The Trello lockfile supports Python 3.12 and 3.13; its pinned `pydantic-core`
does not currently build on Python 3.14.
