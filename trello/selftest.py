"""Post-install check: can the server start, authenticate and read Trello?

Run by install.bat. Prints plain-language results and exits non-zero on a
failure the client needs to act on, so the installer can stop early rather than
registering a server that will not work.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def fail(message: str, hint: str = "") -> int:
    print(f"       [X] {message}")
    if hint:
        print(f"           {hint}")
    return 1


async def main() -> int:
    try:
        from server import settings
    except Exception as error:  # noqa: BLE001
        return fail(f"Could not load the server: {error}")

    if not settings.api_key() or not settings.api_token():
        return fail(
            "Trello credentials not found.",
            f"Expected them in {settings.PACKAGE_ROOT / '.env'}",
        )

    from server.utils.trello_api import TrelloClient

    client = TrelloClient(
        api_key=settings.api_key(),
        token=settings.api_token(),
        max_retries=settings.max_retries(),
        requests_per_second=settings.requests_per_second(),
    )
    try:
        try:
            me = await client.GET("/members/me", params={"fields": "username,fullName"})
        except Exception as error:  # noqa: BLE001
            text = str(error).lower()
            if "invalid" in text or "401" in text or "unauthorized" in text:
                return fail(
                    "Trello rejected the API key or token.",
                    "Check them at https://trello.com/power-ups/admin and re-run install.bat",
                )
            return fail(f"Could not reach Trello: {error}")

        name = me.get("fullName") or me.get("username")
        print(f"       Connected to Trello as: {name}")

        boards = await client.GET(
            "/members/me/boards", params={"filter": "all", "fields": "id"}
        )
        orgs = await client.GET("/members/me/organizations", params={"fields": "id"})
        print(
            f"       Visible to the connector: {len(boards)} boards, "
            f"{len(orgs)} workspaces"
        )
    finally:
        await client.close()

    mode = "read-only (cannot change anything in Trello)" if settings.read_only() else "READ-WRITE"
    print(f"       Access mode: {mode}")
    print(f"       Local index will be stored at: {settings.db_path()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(1)
