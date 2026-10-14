"""Background crawler that keeps the local mirror complete and current.

Runs on its own daemon thread with its own event loop and its own
``TrelloClient``. That isolation is deliberate: ``httpx.AsyncClient`` binds to
the loop that created it, so sharing the module-level client with the MCP
request loop would raise "attached to a different loop" the moment both are
active.

Crawl strategy
--------------
One deep request per board pulls the board, its lists, and **every** card with
checklists, custom fields, attachments, members and stickers inlined. Measured
at ~0.6s and ~200 KB per board, that is far cheaper than walking
board -> list -> card, which is what the old tool surface forced on the client.

Comments come from ``/boards/{id}/actions?filter=commentCard`` because the
per-card default caps at 50; the board-level feed pages 1000 at a time via
``before``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Any

from server import settings
from server.cache.db import CacheDB, get_cache
from server.exceptions import TrelloMCPError
from server.utils.trello_api import TrelloClient

logger = logging.getLogger(__name__)

# Verified against the live API: this single call returns cards *including
# archived ones* with checklists and custom fields inlined.
DEEP_BOARD_PARAMS: dict[str, str] = {
    "fields": "all",
    "cards": "all",
    "card_fields": "all",
    "card_attachments": "true",
    "card_checklists": "all",
    "card_customFieldItems": "true",
    "card_stickers": "true",
    "card_pluginData": "true",
    "lists": "all",
    "labels": "all",
    "members": "all",
    "customFields": "true",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class SyncEngine:
    """Owns one crawl pass over the account."""

    def __init__(self, client: TrelloClient, cache: CacheDB):
        self.client = client
        self.cache = cache

    async def sync_all(self, force: bool = False) -> dict[str, Any]:
        started = time.monotonic()
        self.cache.set_meta("sync_state", "running")
        self.cache.set_meta("sync_started_at", _utcnow())
        self.cache.set_meta("sync_last_error", None)

        try:
            await self._sync_workspaces()
            boards = await self._fetch_boards()
        except Exception as error:  # noqa: BLE001 - recorded then re-raised
            self.cache.set_meta("sync_state", "error")
            self.cache.set_meta("sync_last_error", str(error)[:500])
            raise

        for board in boards:
            self.cache.upsert_board_stub(board)

        previous = self.cache.board_sync_state()
        pending = [b for b in boards if force or self._needs_refresh(b, previous)]

        self.cache.set_meta(
            "sync_progress",
            {"done": 0, "total": len(pending), "skipped": len(boards) - len(pending)},
        )
        logger.info(
            "Sync: %s boards total, %s need refresh, %s unchanged",
            len(boards),
            len(pending),
            len(boards) - len(pending),
        )

        semaphore = asyncio.Semaphore(settings.sync_concurrency())
        done = 0
        failed: list[str] = []
        progress_lock = asyncio.Lock()

        async def run(board: dict[str, Any]) -> None:
            nonlocal done
            async with semaphore:
                try:
                    await self._sync_board(board)
                except Exception as error:  # noqa: BLE001 - one board must not
                    # abort the crawl; record and continue.
                    logger.warning(
                        "Board %s (%s) failed: %s",
                        board.get("name"),
                        board.get("id"),
                        error,
                    )
                    self.cache.record_board_error(board.get("id", ""), str(error))
                    failed.append(board.get("name") or board.get("id") or "?")
                finally:
                    async with progress_lock:
                        done += 1
                        self.cache.set_meta(
                            "sync_progress",
                            {
                                "done": done,
                                "total": len(pending),
                                "current": board.get("name"),
                            },
                        )

        await asyncio.gather(*(run(b) for b in pending))

        # Edge blocks are transient and reputation-driven, so a board that
        # exhausted its retries mid-crawl usually succeeds once the burst is
        # over. Sweep the failures once, serially and unthrottled by
        # concurrency, rather than leaving stale data until the next pass.
        if failed:
            retry_targets = [
                b for b in pending
                if (b.get("name") or b.get("id")) in set(failed)
            ]
            logger.info("Retrying %s board(s) that failed the first pass", len(retry_targets))
            await asyncio.sleep(5)
            recovered: list[str] = []
            for board in retry_targets:
                label = board.get("name") or board.get("id") or "?"
                try:
                    await self._sync_board(board)
                    recovered.append(label)
                except Exception as error:  # noqa: BLE001
                    logger.warning("Retry of %s still failed: %s", label, error)
            if recovered:
                failed = [f for f in failed if f not in set(recovered)]
                logger.info("Recovered %s board(s) on retry", len(recovered))

        elapsed = time.monotonic() - started
        counts = self.cache.counts()
        self.cache.set_meta("sync_state", "idle")
        self.cache.set_meta("sync_finished_at", _utcnow())
        self.cache.set_meta("last_sync_seconds", round(elapsed, 1))
        self.cache.set_meta("last_sync_failed_boards", failed)
        if not failed:
            self.cache.set_meta("last_full_sync", _utcnow())

        logger.info(
            "Sync finished in %.1fs: %s cards (%s archived), %s checklist items, "
            "%s comments, %s failed boards",
            elapsed,
            counts["cards"],
            counts["cards_archived"],
            counts["checklist_items"],
            counts["comments"],
            len(failed),
        )
        return {"elapsed_seconds": round(elapsed, 1), "failed": failed, **counts}

    # ------------------------------------------------------------- internals

    def _needs_refresh(self, board: dict[str, Any], previous: dict[str, Any]) -> bool:
        state = previous.get(board.get("id", ""))
        if not state or not state.get("synced_at"):
            return True
        # A board that failed last pass must be retried, otherwise a transient
        # edge block would freeze stale data in place forever.
        if state.get("sync_error"):
            return True
        remote = board.get("dateLastActivity")
        # No activity timestamp means we cannot prove it is unchanged.
        if not remote:
            return True
        # Compare against the stamp recorded by the last *successful* pull.
        return remote != state.get("synced_activity")

    async def _sync_workspaces(self) -> None:
        orgs = await self.client.GET(
            "/members/me/organizations",
            params={"fields": "id,name,displayName,url,desc"},
        )
        if isinstance(orgs, list):
            self.cache.upsert_workspaces(orgs)

    async def _fetch_boards(self) -> list[dict[str, Any]]:
        boards = await self.client.GET(
            "/members/me/boards",
            params={
                # `filter=all` keeps closed boards in scope; the client asked for
                # everything, and closed boards still hold historic cards.
                "filter": "all",
                "fields": "id,name,closed,idOrganization,url,shortLink,dateLastActivity",
            },
        )
        return [b for b in boards if isinstance(b, dict) and b.get("id")] if isinstance(boards, list) else []

    async def _sync_board(self, board: dict[str, Any]) -> None:
        board_id = board["id"]
        deep = await self.client.GET(f"/boards/{board_id}", params=dict(DEEP_BOARD_PARAMS))
        if not isinstance(deep, dict):
            raise TrelloMCPError(f"Unexpected board payload for {board_id}")

        cards = deep.get("cards") or []
        lists = deep.get("lists") or []
        self.cache.replace_board(deep, cards, lists)

        comments = await self._fetch_comments(board_id)
        self.cache.replace_board_comments(board_id, comments)

        logger.debug(
            "Synced %s: %s cards, %s comments", board.get("name"), len(cards), len(comments)
        )

    async def _fetch_comments(self, board_id: str) -> list[dict[str, Any]]:
        """Page the board comment feed; the default cap is 50 per response."""
        page_size = settings.comment_page_limit()
        collected: list[dict[str, Any]] = []
        before: str | None = None

        for _ in range(settings.max_comment_pages()):
            params: dict[str, Any] = {
                "filter": "commentCard",
                "limit": page_size,
                "memberCreator": "true",
                "memberCreator_fields": "fullName,username",
            }
            if before:
                params["before"] = before
            batch = await self.client.GET(f"/boards/{board_id}/actions", params=params)
            if not isinstance(batch, list) or not batch:
                break
            collected.extend(batch)
            if len(batch) < page_size:
                break
            before = batch[-1].get("id")
            if not before:
                break
        return collected


class SyncWorker:
    """Daemon thread that owns the sync loop for the life of the server."""

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake = threading.Event()
        self._force = False
        self._stop = False
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._run, name="trello-sync", daemon=True
            )
            self._thread.start()
            logger.info("Background Trello sync worker started")

    def request_sync(self, force: bool = False) -> None:
        """Ask for a pass now; safe to call from the MCP request thread."""
        if force:
            self._force = True
        self._wake.set()

    def stop(self) -> None:
        self._stop = True
        self._wake.set()

    # -------------------------------------------------------------- internal

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception:  # noqa: BLE001 - a dead sync thread must never take
            # the MCP server down with it; tools keep serving cached data.
            logger.exception("Sync worker terminated unexpectedly")

    async def _main(self) -> None:
        key, token = settings.api_key(), settings.api_token()
        if not key or not token:
            logger.error("Sync worker: TRELLO_API_KEY/TRELLO_TOKEN missing")
            return

        client = TrelloClient(
            api_key=key,
            token=token,
            max_retries=settings.max_retries(),
            requests_per_second=settings.requests_per_second(),
        )
        cache = get_cache()
        engine = SyncEngine(client, cache)

        try:
            if settings.sync_on_start():
                await self._safe_pass(engine, force=False)

            interval = settings.sync_interval_seconds()
            while not self._stop:
                # Event-based wait so request_sync() interrupts the idle period.
                woke = await asyncio.get_running_loop().run_in_executor(
                    None, self._wake.wait, interval if interval > 0 else None
                )
                self._wake.clear()
                if self._stop:
                    break
                force, self._force = self._force, False
                if woke or interval > 0:
                    await self._safe_pass(engine, force=force)
        finally:
            await client.close()

    async def _safe_pass(self, engine: SyncEngine, force: bool) -> None:
        try:
            await engine.sync_all(force=force)
        except Exception as error:  # noqa: BLE001 - log and keep the loop alive
            logger.warning("Sync pass failed: %s", error)


_worker: SyncWorker | None = None
_worker_lock = threading.Lock()


def get_worker() -> SyncWorker:
    global _worker
    with _worker_lock:
        if _worker is None:
            _worker = SyncWorker()
        return _worker


def start_background_sync() -> SyncWorker:
    worker = get_worker()
    worker.start()
    return worker
