"""Run any connector tool from the command line, without ChatGPT.

Starts the server over a real MCP session -- the same path the ChatGPT app
uses -- so whatever you see here is exactly what ChatGPT would see.

    python try.py                          list every available tool
    python try.py overview                 account totals
    python try.py status                   how much is indexed
    python try.py boards                   all boards with card counts
    python try.py workspaces               all workspaces
    python try.py search migraine          search every board
    python try.py search "tax office" 5    search, 5 results
    python try.py card <id-or-url>         one card, complete
    python try.py cards <board_id>         all cards on a board

Any tool can be called directly with key=value arguments:

    python try.py trello_search_cards query=invoice limit=3
    python try.py trello_board_cards board_id=abc123 full=true
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

APP = Path(__file__).resolve().parent
PYTHON = APP / ".venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = APP / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)

# Friendly names -> (tool, positional argument names)
SHORTCUTS: dict[str, tuple[str, list[str]]] = {
    "overview": ("trello_account_overview", []),
    "status": ("trello_sync_status", []),
    "boards": ("trello_list_boards", []),
    "workspaces": ("trello_list_workspaces", []),
    "search": ("trello_search_cards", ["query", "limit"]),
    "card": ("trello_get_card", ["card"]),
    "cards": ("trello_board_cards", ["board_id", "page"]),
    "sync": ("trello_refresh", []),
}

CASTS = {"limit": int, "page": int, "page_size": int, "offset": int}
BOOLS = {"true": True, "false": False, "yes": True, "no": False}


def parse_args(argv: list[str]) -> tuple[str | None, dict]:
    if not argv:
        return None, {}

    head, rest = argv[0], argv[1:]
    if head in SHORTCUTS:
        tool, positional = SHORTCUTS[head]
        args: dict = {}
        for name, value in zip(positional, [r for r in rest if "=" not in r]):
            args[name] = CASTS.get(name, str)(value)
        for item in rest:
            if "=" in item:
                k, v = item.split("=", 1)
                args[k] = BOOLS.get(v.lower(), CASTS.get(k, str)(v) if k in CASTS else v)
        return tool, args

    # Direct tool name with key=value pairs
    args = {}
    for item in rest:
        if "=" not in item:
            print(f"Ignoring '{item}' - expected key=value")
            continue
        k, v = item.split("=", 1)
        args[k] = BOOLS.get(v.lower(), CASTS.get(k, str)(v) if k in CASTS else v)
    return head, args


def shorten(value, depth: int = 0):
    """Trim the noisiest parts so a card prints readably in a terminal."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in ("limits", "pluginData", "descData", "nodeId", "aiMetadata"):
                continue
            out[k] = shorten(v, depth + 1)
        return out
    if isinstance(value, list):
        if len(value) > 12 and depth > 0:
            return [shorten(v, depth + 1) for v in value[:12]] + [f"... {len(value)-12} more"]
        return [shorten(v, depth + 1) for v in value]
    if isinstance(value, str) and len(value) > 1200:
        return value[:1200] + f"... [{len(value)} chars total]"
    return value


async def main(argv: list[str]) -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    tool, args = parse_args(argv)

    params = StdioServerParameters(
        command=str(PYTHON),
        args=[str(APP / "main.py")],
        cwd=tempfile.gettempdir(),
        env={
            **os.environ,
            "USE_CLAUDE_APP": "true",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            # Don't kick off a crawl just to answer one question.
            "TRELLO_SYNC_ON_START": "false",
        },
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=90)
            available = {t.name: t for t in (await session.list_tools()).tools}

            if tool is None:
                print(f"\n{len(available)} tools available.\n")
                print("Start with these:")
                for name in SHORTCUTS:
                    real = SHORTCUTS[name][0]
                    print(f"  python try.py {name:<12} -> {real}")
                print("\nEverything else (call with key=value):")
                for name in sorted(available):
                    if name.startswith("trello_"):
                        print(f"  {name}")
                print("\n  ...plus the live Trello tools:")
                others = sorted(n for n in available if not n.startswith("trello_"))
                print("   ", ", ".join(others[:14]))
                if len(others) > 14:
                    print(f"    ... and {len(others)-14} more")
                print()
                return 0

            if tool not in available:
                print(f"\nNo tool called '{tool}'.")
                close = [n for n in available if tool.lower() in n.lower()]
                if close:
                    print("Did you mean: " + ", ".join(close))
                print("\nRun 'python try.py' with no arguments to list everything.\n")
                return 1

            print(f"\n> {tool}({', '.join(f'{k}={v!r}' for k, v in args.items())})\n")
            result = await asyncio.wait_for(
                session.call_tool(tool, args), timeout=300
            )

            if result.isError:
                print("Error:")
                for block in result.content:
                    print(" ", getattr(block, "text", block))
                return 1

            for block in result.content:
                text = getattr(block, "text", None)
                if text is None:
                    continue
                try:
                    print(json.dumps(shorten(json.loads(text)), indent=2, ensure_ascii=False))
                except (ValueError, TypeError):
                    print(text)
            print()
            return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main(sys.argv[1:])))
    except KeyboardInterrupt:
        raise SystemExit(1)
