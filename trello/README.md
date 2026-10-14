# Trello MCP service

This is the canonical Trello service in the Connected Services MCP Hub. It
combines the former lightweight connector with the full enhanced Trello MCP
implementation, which is derived from
[m0xai/trello-mcp-server](https://github.com/m0xai/trello-mcp-server) under the
Apache-2.0 license.

It provides typed tools for boards, lists, cards, checklists, members,
attachments, comments, labels, workspaces, custom fields, webhooks, search,
exports, analytics, batch reads, and active context. The former lightweight
`overview`, `search`, `fetch`, and `move_card` tool names remain as
compatibility aliases.

## Install and configure

```powershell
Copy-Item .env.example .env
# Set TRELLO_API_KEY and TRELLO_TOKEN in .env.
uv sync --locked --python 3.15
```

Use Python 3.15, the service runtime and lockfile target.

## Run modes

For local stdio/Claude-app mode, leave `USE_CLAUDE_APP=true` and run:

```powershell
uv run --python 3.15 python main.py
```

For a network MCP connection such as ChatGPT, set these values in `.env`:

```dotenv
USE_CLAUDE_APP=false
TRELLO_READ_ONLY=true
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8000
```

Then run the same command and expose the server through an HTTPS reverse proxy
or tunnel. Connect the client to the Streamable HTTP endpoint, normally
`https://your-host.example/mcp`.

`TRELLO_READ_ONLY=true` is a hard server-side boundary: all mutation-capable
tools are omitted from tool discovery. Use it for read/fetch integrations. Set
it to `false` only when intentional Trello changes should be possible.

## Security

Never add Trello API keys, tokens, board exports, or customer data to source
control, prompts, logs, issues, or pull requests. See [SECURITY.md](SECURITY.md)
for the project's full handling guidance.

## Validation

```powershell
uv run --python 3.15 --with pytest pytest -q
```
