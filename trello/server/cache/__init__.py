"""Local mirror of the Trello account.

A full account crawl measured ~1,669 cards / ~13,160 checklist items / ~16.7 MB
of JSON across 85 boards, taking ~100s. Codex's default ``tool_timeout_sec`` is
60 and no context window holds 16.7 MB, so live-per-request extraction cannot
satisfy "pull everything across all boards and workspaces". This package keeps a
complete local copy so tools answer in milliseconds and nothing is truncated.
"""

from server.cache.db import CacheDB, get_cache

__all__ = ["CacheDB", "get_cache"]
