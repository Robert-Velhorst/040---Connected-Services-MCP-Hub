"""Centralised, CWD-independent configuration.

The ChatGPT / Codex app spawns this server as a stdio subprocess with an
arbitrary working directory. A bare ``load_dotenv()`` resolves ``.env`` relative
to the CWD, so credentials silently vanish and the server dies at import. Every
setting is therefore resolved from an absolute path anchored to this file.
"""

from __future__ import annotations

import os
import json
from pathlib import Path

from dotenv import load_dotenv

# trello/  (the directory holding .env, main.py, pyproject.toml)
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
KEYRING_SERVICE = "Trello ChatGPT Connector"
KEYRING_TOKEN_ACCOUNT = "trello_user_token"

_TRUTHY = {"1", "true", "yes", "on"}


# Variables an MCP client may declare but leave blank in its config.
_CLEARABLE = (
    "TRELLO_API_KEY",
    "TRELLO_TOKEN",
    "TRELLO_READ_ONLY",
    "TRELLO_MCP_DB_PATH",
    "TRELLO_MCP_ENV_FILE",
    "USE_CLAUDE_APP",
)


def _drop_blank_env() -> None:
    """Treat an empty environment variable as absent.

    ``load_dotenv(override=False)`` skips any key already present in
    ``os.environ`` -- including one set to "". A Codex/ChatGPT server entry
    that declares ``env = { TRELLO_API_KEY = "" }`` would therefore mask the
    real value in .env and the server would exit at import claiming the
    credentials are missing.
    """
    for name in _CLEARABLE:
        if name in os.environ and not os.environ[name].strip():
            del os.environ[name]


def _load_env() -> None:
    """Load .env without ever overriding real environment variables.

    Order matters: an explicit TRELLO_MCP_ENV_FILE wins, then the .env that
    sits next to the package, then whatever the CWD happens to hold (kept for
    backwards compatibility with the documented `cd trello && python main.py`
    workflow). ``override=False`` throughout means variables already exported
    by the MCP client — or by a test module — always take precedence.
    """
    _drop_blank_env()
    explicit = os.getenv("TRELLO_MCP_ENV_FILE")
    if explicit:
        load_dotenv(dotenv_path=Path(explicit), override=False)
    load_dotenv(dotenv_path=PACKAGE_ROOT / ".env", override=False)
    load_dotenv(override=False)


_load_env()


def _settings_path() -> Path:
    """Return the per-user native-app settings file, never a repository file."""
    override = os.getenv("TRELLO_MCP_SETTINGS_FILE")
    if override:
        return Path(override).expanduser()
    base = os.getenv("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "trello-mcp" / "settings.json"


def _stored_settings() -> dict[str, str]:
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _credential_manager_token() -> str | None:
    """Read the native installer token without falling back to a new secret."""
    try:
        import keyring
        return keyring.get_password(KEYRING_SERVICE, KEYRING_TOKEN_ACCOUNT) or None
    except Exception:
        return None


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY


def _number(name: str, default: float, minimum: float | None = None) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    if minimum is not None:
        value = max(minimum, value)
    return value


def api_key() -> str | None:
    return os.getenv("TRELLO_API_KEY") or _stored_settings().get("trello_app_key") or None


def api_token() -> str | None:
    return os.getenv("TRELLO_TOKEN") or _credential_manager_token()


def read_only() -> bool:
    """Server-side write boundary. See tools/tools.py:register_tools."""
    return _flag("TRELLO_READ_ONLY", default=False)


def cache_enabled() -> bool:
    return _flag("TRELLO_CACHE_ENABLED", default=True)


def include_archived_default() -> bool:
    """Whether tools show archived cards unless told otherwise.

    Defaults to True because most of this account's history is archived (807
    of 1,160 cards), so hiding them by default would silently repeat the very
    blind spot this project set out to fix.

    This is only the *starting* value: it can be changed at runtime with the
    trello_set_archived_visibility tool, which persists the choice. The mirror
    always stores archived cards either way, so flipping it is instant and
    never needs a re-sync.
    """
    return _flag("TRELLO_INCLUDE_ARCHIVED_DEFAULT", default=True)


def db_path() -> Path:
    """Where the local mirror lives.

    Defaults outside the repo so the cache survives a reinstall and is never
    at risk of being committed. On Windows this lands in the user profile.
    """
    override = os.getenv("TRELLO_MCP_DB_PATH")
    if override:
        path = Path(override).expanduser()
    else:
        base = os.getenv("LOCALAPPDATA")
        root = Path(base) if base else Path.home() / ".local" / "share"
        path = Path(root).expanduser() / "trello-mcp" / "trello_cache.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def sync_on_start() -> bool:
    return _flag("TRELLO_SYNC_ON_START", default=True)


def sync_interval_seconds() -> float:
    """Gap between incremental sync passes. 0 disables periodic resync."""
    return _number("TRELLO_SYNC_INTERVAL_SECONDS", 900.0, minimum=0.0)


def requests_per_second() -> float:
    """Sustained request budget.

    Measured ceilings on this account: 100 req/10s per token, 300/10s per key,
    375/10s per member. The documented limits are not the binding constraint --
    the edge's reputation heuristic blocks sustained heavy crawling well below
    them -- so this sits far under the allowance and the limiter throttles
    itself further whenever a block is seen.
    """
    return _number("TRELLO_REQUESTS_PER_SECOND", 4.0, minimum=0.2)


def sync_concurrency() -> int:
    return int(_number("TRELLO_SYNC_CONCURRENCY", 3, minimum=1))


def max_retries() -> int:
    """Attempts per request before giving up on a transient edge block."""
    return int(_number("TRELLO_MAX_RETRIES", 8, minimum=1))


def comment_page_limit() -> int:
    """Trello caps `limit` at 1000 for action listings."""
    return int(_number("TRELLO_COMMENT_PAGE_LIMIT", 1000, minimum=1))


def max_comment_pages() -> int:
    return int(_number("TRELLO_MAX_COMMENT_PAGES", 20, minimum=1))
