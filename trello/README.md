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

Use Python 3.15, matching the service runtime and committed lockfile. The
connector uses the MCP 2.x `MCPServer` API. Native setup additionally needs
`keyring` for Windows Credential Manager and `python-dotenv`; both are declared
in `pyproject.toml` and locked.

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

## Current SDK and runtime

The consolidated connector retains the current main branch MCP 2.x API (`MCPServer`) and Python 3.15 target. Install the locked environment with `uv sync --locked --python 3.15`; run validation with `uv run --locked --python 3.15 python -m pytest -q`. Earlier archive notes about pinning MCP below 2 apply to the pre-migration source only. Native browser consent stores tokens in Windows Credential Manager; the default Docker transport remains read-only stdio and its mirror should use a persistent volume.

## Stable dependency and image follow-up (24 October 2026)

The frozen lock refreshes certifi 2026.10.23, httpcore2/httpx2 2.16.0,
Starlette 1.9.0, pluggy 1.7.0 and pycparser 3.12 from current public stable
metadata. Python stays at the security release 3.15.1 and uv at 0.13.5.
The earlier #88 image moved from Debian Bookworm to Trixie. The native
candidate below now uses pinned official Alpine 3.24 images and current
distribution updates in its disposable build. No operator installation or persistent database is
modified by preparing these sources.

CI retains the existing source checks, adds an unsuppressed full dependency
audit, builds the image and records its actual Python, SQLite, TLS, CA roots,
installed packages and native module hashes. The inspector does not start the
connector, read credentials, open its mirror or call Trello. Version metadata
is not full native-component currency or a complete image vulnerability scan.
Existing boolean-returning test warnings limit the source suite's assurance;
no tests are removed or relaxed. Freshdesk installed/runtime acceptance, actual
Trello credentials, mirror recovery and Hetzner deployment remain separate.

## Native runtime candidate and cutover requirements

This separate candidate follows #88 at d7a0d75751906193668cbb1a97b2dde80ad532a9.
The disposable SDK builds checksum-verified upstream SQLite 3.54.1 and OpenSSL
4.1.0, rebuilds exact CPython 3.15.1 SSL/hash modules, and compiles cryptography
50.0.2 against the same TLS libraries using Rust 1.99.1. Native libraries are
registered in signed Alpine packages with upstream provenance/license
information. Ephemeral signing private keys stay in the disposable SDK and
are removed in the same build step; final installation verifies packages
using only their public keys, with no global trust-store changes.
All runtime wheels are installed offline from generated SHA-256 locks; build
tools, pip and ensurepip are excluded from the final runtime.

The image runs as UID/GID 10001. Compose preserves the installed image source
and environment rather than mounting the checkout over `/app`. Mirror storage
uses its dedicated named volume; ports bind to loopback, the root filesystem
is read-only, capabilities are dropped, and temporary writes go to a bounded
private tmpfs. No existing volume, mirror or operator installation is changed
by preparing this source.

**Before applying the new Compose definition to an existing installation:**
stop its writers, locate and preserve its current mirror plus WAL/SHM files
and a coherent SQLite backup, record container/volume identities and rollback
configuration, then have the operator copy/restore the reviewed mirror into
the intended volume with UID/GID 10001 ownership. Verify integrity, record
counts, read-only tool boundaries and rollback using the preserved backup.
Do not run `down -v`, discard the old container/data, or assume a new empty
volume contains existing history. No automatic copy, ownership change or
operator migration is performed by this draft.

CI requires installed library/module/package identities, the unchanged source
cases against the image using pure-Python qualification tools and synthetic
credentials with no network, and a complete raw image scan tied to the saved
image configuration. No test case or advisory exclusion is added or relaxed.
Legacy boolean-return warnings still limit the source suite's assurance.
The previous #88 evidence does not qualify this native candidate. Real Trello,
Freshdesk, operator mirror recovery and Hetzner deployment remain unverified;
compatibility system libraries and Rust crate currency are not declared fully
current merely because the selected application libraries build.

### Image operating-system correction

At e3c9d8c, native inspection and all 65 existing image cases passed, but the
complete unsuppressed Trivy report identified 164 Debian package findings
(44 high, 58 medium, 61 low, one unknown); none recorded a fixed version.
The 46 installed Python packages had no reported findings. This candidate
changes the actual runtime to supported stable Alpine 3.24 rather than
ignoring Debian findings or stripping inventory. The same pinned application
libraries are rebuilt for musl, with signed package metadata and full OS and
Python inventories retained. Native inspection, unchanged cases and the full
raw scan must qualify the new image before it can be considered ready.
The libc and base-system change requires this fresh compatibility evidence;
previous Debian results do not qualify the Alpine image. This draft changes
no host installation, mirror, credentials or running deployment.
