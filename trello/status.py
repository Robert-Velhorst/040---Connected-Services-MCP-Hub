"""Report how much of the Trello account is currently indexed locally."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.cache.db import get_cache  # noqa: E402


def main() -> int:
    cache = get_cache()
    counts = cache.counts()

    print(f"  workspaces      : {counts['workspaces']}")
    print(
        f"  boards          : {counts['boards']}"
        f"  (indexed {counts['boards_synced']}, failed {counts['boards_failed']})"
    )
    print(
        f"  cards           : {counts['cards']}"
        f"  (active {counts['cards_open']}, archived {counts['cards_archived']})"
    )
    print(f"  checklist items : {counts['checklist_items']}")
    print(f"  comments        : {counts['comments']}")
    print(f"  last full sync  : {cache.get_meta('last_full_sync') or 'never'}")
    print(f"  search index    : {'on' if cache.fts_enabled else 'basic'}")

    state = cache.get_meta("sync_state", "never_run")
    progress = cache.get_meta("sync_progress") or {}
    if state == "running":
        print(
            f"  status          : indexing now"
            f" ({progress.get('done', 0)}/{progress.get('total', '?')} boards)"
        )
    else:
        print(f"  status          : {state}")

    failed = cache.get_meta("last_sync_failed_boards") or []
    if failed:
        print(f"  boards that failed last pass: {', '.join(str(f) for f in failed[:5])}")

    if counts["boards_synced"] == 0:
        print()
        print("  The index is still empty. Open the ChatGPT app and ask it for a")
        print("  Trello overview - that starts the first index build.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
