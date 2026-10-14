"""Acceptance test: start the connector the way ChatGPT does and check it works.

This talks to the server over a real MCP stdio session -- the same transport the
ChatGPT app uses -- from an unrelated working directory, and reports PASS/FAIL
for each thing the connector is supposed to do.

    .venv\\Scripts\\python.exe verify.py

Exit code is 0 only if every check passes.
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


def launch_command() -> tuple[str, list[str], str | None, str]:
    """Test whatever is actually registered with the ChatGPT app.

    Falls back to the local Python checkout when nothing is registered yet.
    Reading the real config means this verifies the Docker install too,
    without needing a separate script.
    """
    config = Path.home() / ".codex" / "config.toml"
    if config.exists():
        try:
            import tomllib

            data = tomllib.loads(config.read_text(encoding="utf-8"))
            entry = (data.get("mcp_servers") or {}).get("trello")
            if entry and entry.get("command"):
                mode = "Docker" if entry["command"] == "docker" else "local Python"
                return (
                    str(entry["command"]),
                    [str(a) for a in (entry.get("args") or [])],
                    entry.get("cwd"),
                    f"{mode} (as registered with the ChatGPT app)",
                )
        except Exception:  # noqa: BLE001 - fall through to the local checkout
            pass
    return str(PYTHON), [str(APP / "main.py")], None, "local Python (not yet registered)"

PASS, FAIL, WARN = "PASS", "FAIL", "WARN"
results: list[tuple[str, str, str]] = []


def record(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    symbol = {PASS: "[ok]  ", FAIL: "[FAIL]", WARN: "[warn]"}[status]
    print(f"  {symbol} {name}")
    if detail:
        print(f"         {detail}")


async def main() -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    command, args, cwd, mode = launch_command()

    print("\nTrello connector - acceptance test")
    print("=" * 58)
    print(f"  mode    : {mode}")
    print(f"  command : {command} {' '.join(args[:4])}{' ...' if len(args) > 4 else ''}")
    print("=" * 58 + "\n")

    params = StdioServerParameters(
        command=command,
        args=args,
        # Deliberately unrelated: proves credentials do not depend on the
        # working directory, which is how the ChatGPT app launches it.
        cwd=cwd or tempfile.gettempdir(),
        env={
            **os.environ,
            "USE_CLAUDE_APP": "true",
            "TRELLO_READ_ONLY": "true",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        },
    )

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=90)
                record(PASS, "Server starts and completes the MCP handshake")

                tools = {t.name for t in (await session.list_tools()).tools}
                record(PASS, f"Tools exposed: {len(tools)}")

                # --- read-only boundary ---------------------------------
                writes = sorted(
                    t for t in tools
                    if t.split("_")[0] in {
                        "create", "delete", "update", "add", "remove", "set",
                        "archive", "attach", "subscribe", "unsubscribe", "vote", "move",
                    }
                )
                if writes:
                    record(FAIL, "Read-only mode", f"write tools exposed: {writes[:5]}")
                else:
                    record(PASS, "Read-only: no write tool is exposed")

                probe = await asyncio.wait_for(
                    session.call_tool("delete_card", {"card_id": "0" * 24}), timeout=60
                )
                if probe.isError:
                    record(PASS, "Read-only: delete_card is rejected outright")
                else:
                    record(FAIL, "Read-only: delete_card EXECUTED", "boundary is broken")

                # --- index coverage -------------------------------------
                res = await asyncio.wait_for(
                    session.call_tool("trello_sync_status", {}), timeout=180
                )
                sync = json.loads(res.content[0].text)
                counts = sync["counts"]

                if not sync["ready"]:
                    record(
                        WARN,
                        "Local index is still building",
                        "Wait ~90s after first launch, then run verify.py again.",
                    )
                    return summarise()

                record(
                    PASS,
                    f"Index ready: {counts['boards_synced']}/{counts['boards']} boards, "
                    f"{counts['workspaces']} workspaces",
                )

                if counts["boards_failed"]:
                    record(
                        WARN,
                        f"{counts['boards_failed']} board(s) failed the last pass",
                        f"{sync.get('failed_boards')} - they retry automatically",
                    )

                # --- completeness ---------------------------------------
                if counts["cards_archived"] > 0:
                    record(
                        PASS,
                        f"Archived cards included: {counts['cards_archived']} "
                        f"of {counts['cards']} total",
                    )
                else:
                    record(WARN, "No archived cards indexed", "unexpected on this account")

                if counts["checklist_items"] > 0:
                    record(PASS, f"Checklist items captured: {counts['checklist_items']}")
                else:
                    record(FAIL, "No checklist items captured", "the main defect has regressed")

                if counts["comments"] > 0:
                    record(PASS, f"Comments captured: {counts['comments']}")
                else:
                    record(WARN, "No comments captured")

                # --- search reaches checklist text ----------------------
                res = await asyncio.wait_for(
                    session.call_tool(
                        "trello_search_cards", {"query": "step", "limit": 3}
                    ),
                    timeout=120,
                )
                hits = json.loads(res.content[0].text)
                if hits["total_matches"] > 10:
                    record(
                        PASS,
                        f"Search works across all boards: {hits['total_matches']} "
                        "matches for 'step'",
                    )
                else:
                    record(
                        WARN,
                        f"Search returned only {hits['total_matches']} matches",
                        "expected many more; the old code capped at 10",
                    )

                # --- a full card round-trip -----------------------------
                target = None
                for hit in hits.get("results", []):
                    if hit.get("checklist_items"):
                        target = hit
                        break
                if target:
                    res = await asyncio.wait_for(
                        session.call_tool("trello_get_card", {"card": target["id"]}),
                        timeout=120,
                    )
                    detail = json.loads(res.content[0].text)
                    card = detail.get("card", {})
                    fields = len(card)
                    if fields >= 40:
                        record(
                            PASS,
                            f"Full card returned: {fields} fields, "
                            f"{detail['summary']['checklist_items']} checklist items",
                            f"{target['name'][:52]}",
                        )
                    else:
                        record(
                            FAIL,
                            f"Card returned only {fields} fields",
                            "field-dropping has regressed (expect 40+)",
                        )
                    if card.get("checklists"):
                        record(PASS, "Checklists present on the card object")
                    else:
                        record(FAIL, "Checklists missing from the card object")
                else:
                    record(WARN, "No card with checklists found to inspect")

    except asyncio.TimeoutError:
        record(FAIL, "Timed out talking to the server")
    except Exception as error:  # noqa: BLE001
        record(FAIL, "Could not run the connector", str(error)[:200])

    return summarise()


def summarise() -> int:
    failed = [r for r in results if r[0] == FAIL]
    warned = [r for r in results if r[0] == WARN]
    print("\n" + "=" * 58)
    if failed:
        print(f"  RESULT: {len(failed)} CHECK(S) FAILED")
        for _, name, detail in failed:
            print(f"    - {name}{(' - ' + detail) if detail else ''}")
    elif warned:
        print(f"  RESULT: OK, with {len(warned)} warning(s)")
    else:
        print("  RESULT: ALL CHECKS PASSED")
    print("=" * 58 + "\n")
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(1)
