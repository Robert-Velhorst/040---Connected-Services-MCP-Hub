"""Force a full re-read of Trello into the local index, now.

Normally unnecessary -- the connector refreshes itself in the background and
only re-reads boards that changed. Use this after a large reorganisation in
Trello, or to confirm the connector can still reach everything.

    .venv\\Scripts\\python.exe resync.py            # only what changed
    .venv\\Scripts\\python.exe resync.py --force    # re-read every board
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from server import settings  # noqa: E402
from server.cache.db import get_cache  # noqa: E402
from server.cache.sync import SyncEngine  # noqa: E402
from server.utils.trello_api import TrelloClient  # noqa: E402


async def main(force: bool) -> int:
    if not settings.api_key() or not settings.api_token():
        print(f"Trello credentials not found. Expected {settings.PACKAGE_ROOT / '.env'}")
        return 1

    print("Reading Trello" + (" (full rebuild)" if force else " (changed boards only)"))
    print("This can take about 90 seconds for a full rebuild.\n")

    client = TrelloClient(
        api_key=settings.api_key(),
        token=settings.api_token(),
        max_retries=settings.max_retries(),
        requests_per_second=settings.requests_per_second(),
    )
    started = time.time()
    try:
        result = await SyncEngine(client, get_cache()).sync_all(force=force)
    except Exception as error:  # noqa: BLE001
        print(f"\nRe-read failed: {error}")
        return 1
    finally:
        await client.close()

    print(f"\nDone in {time.time() - started:.0f}s")
    print(f"  workspaces      : {result['workspaces']}")
    print(f"  boards          : {result['boards_synced']} of {result['boards']} indexed")
    print(
        f"  cards           : {result['cards']}"
        f"  (active {result['cards_open']}, archived {result['cards_archived']})"
    )
    print(f"  checklist items : {result['checklist_items']}")
    print(f"  comments        : {result['comments']}")

    if result["failed"]:
        print(f"\n  {len(result['failed'])} board(s) could not be read this time:")
        for name in result["failed"][:10]:
            print(f"    - {name}")
        print("  These retry automatically on the next background refresh.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force", action="store_true", help="re-read every board, not just changed ones"
    )
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(main(args.force)))
    except KeyboardInterrupt:
        raise SystemExit(1)
