"""Regression coverage for the complete-extraction fixes.

Each test pins one defect that made Codex unable to see all card data.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx
import pytest

os.environ["TRELLO_API_KEY"] = "test_key"
os.environ["TRELLO_TOKEN"] = "test_token"
sys.path.insert(0, str(Path(__file__).parent))

from server.cache.db import CacheDB
from server.exceptions import TransientBlockError
from server.models import TrelloCard
from server.services.card import CardService
from server.services.search import SearchService
from server.utils.trello_api import TrelloClient, _RateLimiter


# --------------------------------------------------------------- field loss

# Abridged from a real card on the account: Trello sends 67 top-level keys,
# the old model declared 16 and silently dropped the rest.
REAL_CARD = {
    "id": "60ed46ce677e4c5e34c331d3",
    "name": "Reimbursement health insurance daylight therapy glasses",
    "desc": "Original description",
    "closed": False,
    "idList": "5fbacb5710990009decabf50",
    "idBoard": "5fbacb5710990009decabf4f",
    "url": "https://trello.com/c/pcocKQlk/10-reimbursement",
    "pos": 65535,
    "shortLink": "pcocKQlk",
    "shortUrl": "https://trello.com/c/pcocKQlk",
    "idShort": 10,
    "dateLastActivity": "2026-06-24T22:21:39.883Z",
    "idOrganization": "5fb422f4f49e837666014b5d",
    "badges": {"checkItems": 17, "checkItemsChecked": 0, "comments": 2},
    "checklists": [
        {
            "id": "6934b970f20b9317209b5499",
            "name": "APTLSS",
            "checkItems": [
                {"id": "i1", "name": "Step 1: Analyze existing doc", "state": "incomplete"},
                {"id": "i2", "name": "Step 2: Identify and list all", "state": "complete"},
                {"id": "i3", "name": "Step 3: Review Dutch healthcare", "state": "incomplete"},
            ],
        }
    ],
    "customFieldItems": [{"id": "cf1", "idCustomField": "f1", "value": {"text": "high"}}],
    "idChecklists": ["6934b970f20b9317209b5499"],
    "idLabels": ["lab1"],
    "idMemberCreator": "59b3208fbd9a6b2be8b0a436",
    "members": [{"id": "59b3208fbd9a6b2be8b0a436", "fullName": "Noodzakelijk Online"}],
    "start": None,
    "dueReminder": -1,
    "isTemplate": False,
    "pinned": False,
    "manualCoverAttachment": True,
    "locationName": None,
    "stickers": [],
    "pluginData": [],
    "limits": {"attachments": {"perCard": {"status": "ok"}}},
    "nodeId": "ari:cloud:trello::card/workspace/x/y",
}


def test_card_model_preserves_every_field_trello_sends():
    """The core defect: pydantic silently discarded 75% of each card."""
    card = TrelloCard(**REAL_CARD)
    dumped = card.model_dump()

    # Fields the old 16-field model dropped entirely.
    for field in (
        "checklists",
        "customFieldItems",
        "badges",
        "dateLastActivity",
        "idShort",
        "shortUrl",
        "idLabels",
        "idMemberCreator",
        "members",
        "isTemplate",
    ):
        assert field in dumped, f"{field} was dropped by the model"

    # Even fields the model has never heard of must survive.
    for extra in ("nodeId", "limits", "pinned", "manualCoverAttachment", "dueReminder"):
        assert extra in dumped, f"undeclared field {extra} was dropped"

    # The actual work content must be intact, not just the key.
    items = dumped["checklists"][0]["checkItems"]
    assert len(items) == 3
    assert items[0]["name"] == "Step 1: Analyze existing doc"

    # Nothing Trello sent may be lost.
    assert set(REAL_CARD) <= set(dumped)


def test_card_model_tolerates_narrowed_field_sets():
    """A partial response must not raise mid-crawl."""
    card = TrelloCard(id="abc123", name="Sparse")
    assert card.id == "abc123"
    assert card.checklists == []


# ------------------------------------------------------- transient 405 block


class _BlockingTransport:
    """Fails with an HTML bot-check `fail_times` times, then succeeds."""

    def __init__(self, fail_times: int, status: int = 405):
        self.fail_times = fail_times
        self.status = status
        self.calls = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.calls <= self.fail_times:
            return httpx.Response(
                self.status,
                headers={"content-type": "text/html; charset=utf-8"},
                text="<!DOCTYPE html><html><head><title>Human Verification</title>",
                request=request,
            )
        return httpx.Response(200, json={"id": "board1", "name": "Recovered"}, request=request)


def _client_with(transport_handler, **kwargs) -> TrelloClient:
    client = TrelloClient(api_key="k", token="t", **kwargs)
    client.client = httpx.AsyncClient(
        base_url="https://api.trello.com/1",
        transport=httpx.MockTransport(transport_handler.handle),
    )
    return client


def test_html_bot_check_is_retried_not_raised():
    """Trello answers ~8-10% of valid requests with a 405 HTML interstitial."""

    async def exercise():
        handler = _BlockingTransport(fail_times=2)
        client = _client_with(handler, max_retries=5)
        result = await client.GET("/boards/board1")
        assert result["name"] == "Recovered"
        assert handler.calls == 3, "should have retried twice before succeeding"
        await client.close()

    asyncio.run(exercise())


def test_bot_check_gives_up_with_a_clear_error_after_max_retries():
    async def exercise():
        handler = _BlockingTransport(fail_times=99)
        client = _client_with(handler, max_retries=3)
        with pytest.raises(TransientBlockError):
            await client.GET("/boards/board1")
        assert handler.calls == 3
        await client.close()

    asyncio.run(exercise())


def test_genuine_405_without_html_is_not_swallowed_as_transient():
    """A real method-not-allowed (JSON body) must still surface as an error."""

    class JsonHandler:
        def handle(self, request):
            return httpx.Response(
                405, headers={"content-type": "application/json"},
                json={"message": "method not allowed"}, request=request,
            )

    async def exercise():
        client = _client_with(JsonHandler(), max_retries=2)
        with pytest.raises(Exception) as excinfo:
            await client.GET("/boards/board1")
        assert not isinstance(excinfo.value, TransientBlockError)
        await client.close()

    asyncio.run(exercise())


def test_rate_limiter_paces_requests():
    """Token bucket must hold sustained throughput near the configured rate."""

    async def exercise():
        limiter = _RateLimiter(rate_per_second=20.0, burst=1)
        loop = asyncio.get_running_loop()
        start = loop.time()
        for _ in range(6):
            await limiter.acquire()
        # 5 gaps at 1/20s = 0.25s minimum, minus the initial burst token.
        assert loop.time() - start >= 0.2

    asyncio.run(exercise())


# --------------------------------------------------------- request shaping


class RecordingClient:
    def __init__(self, payload=None):
        self.calls = []
        self.payload = payload if payload is not None else {}

    async def GET(self, endpoint, params=None):
        self.calls.append((endpoint, params or {}))
        return self.payload


def test_get_card_requests_checklists_and_custom_fields():
    """Trello omits checklists unless explicitly asked."""

    async def exercise():
        client = RecordingClient(dict(REAL_CARD))
        await CardService(client).get_card("card1")
        _, params = client.calls[0]
        assert params.get("checklists") == "all"
        assert params.get("customFieldItems") == "true"
        assert params.get("fields") == "all"
        assert params.get("actions_limit") == "1000"

    asyncio.run(exercise())


def test_get_board_cards_includes_archived_by_default():
    """/boards/{id}/cards hides archived cards; /cards/all does not."""

    async def exercise():
        client = RecordingClient([dict(REAL_CARD)])
        service = CardService(client)

        await service.get_board_cards("board1")
        assert client.calls[0][0].endswith("/cards/all")

        await service.get_board_cards("board1", include_archived=False)
        assert client.calls[1][0].endswith("/cards/open")

    asyncio.run(exercise())


def test_card_comments_request_the_full_limit_not_the_default_50():
    async def exercise():
        client = RecordingClient([])
        await CardService(client).get_card_comments("card1")
        assert client.calls[0][1]["limit"] == 1000

    asyncio.run(exercise())


def test_search_lifts_the_ten_result_cap():
    """Trello defaults cards_limit to 10; omitting it capped every search."""

    async def exercise():
        client = RecordingClient({"cards": []})
        await SearchService(client).search("roadmap")
        _, params = client.calls[0]
        assert params["cards_limit"] == 1000
        assert params["idBoards"] == "mine"
        assert params["partial"] == "false"

        await SearchService(client).search("roadmap", partial=True)
        assert client.calls[1][1]["partial"] == "true"

    asyncio.run(exercise())


# ------------------------------------------------------------------- cache


@pytest.fixture()
def cache(tmp_path):
    db = CacheDB(path=tmp_path / "test_cache.db")
    yield db
    db.close()


def _board(board_id="b1", name="001. General"):
    return {"id": board_id, "name": name, "closed": False, "idOrganization": "org1"}


def test_cache_round_trips_a_card_without_losing_fields(cache):
    cache.replace_board(_board(), [REAL_CARD], [{"id": "l1", "name": "To do"}])
    stored = cache.get_card(REAL_CARD["id"])
    assert stored is not None
    assert set(REAL_CARD) <= set(stored), "cache must preserve every field"
    assert stored["checklists"][0]["checkItems"][1]["state"] == "complete"


def test_cache_looks_cards_up_by_shortlink_and_url(cache):
    cache.replace_board(_board(), [REAL_CARD], [])
    assert cache.get_card("pcocKQlk")["id"] == REAL_CARD["id"]
    assert cache.get_card("https://trello.com/c/pcocKQlk/10-x")["id"] == REAL_CARD["id"]


def test_cache_stores_archived_cards(cache):
    archived = {**REAL_CARD, "id": "arch1", "closed": True, "name": "Archived work"}
    cache.replace_board(_board(), [REAL_CARD, archived], [])

    counts = cache.counts()
    assert counts["cards"] == 2
    assert counts["cards_archived"] == 1

    _, total_all = cache.board_cards("b1", include_archived=True)
    _, total_open = cache.board_cards("b1", include_archived=False)
    assert total_all == 2 and total_open == 1


def test_search_matches_text_inside_checklist_items(cache):
    """Checklist text is the largest body of content and Trello never indexes it."""
    cache.replace_board(_board(), [REAL_CARD], [{"id": "l1", "name": "To do"}])

    hits, total = cache.search("Dutch healthcare")
    assert total == 1, "checklist item text must be searchable"
    assert hits[0]["id"] == REAL_CARD["id"]
    assert hits[0]["checklist_items"] == 3


def test_search_matches_comment_text(cache):
    cache.replace_board(_board(), [REAL_CARD], [])
    cache.replace_board_comments(
        "b1",
        [
            {
                "id": "a1",
                "type": "commentCard",
                "date": "2026-01-01T00:00:00Z",
                "idMemberCreator": "m1",
                "memberCreator": {"fullName": "Someone"},
                "data": {"card": {"id": REAL_CARD["id"]}, "text": "zorgverzekeraar declined"},
            }
        ],
    )
    _, total = cache.search("zorgverzekeraar")
    assert total == 1
    assert cache.get_card_comments(REAL_CARD["id"])[0]["text"].startswith("zorgverzekeraar")


def test_search_tolerates_punctuation_and_operators(cache):
    """Raw user text must never raise an FTS5 syntax error."""
    cache.replace_board(_board(), [REAL_CARD], [])
    for query in ['glasses AND (', 'therapy "', "OR NOT *", "reimburse*"]:
        hits, total = cache.search(query)
        assert isinstance(total, int)


def test_resyncing_a_board_replaces_rather_than_duplicates(cache):
    cache.replace_board(_board(), [REAL_CARD], [])
    cache.replace_board(_board(), [REAL_CARD], [])
    assert cache.counts()["cards"] == 1
    _, total = cache.search("Dutch healthcare")
    assert total == 1, "reindex must not leave stale duplicate FTS rows"


def test_removed_cards_disappear_on_resync(cache):
    other = {**REAL_CARD, "id": "gone", "name": "Deleted later"}
    cache.replace_board(_board(), [REAL_CARD, other], [])
    assert cache.counts()["cards"] == 2

    cache.replace_board(_board(), [REAL_CARD], [])
    assert cache.counts()["cards"] == 1
    assert cache.get_card("gone") is None


def test_incremental_sync_skips_boards_whose_activity_is_unchanged(cache):
    from server.cache.sync import SyncEngine

    engine = SyncEngine(client=None, cache=cache)
    board = {**_board(), "dateLastActivity": "2026-06-24T22:21:39.883Z"}

    assert engine._needs_refresh(board, {}) is True, "unknown board must sync"

    cache.replace_board(board, [REAL_CARD], [])
    state = cache.board_sync_state()
    assert engine._needs_refresh(board, state) is False, "unchanged board must be skipped"

    moved = {**board, "dateLastActivity": "2026-07-01T00:00:00.000Z"}
    assert engine._needs_refresh(moved, state) is True, "changed board must resync"


def test_board_that_failed_mid_crawl_is_retried_next_pass(cache):
    """A transient edge block must not freeze stale data in place forever.

    The pre-pull stub writes the remote activity stamp. If the deep pull then
    fails, comparing against that stub value would mark the board current and
    it would never be refetched.
    """
    from server.cache.sync import SyncEngine

    engine = SyncEngine(client=None, cache=cache)
    board = {**_board(), "dateLastActivity": "2026-06-24T22:21:39.883Z"}

    cache.replace_board(board, [REAL_CARD], [])
    assert engine._needs_refresh(board, cache.board_sync_state()) is False

    # Simulate the next pass: stub written, then the deep pull blows up.
    moved = {**board, "dateLastActivity": "2026-07-01T00:00:00.000Z"}
    cache.upsert_board_stub(moved)
    cache.record_board_error(moved["id"], "Trello edge temporarily blocked")

    state = cache.board_sync_state()
    assert state[moved["id"]]["sync_error"], "error must be recorded"
    assert engine._needs_refresh(moved, state) is True, (
        "a board whose pull failed must be retried, not treated as current"
    )


def test_cache_migrates_a_database_created_before_new_columns(tmp_path):
    """CREATE TABLE IF NOT EXISTS is a no-op, so new columns need an ALTER."""
    import sqlite3 as _sqlite3

    path = tmp_path / "legacy.db"
    legacy = _sqlite3.connect(str(path))
    legacy.executescript(
        """
        CREATE TABLE boards (
            id TEXT PRIMARY KEY, name TEXT, closed INTEGER DEFAULT 0,
            id_organization TEXT, url TEXT, short_link TEXT,
            date_last_activity TEXT, raw TEXT NOT NULL, synced_at TEXT
        );
        """
    )
    legacy.execute(
        "INSERT INTO boards(id, name, raw) VALUES('b1', 'Old board', '{}')"
    )
    legacy.commit()
    legacy.close()

    db = CacheDB(path=path)
    try:
        state = db.board_sync_state()
        assert "b1" in state
        assert state["b1"]["synced_activity"] is None
        assert state["b1"]["sync_error"] is None
    finally:
        db.close()


def test_rate_limiter_backs_off_on_blocks_and_recovers():
    limiter = _RateLimiter(rate_per_second=8.0)
    assert limiter.effective_rate == 8.0

    limiter.penalize()
    assert limiter.effective_rate == 4.0
    limiter.penalize()
    assert limiter.effective_rate == 2.0

    for _ in range(500):
        limiter.recover()
    assert limiter.effective_rate == 8.0, "penalty must decay back to the base rate"


def test_rate_limiter_penalty_is_capped():
    limiter = _RateLimiter(rate_per_second=8.0)
    for _ in range(50):
        limiter.penalize()
    assert limiter.effective_rate >= 8.0 / _RateLimiter.MAX_PENALTY


# -------------------------------------------------------- read-only boundary


class MockMCP:
    def __init__(self):
        self.tools = []

    def add_tool(self, tool, annotations=None):
        self.tools.append(tool.__name__)


def test_read_only_mode_exposes_complete_tools_but_no_mutations():
    from server.tools.tools import register_tools

    mcp = MockMCP()
    register_tools(mcp, read_only=True)

    for tool in (
        "trello_search_cards",
        "trello_get_card",
        "trello_board_cards",
        "trello_account_overview",
        "trello_sync_status",
        "trello_refresh",
        "get_board_cards",
    ):
        assert tool in mcp.tools, f"{tool} must be available for extraction"

    for mutation in ("delete_board", "delete_card", "create_card", "update_card",
                     "delete_workspace", "archive_card"):
        assert mutation not in mcp.tools, f"{mutation} must not be registered read-only"


def test_settings_resolve_env_independently_of_cwd(tmp_path, monkeypatch):
    """The ChatGPT app spawns the server with an arbitrary working directory."""
    import importlib

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TRELLO_API_KEY", raising=False)
    monkeypatch.delenv("TRELLO_TOKEN", raising=False)

    from server import settings as settings_module

    reloaded = importlib.reload(settings_module)
    # The package-anchored .env must still be found from an unrelated CWD.
    assert reloaded.PACKAGE_ROOT.name == "trello"
    if (reloaded.PACKAGE_ROOT / ".env").exists():
        assert reloaded.api_key(), "credentials must resolve from the package .env"

    os.environ["TRELLO_API_KEY"] = "test_key"
    os.environ["TRELLO_TOKEN"] = "test_token"
    importlib.reload(settings_module)


# ------------------------------------------------- archived visibility toggle


def _use_cache(monkeypatch, cache):
    """Point the complete-tools module at a throwaway cache."""
    from server.tools import complete

    monkeypatch.setattr(complete, "get_cache", lambda: cache)
    return complete


def test_archived_toggle_defaults_to_showing_archived(monkeypatch, cache):
    complete = _use_cache(monkeypatch, cache)
    monkeypatch.delenv("TRELLO_INCLUDE_ARCHIVED_DEFAULT", raising=False)
    assert complete._archived_default() is True


def test_archived_toggle_persists_and_filters_results(monkeypatch, cache):
    complete = _use_cache(monkeypatch, cache)
    archived = {**REAL_CARD, "id": "arch1", "closed": True,
                "name": "Old reimbursement", "checklists": REAL_CARD["checklists"]}
    cache.replace_board(_board(), [REAL_CARD, archived], [])

    # Default: both cards are searchable.
    both = asyncio.run(complete.trello_search_cards("Dutch healthcare"))
    assert both["total_matches"] == 2
    assert both["archived_included"] is True

    # Client's request: turn archived off, and have it stick.
    result = asyncio.run(complete.trello_set_archived_visibility(False))
    assert result["include_archived"] is False
    assert result["previous"] is True
    assert result["archived_cards"] == 1

    after = asyncio.run(complete.trello_search_cards("Dutch healthcare"))
    assert after["total_matches"] == 1, "archived card must be hidden now"
    assert after["archived_included"] is False

    # The preference survives, without being passed again.
    assert complete._archived_default() is False
    listing = asyncio.run(complete.trello_board_cards("b1"))
    assert listing["total_cards"] == 1

    # And it can be turned back on.
    asyncio.run(complete.trello_set_archived_visibility(True))
    assert asyncio.run(complete.trello_search_cards("Dutch healthcare"))["total_matches"] == 2


def test_explicit_argument_overrides_the_saved_preference(monkeypatch, cache):
    complete = _use_cache(monkeypatch, cache)
    archived = {**REAL_CARD, "id": "arch2", "closed": True, "name": "Archived one"}
    cache.replace_board(_board(), [REAL_CARD, archived], [])

    asyncio.run(complete.trello_set_archived_visibility(False))
    # A per-call argument must win over the stored default.
    forced = asyncio.run(
        complete.trello_search_cards("Dutch healthcare", include_archived=True)
    )
    assert forced["total_matches"] == 2
    assert forced["archived_included"] is True
    # ...without changing the saved preference.
    assert complete._archived_default() is False


def test_toggle_never_discards_archived_data(monkeypatch, cache):
    """Hiding must be a display filter, not a deletion - or re-enabling would
    require a full re-sync."""
    complete = _use_cache(monkeypatch, cache)
    archived = {**REAL_CARD, "id": "arch3", "closed": True, "name": "Still here"}
    cache.replace_board(_board(), [REAL_CARD, archived], [])

    asyncio.run(complete.trello_set_archived_visibility(False))
    assert cache.counts()["cards"] == 2, "archived card must remain stored"
    assert cache.get_card("arch3") is not None, "archived card must stay retrievable"


def test_settings_tool_reports_the_current_state(monkeypatch, cache):
    complete = _use_cache(monkeypatch, cache)
    archived = {**REAL_CARD, "id": "arch4", "closed": True, "name": "Archived"}
    cache.replace_board(_board(), [REAL_CARD, archived], [])

    asyncio.run(complete.trello_set_archived_visibility(False))
    info = asyncio.run(complete.trello_get_settings())
    assert info["include_archived"] is False
    assert info["visible_cards"] == 1
    assert info["total_cards"] == 2
    assert info["archived_cards"] == 1


def test_env_default_can_hide_archived_from_the_start(monkeypatch, cache):
    """TRELLO_INCLUDE_ARCHIVED_DEFAULT=false in .env, with nothing saved yet."""
    import importlib

    complete = _use_cache(monkeypatch, cache)
    monkeypatch.setenv("TRELLO_INCLUDE_ARCHIVED_DEFAULT", "false")
    from server import settings as settings_module

    importlib.reload(settings_module)
    monkeypatch.setattr(complete, "settings", settings_module)
    try:
        assert complete._archived_default() is False
    finally:
        monkeypatch.delenv("TRELLO_INCLUDE_ARCHIVED_DEFAULT", raising=False)
        importlib.reload(settings_module)


def test_read_only_mode_exposes_the_toggle():
    from server.tools.tools import register_tools

    mcp = MockMCP()
    register_tools(mcp, read_only=True)
    assert "trello_set_archived_visibility" in mcp.tools
    assert "trello_get_settings" in mcp.tools
