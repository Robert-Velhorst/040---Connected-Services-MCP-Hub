"""Cache-backed tools for complete extraction across every board and workspace.

These are the tools an assistant should reach for when the question spans the
whole account. They answer from the local mirror, so a query touching 85 boards
returns in milliseconds instead of the ~100s a live crawl needs -- comfortably
inside Codex's 60s ``tool_timeout_sec``.

Every card is returned with all fields Trello sent, including checklists and
archived cards, both of which the live tool surface used to drop.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from server import settings
from server.cache.db import get_cache
from server.cache.sync import get_worker

logger = logging.getLogger(__name__)

MAX_PAGE_SIZE = 200

# Key under which the runtime archived-visibility choice is persisted.
_ARCHIVED_PREF = "pref_include_archived"


def _archived_default() -> bool:
    """Current default for showing archived cards.

    A value set at runtime wins over the .env setting; if neither is present,
    fall back to including them.
    """
    stored = get_cache().get_meta(_ARCHIVED_PREF)
    if isinstance(stored, bool):
        return stored
    return settings.include_archived_default()


def _resolve_archived(explicit: bool | None) -> bool:
    """A per-call argument always beats the saved preference."""
    return _archived_default() if explicit is None else bool(explicit)


def _sync_snapshot() -> dict[str, Any]:
    cache = get_cache()
    progress = cache.get_meta("sync_progress") or {}
    state = cache.get_meta("sync_state", "never_run")
    counts = cache.counts()
    ready = counts["boards_synced"] > 0
    return {
        "state": state,
        "ready": ready,
        "progress": progress,
        "last_full_sync": cache.get_meta("last_full_sync"),
        "last_sync_seconds": cache.get_meta("last_sync_seconds"),
        "failed_boards": cache.get_meta("last_sync_failed_boards") or [],
        "last_error": cache.get_meta("sync_last_error"),
        "counts": counts,
    }


def _warming_note(snapshot: dict[str, Any]) -> str | None:
    if snapshot["ready"]:
        return None
    if snapshot["state"] == "running":
        p = snapshot["progress"]
        return (
            f"First sync in progress ({p.get('done', 0)}/{p.get('total', '?')} boards). "
            "Results are incomplete until it finishes; call trello_sync_status again shortly."
        )
    return (
        "The local mirror is empty. Call trello_refresh to populate it, then retry."
    )


async def trello_sync_status() -> dict[str, Any]:
    """Report mirror coverage: how much of the Trello account is cached locally.

    Call this first when you need to know whether an answer is based on the
    complete account. Reports per-entity counts, the last successful sync, and
    any boards that failed.

    Returns:
        dict: state, readiness, progress, counts of workspaces/boards/cards/
        checklist items/comments, and any failed boards.
    """
    return await asyncio.to_thread(_sync_snapshot)


async def trello_refresh(board_id: str | None = None, force: bool = False) -> dict[str, Any]:
    """Trigger a background refresh of the local mirror.

    This only reads from Trello; it never modifies Trello data. Returns
    immediately -- the crawl continues in the background, so poll
    trello_sync_status to watch it complete.

    Args:
        board_id (str, optional): Currently advisory; a full incremental pass
            runs regardless, skipping boards whose activity timestamp is
            unchanged.
        force (bool): Re-pull every board even if it looks unchanged.

    Returns:
        dict: Acknowledgement plus the current sync snapshot.
    """
    worker = get_worker()
    worker.start()
    worker.request_sync(force=force)
    snapshot = await asyncio.to_thread(_sync_snapshot)
    return {
        "requested": True,
        "force": force,
        "board_id": board_id,
        "note": "Refresh running in background; poll trello_sync_status.",
        "sync": snapshot,
    }


async def trello_set_archived_visibility(include_archived: bool) -> dict[str, Any]:
    """Turn archived cards on or off for all later searches and listings.

    Use this when the user says something like "stop showing me archived
    cards", "only active cards from now on", or "include archived again".
    The choice is remembered until changed, so it does not need repeating.

    This changes only what is shown. Archived cards stay in the local mirror
    either way, so switching back is instant and never needs a re-sync, and
    nothing in Trello is modified.

    Args:
        include_archived (bool): True to show archived cards alongside active
            ones; False to show only active cards.

    Returns:
        dict: the new setting, the previous one, and how many cards each
        choice covers.
    """

    def run() -> dict[str, Any]:
        cache = get_cache()
        previous = _archived_default()
        cache.set_meta(_ARCHIVED_PREF, bool(include_archived))
        counts = cache.counts()
        return {
            "include_archived": bool(include_archived),
            "previous": previous,
            "visible_cards": counts["cards"] if include_archived else counts["cards_open"],
            "total_cards": counts["cards"],
            "archived_cards": counts["cards_archived"],
            "note": (
                "Archived cards will now be included."
                if include_archived
                else f"Archived cards are now hidden; {counts['cards_archived']} "
                     "cards are excluded. They remain indexed, so turning this "
                     "back on is instant."
            ),
        }

    return await asyncio.to_thread(run)


async def trello_get_settings() -> dict[str, Any]:
    """Show the connector's current display settings.

    Returns:
        dict: whether archived cards are currently included, where that value
        came from, and how many cards are visible as a result.
    """

    def run() -> dict[str, Any]:
        cache = get_cache()
        stored = cache.get_meta(_ARCHIVED_PREF)
        archived = _archived_default()
        counts = cache.counts()
        return {
            "include_archived": archived,
            "source": "set in this conversation" if isinstance(stored, bool)
                      else "default from .env (TRELLO_INCLUDE_ARCHIVED_DEFAULT)",
            "visible_cards": counts["cards"] if archived else counts["cards_open"],
            "total_cards": counts["cards"],
            "archived_cards": counts["cards_archived"],
            "how_to_change": "Call trello_set_archived_visibility(include_archived=false)",
        }

    return await asyncio.to_thread(run)


async def trello_search_cards(
    query: str,
    limit: int = 25,
    offset: int = 0,
    board_id: str | None = None,
    include_archived: bool | None = None,
) -> dict[str, Any]:
    """Full-text search across EVERY card in EVERY board and workspace.

    Searches card names, descriptions, checklist item text, comment text,
    labels, board names and list names. Archived cards are included by default
    because they hold most of the history on this account.

    Args:
        query (str): Words to look for. Terms are ANDed. Append '*' to a term
            for prefix matching, e.g. "invoic*".
        limit (int): Results to return, 1-200. Defaults to 25.
        offset (int): Results to skip, for paging through a large result set.
        board_id (str, optional): Restrict the search to one board.
        include_archived (bool, optional): Include archived cards. When
            omitted, uses the saved preference - see
            trello_set_archived_visibility.

    Returns:
        dict: total match count, the requested page of hits (each with id,
        name, board, list, url, due date, checklist item count and a matching
        snippet), and a sync note if the mirror is still warming.
    """
    limit = max(1, min(int(limit), MAX_PAGE_SIZE))
    offset = max(0, int(offset))

    def run() -> dict[str, Any]:
        cache = get_cache()
        archived = _resolve_archived(include_archived)
        hits, total = cache.search(
            query,
            limit=limit,
            offset=offset,
            board_id=board_id,
            include_archived=archived,
        )
        snapshot = _sync_snapshot()
        result: dict[str, Any] = {
            "query": query,
            "total_matches": total,
            "returned": len(hits),
            "offset": offset,
            "archived_included": archived,
            "results": hits,
        }
        note = _warming_note(snapshot)
        if note:
            result["sync_note"] = note
        if total > offset + len(hits):
            result["next_offset"] = offset + len(hits)
        return result

    return await asyncio.to_thread(run)


async def trello_get_card(card: str, include_comments: bool = True) -> dict[str, Any]:
    """Fetch one card with EVERY field Trello holds for it.

    Includes checklists with all check items, custom field values, attachments,
    members, labels, badges and dates -- the data the previous implementation
    silently discarded.

    Args:
        card (str): Card id, shortLink, or a pasted trello.com/c/... URL.
        include_comments (bool): Attach the card's comment history.

    Returns:
        dict: The complete card object, plus comments and a derived summary of
        checklist progress.
    """

    def run() -> dict[str, Any]:
        cache = get_cache()
        found = cache.get_card(card)
        if found is None:
            snapshot = _sync_snapshot()
            return {
                "found": False,
                "error": f"No cached card matches {card!r}.",
                "hint": _warming_note(snapshot)
                or "Check the id, or call trello_refresh if the card is new.",
            }

        checklists = found.get("checklists") or []
        total_items = sum(len(c.get("checkItems") or []) for c in checklists)
        complete_items = sum(
            1
            for c in checklists
            for i in (c.get("checkItems") or [])
            if i.get("state") == "complete"
        )
        payload: dict[str, Any] = {
            "found": True,
            "card": found,
            "summary": {
                "name": found.get("name"),
                "archived": bool(found.get("closed")),
                "url": found.get("shortUrl") or found.get("url"),
                "checklists": len(checklists),
                "checklist_items": total_items,
                "checklist_complete": complete_items,
                "attachments": len(found.get("attachments") or []),
                "custom_fields": len(found.get("customFieldItems") or []),
            },
        }
        if include_comments and found.get("id"):
            payload["comments"] = cache.get_card_comments(found["id"])
        return payload

    return await asyncio.to_thread(run)


async def trello_list_workspaces() -> dict[str, Any]:
    """List every workspace (organization) the account belongs to.

    Returns:
        dict: workspaces with id, name, display name and board count.
    """

    def run() -> dict[str, Any]:
        cache = get_cache()
        workspaces = cache.list_workspaces()
        return {"count": len(workspaces), "workspaces": workspaces}

    return await asyncio.to_thread(run)


async def trello_list_boards(
    include_closed: bool = True, workspace_id: str | None = None
) -> dict[str, Any]:
    """List every board, with card counts and sync state.

    Args:
        include_closed (bool): Include closed/archived boards. Defaults to True.
        workspace_id (str, optional): Restrict to one workspace.

    Returns:
        dict: boards with id, name, workspace, card and archived-card counts,
        last activity, and any sync error.
    """

    def run() -> dict[str, Any]:
        cache = get_cache()
        boards = cache.list_boards(include_closed=include_closed)
        if workspace_id:
            boards = [b for b in boards if b.get("id_organization") == workspace_id]
        snapshot = _sync_snapshot()
        result = {"count": len(boards), "boards": boards}
        note = _warming_note(snapshot)
        if note:
            result["sync_note"] = note
        return result

    return await asyncio.to_thread(run)


async def trello_board_cards(
    board_id: str,
    page: int = 1,
    page_size: int = 25,
    include_archived: bool | None = None,
    full: bool = False,
) -> dict[str, Any]:
    """Page through every card on a board, including archived ones.

    The live Trello endpoint hides archived cards -- on this account that is
    typically the majority of a board's history -- so this tool includes them
    by default.

    Args:
        board_id (str): The board id.
        page (int): 1-based page number.
        page_size (int): Cards per page, 1-200. Defaults to 25.
        include_archived (bool, optional): Include archived cards. When
            omitted, uses the saved preference - see
            trello_set_archived_visibility.
        full (bool): Return complete card objects. Defaults to False, which
            returns a compact summary per card to keep responses small; set
            True when you need checklists and custom fields inline.

    Returns:
        dict: total card count, page metadata, and the cards.
    """
    page = max(1, int(page))
    page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
    offset = (page - 1) * page_size

    def run() -> dict[str, Any]:
        cache = get_cache()
        archived = _resolve_archived(include_archived)
        cards, total = cache.board_cards(
            board_id,
            include_archived=archived,
            offset=offset,
            limit=page_size,
        )
        if not full:
            cards = [_compact(c) for c in cards]
        pages = (total + page_size - 1) // page_size if page_size else 1
        result: dict[str, Any] = {
            "board_id": board_id,
            "total_cards": total,
            "page": page,
            "page_size": page_size,
            "total_pages": pages,
            "archived_included": archived,
            "cards": cards,
        }
        if page < pages:
            result["next_page"] = page + 1
        return result

    return await asyncio.to_thread(run)


async def trello_account_overview() -> dict[str, Any]:
    """Account-wide totals: workspaces, boards, cards, checklist items, comments.

    Use this to size an analysis before drilling in.

    Returns:
        dict: aggregate counts, the busiest boards, and sync freshness.
    """

    def run() -> dict[str, Any]:
        cache = get_cache()
        snapshot = _sync_snapshot()
        boards = cache.list_boards(include_closed=True)
        busiest = sorted(boards, key=lambda b: b.get("cards") or 0, reverse=True)[:15]
        archived = _archived_default()
        return {
            "totals": snapshot["counts"],
            "settings": {
                "include_archived": archived,
                "visible_cards": (
                    snapshot["counts"]["cards"] if archived
                    else snapshot["counts"]["cards_open"]
                ),
            },
            "sync": {
                "state": snapshot["state"],
                "ready": snapshot["ready"],
                "last_full_sync": snapshot["last_full_sync"],
                "last_sync_seconds": snapshot["last_sync_seconds"],
                "failed_boards": snapshot["failed_boards"],
            },
            "busiest_boards": [
                {
                    "id": b["id"],
                    "name": b["name"],
                    "workspace": b.get("workspace"),
                    "cards": b.get("cards"),
                    "archived": b.get("archived"),
                }
                for b in busiest
            ],
        }

    return await asyncio.to_thread(run)


def _compact(card: dict[str, Any]) -> dict[str, Any]:
    """Small per-card summary for listings; `full=True` returns everything."""
    checklists = card.get("checklists") or []
    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "archived": bool(card.get("closed")),
        "url": card.get("shortUrl") or card.get("url"),
        "idList": card.get("idList"),
        "due": card.get("due"),
        "dueComplete": card.get("dueComplete"),
        "dateLastActivity": card.get("dateLastActivity"),
        "labels": [l.get("name") or l.get("color") for l in (card.get("labels") or [])],
        "desc_preview": (card.get("desc") or "")[:280],
        "checklist_items": sum(len(c.get("checkItems") or []) for c in checklists),
        "attachments": len(card.get("attachments") or []),
    }
