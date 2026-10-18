"""SQLite mirror of every board, list, card, checklist and comment.

Design rules:

* ``cards.raw`` holds the **complete** Trello card JSON. Promoted columns exist
  only to make queries fast; nothing is ever the sole copy of a field, so a
  field this module has never heard of still round-trips intact.
* Archived cards are stored alongside open ones and flagged with ``closed``.
  ``/boards/{id}/cards`` hides archived cards -- on the reference board that is
  99 of 131 cards -- so the mirror deliberately pulls ``cards=all``.
* Reads happen on the MCP request thread while writes happen on the sync
  thread, so the connection is opened with ``check_same_thread=False``, runs in
  WAL mode, and serialises writes behind a lock.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from server import settings

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS workspaces (
    id           TEXT PRIMARY KEY,
    name         TEXT,
    display_name TEXT,
    url          TEXT,
    raw          TEXT NOT NULL,
    synced_at    TEXT
);

CREATE TABLE IF NOT EXISTS boards (
    id                 TEXT PRIMARY KEY,
    name               TEXT,
    closed             INTEGER DEFAULT 0,
    id_organization    TEXT,
    url                TEXT,
    short_link         TEXT,
    date_last_activity TEXT,
    -- Activity stamp at the moment of the last SUCCESSFUL deep pull. Kept
    -- separate from date_last_activity, which the pre-pull stub overwrites.
    synced_activity    TEXT,
    raw                TEXT NOT NULL,
    synced_at          TEXT,
    sync_error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_boards_org ON boards(id_organization);

CREATE TABLE IF NOT EXISTS lists (
    id       TEXT PRIMARY KEY,
    id_board TEXT,
    name     TEXT,
    closed   INTEGER DEFAULT 0,
    pos      REAL,
    raw      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lists_board ON lists(id_board);

CREATE TABLE IF NOT EXISTS cards (
    id                 TEXT PRIMARY KEY,
    id_board           TEXT,
    id_list            TEXT,
    name               TEXT,
    description        TEXT,
    closed             INTEGER DEFAULT 0,
    url                TEXT,
    short_url          TEXT,
    short_link         TEXT,
    id_short           INTEGER,
    due                TEXT,
    start              TEXT,
    due_complete       INTEGER DEFAULT 0,
    date_last_activity TEXT,
    pos                REAL,
    checklist_items    INTEGER DEFAULT 0,
    attachment_count   INTEGER DEFAULT 0,
    comment_count      INTEGER DEFAULT 0,
    raw                TEXT NOT NULL,
    synced_at          TEXT
);
CREATE INDEX IF NOT EXISTS idx_cards_board  ON cards(id_board);
CREATE INDEX IF NOT EXISTS idx_cards_list   ON cards(id_list);
CREATE INDEX IF NOT EXISTS idx_cards_closed ON cards(closed);
CREATE INDEX IF NOT EXISTS idx_cards_short  ON cards(short_link);

CREATE TABLE IF NOT EXISTS comments (
    id          TEXT PRIMARY KEY,
    id_card     TEXT,
    id_board    TEXT,
    date        TEXT,
    author_id   TEXT,
    author_name TEXT,
    text        TEXT,
    raw         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_comments_card  ON comments(id_card);
CREATE INDEX IF NOT EXISTS idx_comments_board ON comments(id_board);
"""

_FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS cards_fts USING fts5(
    card_id UNINDEXED,
    name,
    description,
    checklist_text,
    comment_text,
    board_name,
    list_name,
    label_text,
    tokenize = 'porter unicode61'
);
"""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checklist_text(card: dict[str, Any]) -> str:
    """Flatten checklist names and every check item into searchable text.

    This is the single biggest body of content the old model discarded: 714
    check items on one board alone, holding the actual step-by-step work.
    """
    parts: list[str] = []
    for checklist in card.get("checklists") or []:
        if not isinstance(checklist, dict):
            continue
        if checklist.get("name"):
            parts.append(str(checklist["name"]))
        for item in checklist.get("checkItems") or []:
            if isinstance(item, dict) and item.get("name"):
                state = item.get("state", "")
                parts.append(f"{item['name']} [{state}]" if state else str(item["name"]))
    return "\n".join(parts)


def _label_text(card: dict[str, Any]) -> str:
    names = []
    for label in card.get("labels") or []:
        if isinstance(label, dict):
            names.append(str(label.get("name") or label.get("color") or ""))
    return " ".join(n for n in names if n)


def _count_checkitems(card: dict[str, Any]) -> int:
    total = 0
    for checklist in card.get("checklists") or []:
        if isinstance(checklist, dict):
            total += len(checklist.get("checkItems") or [])
    return total


class CacheDB:
    """Thread-safe SQLite mirror."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else settings.db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self.fts_enabled = False
        self._init_schema()

    # ---------------------------------------------------------------- schema

    # Columns added after the first release. CREATE TABLE IF NOT EXISTS is a
    # no-op on an existing database, so new columns need an explicit backfill
    # or every query referencing them raises OperationalError.
    _MIGRATIONS: tuple[tuple[str, str, str], ...] = (
        ("boards", "synced_activity", "TEXT"),
        ("boards", "sync_error", "TEXT"),
    )

    def _migrate(self) -> None:
        for table, column, coltype in self._MIGRATIONS:
            existing = {
                row["name"]
                for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if not existing:
                continue  # table not created yet; _SCHEMA will handle it
            if column not in existing:
                logger.info("Migrating cache: adding %s.%s", table, column)
                self._conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"
                )

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            self._migrate()
            try:
                self._conn.executescript(_FTS_SCHEMA)
                self.fts_enabled = True
            except sqlite3.OperationalError as error:
                # Some Python builds ship without FTS5; degrade to LIKE search
                # rather than refusing to run.
                logger.warning("FTS5 unavailable (%s); falling back to LIKE search", error)
                self.fts_enabled = False
            self._conn.commit()
        self.set_meta("schema_version", SCHEMA_VERSION)

    # ------------------------------------------------------------------ meta

    def set_meta(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value)),
            )
            self._conn.commit()

    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, ValueError):
            return default

    # ----------------------------------------------------------------- write

    def upsert_workspaces(self, workspaces: Iterable[dict[str, Any]]) -> int:
        now = _utcnow()
        rows = [
            (
                w.get("id"),
                w.get("name"),
                w.get("displayName"),
                w.get("url"),
                json.dumps(w, ensure_ascii=False),
                now,
            )
            for w in workspaces
            if isinstance(w, dict) and w.get("id")
        ]
        if not rows:
            return 0
        with self._lock:
            self._conn.executemany(
                "INSERT INTO workspaces(id, name, display_name, url, raw, synced_at) "
                "VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
                "name=excluded.name, display_name=excluded.display_name, "
                "url=excluded.url, raw=excluded.raw, synced_at=excluded.synced_at",
                rows,
            )
            self._conn.commit()
        return len(rows)

    def upsert_board_stub(self, board: dict[str, Any]) -> None:
        """Record a board before its deep pull, so listings work during sync."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO boards(id, name, closed, id_organization, url, short_link,"
                " date_last_activity, raw, synced_at) VALUES(?,?,?,?,?,?,?,?,NULL) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, closed=excluded.closed,"
                " id_organization=excluded.id_organization, url=excluded.url,"
                " short_link=excluded.short_link,"
                " date_last_activity=excluded.date_last_activity",
                (
                    board.get("id"),
                    board.get("name"),
                    1 if board.get("closed") else 0,
                    board.get("idOrganization"),
                    board.get("url"),
                    board.get("shortLink"),
                    board.get("dateLastActivity"),
                    json.dumps(board, ensure_ascii=False),
                ),
            )
            self._conn.commit()

    def replace_board(
        self,
        board: dict[str, Any],
        cards: list[dict[str, Any]],
        lists: list[dict[str, Any]],
    ) -> None:
        """Atomically swap in a freshly pulled board and all of its cards."""
        board_id = board.get("id")
        now = _utcnow()
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("BEGIN")
            try:
                cur.execute(
                    "INSERT INTO boards(id, name, closed, id_organization, url, short_link,"
                    " date_last_activity, synced_activity, raw, synced_at, sync_error)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,NULL)"
                    " ON CONFLICT(id) DO UPDATE SET name=excluded.name,"
                    " closed=excluded.closed, id_organization=excluded.id_organization,"
                    " url=excluded.url, short_link=excluded.short_link,"
                    " date_last_activity=excluded.date_last_activity,"
                    " synced_activity=excluded.synced_activity, raw=excluded.raw,"
                    " synced_at=excluded.synced_at, sync_error=NULL",
                    (
                        board_id,
                        board.get("name"),
                        1 if board.get("closed") else 0,
                        board.get("idOrganization"),
                        board.get("url"),
                        board.get("shortLink"),
                        board.get("dateLastActivity"),
                        board.get("dateLastActivity"),
                        json.dumps(
                            {k: v for k, v in board.items() if k not in ("cards", "lists")},
                            ensure_ascii=False,
                        ),
                        now,
                    ),
                )

                cur.execute("DELETE FROM lists WHERE id_board=?", (board_id,))
                cur.executemany(
                    "INSERT OR REPLACE INTO lists(id, id_board, name, closed, pos, raw)"
                    " VALUES(?,?,?,?,?,?)",
                    [
                        (
                            lst.get("id"),
                            board_id,
                            lst.get("name"),
                            1 if lst.get("closed") else 0,
                            lst.get("pos"),
                            json.dumps(lst, ensure_ascii=False),
                        )
                        for lst in lists
                        if isinstance(lst, dict) and lst.get("id")
                    ],
                )

                cur.execute("DELETE FROM cards WHERE id_board=?", (board_id,))
                card_rows = []
                for card in cards:
                    if not isinstance(card, dict) or not card.get("id"):
                        continue
                    card_rows.append(
                        (
                            card.get("id"),
                            board_id,
                            card.get("idList"),
                            card.get("name"),
                            card.get("desc"),
                            1 if card.get("closed") else 0,
                            card.get("url"),
                            card.get("shortUrl"),
                            card.get("shortLink"),
                            card.get("idShort"),
                            card.get("due"),
                            card.get("start"),
                            1 if card.get("dueComplete") else 0,
                            card.get("dateLastActivity"),
                            card.get("pos") if isinstance(card.get("pos"), (int, float)) else None,
                            _count_checkitems(card),
                            len(card.get("attachments") or []),
                            0,
                            json.dumps(card, ensure_ascii=False),
                            now,
                        )
                    )
                cur.executemany(
                    "INSERT OR REPLACE INTO cards(id, id_board, id_list, name, description,"
                    " closed, url, short_url, short_link, id_short, due, start, due_complete,"
                    " date_last_activity, pos, checklist_items, attachment_count,"
                    " comment_count, raw, synced_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    card_rows,
                )
                cur.execute("COMMIT")
            except Exception:
                cur.execute("ROLLBACK")
                raise

        self._reindex_board(board_id)

    def record_board_error(self, board_id: str, message: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE boards SET sync_error=? WHERE id=?", (message[:500], board_id)
            )
            self._conn.commit()

    def replace_board_comments(self, board_id: str, actions: list[dict[str, Any]]) -> int:
        rows = []
        for action in actions:
            if not isinstance(action, dict) or action.get("type") != "commentCard":
                continue
            data = action.get("data") or {}
            card = data.get("card") or {}
            creator = action.get("memberCreator") or {}
            rows.append(
                (
                    action.get("id"),
                    card.get("id"),
                    board_id,
                    action.get("date"),
                    action.get("idMemberCreator"),
                    creator.get("fullName") or creator.get("username"),
                    data.get("text", ""),
                    json.dumps(action, ensure_ascii=False),
                )
            )
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("DELETE FROM comments WHERE id_board=?", (board_id,))
            if rows:
                cur.executemany(
                    "INSERT OR REPLACE INTO comments(id, id_card, id_board, date,"
                    " author_id, author_name, text, raw) VALUES(?,?,?,?,?,?,?,?)",
                    rows,
                )
                cur.execute(
                    "UPDATE cards SET comment_count = ("
                    "  SELECT COUNT(*) FROM comments WHERE comments.id_card = cards.id"
                    ") WHERE id_board = ?",
                    (board_id,),
                )
            self._conn.commit()
        self._reindex_board(board_id)
        return len(rows)

    # ----------------------------------------------------------------- index

    def _reindex_board(self, board_id: str) -> None:
        if not self.fts_enabled:
            return
        with self._lock:
            cur = self._conn.cursor()
            rows = cur.execute(
                "SELECT c.id, c.name, c.description, c.raw, b.name AS board_name,"
                " l.name AS list_name FROM cards c"
                " LEFT JOIN boards b ON b.id = c.id_board"
                " LEFT JOIN lists  l ON l.id = c.id_list"
                " WHERE c.id_board = ?",
                (board_id,),
            ).fetchall()

            comment_map: dict[str, list[str]] = {}
            for row in cur.execute(
                "SELECT id_card, text FROM comments WHERE id_board=?", (board_id,)
            ):
                if row["id_card"]:
                    comment_map.setdefault(row["id_card"], []).append(row["text"] or "")

            cur.execute(
                "DELETE FROM cards_fts WHERE card_id IN (SELECT id FROM cards WHERE id_board=?)",
                (board_id,),
            )
            payload = []
            for row in rows:
                try:
                    card = json.loads(row["raw"])
                except (TypeError, ValueError):
                    card = {}
                payload.append(
                    (
                        row["id"],
                        row["name"] or "",
                        row["description"] or "",
                        _checklist_text(card),
                        "\n".join(comment_map.get(row["id"], [])),
                        row["board_name"] or "",
                        row["list_name"] or "",
                        _label_text(card),
                    )
                )
            cur.executemany(
                "INSERT INTO cards_fts(card_id, name, description, checklist_text,"
                " comment_text, board_name, list_name, label_text)"
                " VALUES(?,?,?,?,?,?,?,?)",
                payload,
            )
            self._conn.commit()

    # ------------------------------------------------------------------ read

    def counts(self) -> dict[str, int]:
        cur = self._conn.cursor()

        def one(sql: str) -> int:
            return int(cur.execute(sql).fetchone()[0])

        return {
            "workspaces": one("SELECT COUNT(*) FROM workspaces"),
            "boards": one("SELECT COUNT(*) FROM boards"),
            "boards_synced": one("SELECT COUNT(*) FROM boards WHERE synced_at IS NOT NULL"),
            "boards_failed": one("SELECT COUNT(*) FROM boards WHERE sync_error IS NOT NULL"),
            "lists": one("SELECT COUNT(*) FROM lists"),
            "cards": one("SELECT COUNT(*) FROM cards"),
            "cards_open": one("SELECT COUNT(*) FROM cards WHERE closed=0"),
            "cards_archived": one("SELECT COUNT(*) FROM cards WHERE closed=1"),
            "checklist_items": one("SELECT COALESCE(SUM(checklist_items),0) FROM cards"),
            "comments": one("SELECT COUNT(*) FROM comments"),
        }

    def board_sync_state(self) -> dict[str, dict[str, Any]]:
        """Per-board state used to decide what an incremental pass must refetch.

        ``synced_activity`` is the activity stamp as of the last *successful*
        deep pull -- deliberately not the stamp written by the pre-pull stub.
        Comparing against the stub value would mark a board that failed
        mid-crawl as up to date, and it would then never be retried.
        """
        rows = self._conn.execute(
            "SELECT id, date_last_activity, synced_activity, synced_at, sync_error"
            " FROM boards"
        ).fetchall()
        return {
            r["id"]: {
                "date_last_activity": r["date_last_activity"],
                "synced_activity": r["synced_activity"],
                "synced_at": r["synced_at"],
                "sync_error": r["sync_error"],
            }
            for r in rows
        }

    def list_boards(self, include_closed: bool = True) -> list[dict[str, Any]]:
        sql = (
            "SELECT b.id, b.name, b.closed, b.id_organization, b.url, b.short_link,"
            " b.date_last_activity, b.synced_at, b.sync_error,"
            " w.display_name AS workspace,"
            " (SELECT COUNT(*) FROM cards c WHERE c.id_board=b.id) AS cards,"
            " (SELECT COUNT(*) FROM cards c WHERE c.id_board=b.id AND c.closed=1) AS archived"
            " FROM boards b LEFT JOIN workspaces w ON w.id = b.id_organization"
        )
        if not include_closed:
            sql += " WHERE b.closed = 0"
        sql += " ORDER BY b.name COLLATE NOCASE"
        return [dict(r) for r in self._conn.execute(sql).fetchall()]

    def list_workspaces(self) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self._conn.execute(
                "SELECT w.id, w.name, w.display_name, w.url,"
                " (SELECT COUNT(*) FROM boards b WHERE b.id_organization=w.id) AS boards"
                " FROM workspaces w ORDER BY w.display_name COLLATE NOCASE"
            ).fetchall()
        ]

    def get_card(self, identifier: str) -> dict[str, Any] | None:
        """Look a card up by full id, shortLink, or a pasted Trello URL."""
        token = (identifier or "").strip()
        if "trello.com/c/" in token:
            token = token.split("trello.com/c/", 1)[1].split("/")[0].split("?")[0]
        row = self._conn.execute(
            "SELECT raw FROM cards WHERE id=? OR short_link=?", (token, token)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["raw"])

    def get_card_comments(self, card_id: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT id, date, author_id, author_name, text FROM comments"
            " WHERE id_card=? ORDER BY date DESC",
            (card_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def board_cards(
        self,
        board_id: str,
        include_archived: bool = True,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        where = "WHERE id_board = ?"
        args: list[Any] = [board_id]
        if not include_archived:
            where += " AND closed = 0"
        total = int(
            self._conn.execute(
                f"SELECT COUNT(*) FROM cards {where}", args
            ).fetchone()[0]
        )
        rows = self._conn.execute(
            f"SELECT raw FROM cards {where} ORDER BY pos, name LIMIT ? OFFSET ?",
            (*args, limit, offset),
        ).fetchall()
        return [json.loads(r["raw"]) for r in rows], total

    def search(
        self,
        query: str,
        limit: int = 25,
        offset: int = 0,
        board_id: str | None = None,
        include_archived: bool = True,
    ) -> tuple[list[dict[str, Any]], int]:
        """Full-text search over names, descriptions, checklists and comments."""
        if self.fts_enabled:
            return self._search_fts(query, limit, offset, board_id, include_archived)
        return self._search_like(query, limit, offset, board_id, include_archived)

    def _search_fts(self, query, limit, offset, board_id, include_archived):
        match = _to_fts_query(query)
        filters = ""
        args: list[Any] = [match]
        if board_id:
            filters += " AND c.id_board = ?"
            args.append(board_id)
        if not include_archived:
            filters += " AND c.closed = 0"

        total = int(
            self._conn.execute(
                "SELECT COUNT(*) FROM cards_fts f JOIN cards c ON c.id = f.card_id"
                f" WHERE cards_fts MATCH ?{filters}",
                args,
            ).fetchone()[0]
        )
        rows = self._conn.execute(
            "SELECT c.raw, b.name AS board_name, l.name AS list_name,"
            " snippet(cards_fts, -1, '<<', '>>', ' ... ', 24) AS snippet"
            " FROM cards_fts f JOIN cards c ON c.id = f.card_id"
            " LEFT JOIN boards b ON b.id = c.id_board"
            " LEFT JOIN lists  l ON l.id = c.id_list"
            f" WHERE cards_fts MATCH ?{filters}"
            " ORDER BY bm25(cards_fts) LIMIT ? OFFSET ?",
            (*args, limit, offset),
        ).fetchall()
        return [_hit(r) for r in rows], total

    def _search_like(self, query, limit, offset, board_id, include_archived):
        like = f"%{query}%"
        filters = ""
        args: list[Any] = [like, like, like]
        if board_id:
            filters += " AND c.id_board = ?"
            args.append(board_id)
        if not include_archived:
            filters += " AND c.closed = 0"
        base = (
            " FROM cards c LEFT JOIN boards b ON b.id = c.id_board"
            " LEFT JOIN lists l ON l.id = c.id_list"
            " WHERE (c.name LIKE ? OR c.description LIKE ? OR c.raw LIKE ?)" + filters
        )
        total = int(self._conn.execute(f"SELECT COUNT(*){base}", args).fetchone()[0])
        rows = self._conn.execute(
            "SELECT c.raw, b.name AS board_name, l.name AS list_name, '' AS snippet"
            + base
            + " ORDER BY c.date_last_activity DESC LIMIT ? OFFSET ?",
            (*args, limit, offset),
        ).fetchall()
        return [_hit(r) for r in rows], total

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _hit(row: sqlite3.Row) -> dict[str, Any]:
    card = json.loads(row["raw"])
    return {
        "id": card.get("id"),
        "name": card.get("name"),
        "board": row["board_name"],
        "list": row["list_name"],
        "closed": bool(card.get("closed")),
        "url": card.get("shortUrl") or card.get("url"),
        "due": card.get("due"),
        "dateLastActivity": card.get("dateLastActivity"),
        "checklist_items": _count_checkitems(card),
        "snippet": (row["snippet"] or "").strip(),
    }


def _to_fts_query(query: str) -> str:
    """Turn user text into a safe FTS5 MATCH expression.

    Bare user input can contain FTS operators that raise OperationalError, so
    each term is quoted and joined with AND. A trailing ``*`` is preserved to
    keep prefix search available.
    """
    terms = [t for t in (query or "").split() if t.strip()]
    if not terms:
        return '""'
    quoted = []
    for term in terms:
        prefix = term.endswith("*")
        cleaned = term.rstrip("*").replace('"', "")
        if not cleaned:
            continue
        quoted.append(f'"{cleaned}"*' if prefix else f'"{cleaned}"')
    return " AND ".join(quoted) or '""'


_cache: CacheDB | None = None
_cache_lock = threading.Lock()


def get_cache() -> CacheDB:
    """Process-wide singleton, created on first use."""
    global _cache
    with _cache_lock:
        if _cache is None:
            _cache = CacheDB()
        return _cache
