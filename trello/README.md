# Trello MCP service

The canonical Trello service in the Connected Services MCP Hub. It combines the
former lightweight connector with the full enhanced Trello MCP implementation,
derived from [m0xai/trello-mcp-server](https://github.com/m0xai/trello-mcp-server)
under the Apache-2.0 license.

It exposes typed tools for boards, lists, cards, checklists, members,
attachments, comments, labels, workspaces, custom fields, webhooks, search,
exports, analytics, batch reads and active context — plus a **complete-extraction
layer** backed by a local mirror of the whole account. The former lightweight
`overview`, `search`, `fetch` and `move_card` names remain as compatibility
aliases.

---

## Quick start (ChatGPT desktop app / Codex on Windows)

Double-click `..\install.bat`. On the first run it opens a local browser page:
enter the public Trello Power-Up API key once, then sign in and approve
read-only access in Trello. The user token is stored in Windows Credential
Manager and survives Windows restarts; it is not added to the repository or
shared Codex configuration.

The Power-Up must list `http://localhost:8765` as an allowed origin. This is
Trello's app-registration requirement; the installer cannot create an app key
on the user's behalf.

`setup_codex.py` registers the server in `~/.codex/config.toml`, which the
ChatGPT desktop app, Codex CLI and the IDE extension all share. Fully quit and
reopen the ChatGPT app; the server then appears under **Settings → MCP servers**
with an on/off toggle. The app launches the process itself — there is no service
to start, no port to open, and **no tunnel or ngrok**, because the app supports
local stdio servers directly.

```powershell
.\.venv\Scripts\python.exe setup_codex.py --check    # show current registration
.\.venv\Scripts\python.exe setup_codex.py --remove   # unregister
```

Use Python 3.12 or 3.13. The committed lockfile cannot install on 3.14 because
of its pinned `pydantic-core`.

> `mcp` must stay below 2.0. Version 2.0 removed `mcp.server.fastmcp`, which
> every tool module imports; an unpinned install resolves to 2.x and the server
> fails at import. `pyproject.toml` pins `mcp[cli]>=1.17.0,<2`.

---

## Complete extraction

Trello returns 67 top-level fields on a card. The models here previously
declared 16, and pydantic silently discards undeclared fields — so **75% of every
card was thrown away**, including `checklists` (the actual work items),
`customFieldItems`, `badges`, `dateLastActivity`, `members` and `idLabels`.
Archived cards were invisible too: `/boards/{id}/cards` returns only open cards.

Every model now inherits `extra="allow"`, and the server keeps a local SQLite
mirror so whole-account questions are answerable at all. Measured on a real
account:

| | before | after |
|---|---|---|
| Cards visible | 353 (open only) | **1,160** (807 archived included) |
| Checklist items | 0 | **7,664** |
| Comments | capped at 50/board | **13,079** |
| Fields kept per card | 16 | **65+** (everything Trello sends) |
| Search results | capped at 10 | unlimited, incl. checklist + comment text |

A full crawl of 85 boards takes ~80 s and ~17 MB. That exceeds Codex's default
60 s `tool_timeout_sec` and fits no context window, so it runs in a background
thread and the tools answer from the mirror in milliseconds.

### Cache-backed tools

| Tool | Purpose |
|---|---|
| `trello_search_cards` | Full-text search over names, descriptions, **checklist items**, comments, labels — across every board and workspace |
| `trello_get_card` | One card with every field, checklists and comments; accepts an id, shortLink or pasted URL |
| `trello_board_cards` | Paged listing of all cards on a board, archived included |
| `trello_list_boards` / `trello_list_workspaces` | Inventory with card counts |
| `trello_account_overview` | Account-wide totals and busiest boards |
| `trello_sync_status` | Mirror coverage, progress, last sync, failed boards |
| `trello_refresh` | Trigger a background refresh (reads only) |

The mirror lives at `%LOCALAPPDATA%\trello-mcp\trello_cache.db`, refreshes every
15 minutes by default, and only refetches boards whose activity timestamp
changed — an incremental pass over 85 boards takes ~5 s.

### Reliability

Trello's edge intermittently answers a valid API request with HTTP 405 and an
HTML "Human Verification" page — roughly 8–10% of requests, uncorrelated with
payload size, clearing on retry. The client treats that as transient and retries
with jittered backoff, throttles itself down when blocks cluster, and re-sweeps
any board that still failed. A board that fails is re-queued for the next pass
rather than being left stale.

Never send a browser-like `User-Agent`: a `Mozilla/5.0` UA is rejected outright
with 405, while httpx's own default is accepted.

---

## Run modes

For local stdio (ChatGPT app, Codex, Claude app), leave `USE_CLAUDE_APP=true`:

```powershell
.\.venv\Scripts\python.exe main.py
```

For a network MCP connection, set in `.env`:

```dotenv
USE_CLAUDE_APP=false
TRELLO_READ_ONLY=true
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8000
```

Then expose the server through an HTTPS reverse proxy or tunnel and connect the
client to the Streamable HTTP endpoint, normally `https://your-host.example/mcp`.
`/sse` is served as an alias so older saved connectors keep working.

---

## Security

`TRELLO_READ_ONLY=true` is a hard server-side boundary, not a label: all 65
mutation-capable tools are omitted from registration, so `delete_card`,
`delete_board` and friends are neither listed nor executable — calling one
returns `Unknown tool`. Set it to `false` only when intentional Trello changes
should be possible.

The native installer keeps the public app key under `%LOCALAPPDATA%\trello-mcp`
and the user token in Windows Credential Manager. A `.env` file remains a
gitignored compatibility option for network/Docker deployments; never add
Trello API keys, tokens, board exports or customer data to source control,
prompts, logs, issues or pull requests. See [SECURITY.md](SECURITY.md).

---

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

58 tests, no network access required — every Trello call is stubbed.
