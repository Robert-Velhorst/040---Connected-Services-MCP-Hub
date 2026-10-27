"""One-time local Trello consent flow for the Windows installer.

The app key is public configuration and is stored under the user's local app
data. The Trello user token is stored only in Windows Credential Manager.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import urlopen

import keyring


HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SERVICE = "Trello ChatGPT Connector"
TOKEN_ACCOUNT = "trello_user_token"


def port() -> int:
    return int(os.getenv("TRELLO_CONNECT_PORT", str(DEFAULT_PORT)))


def base_url() -> str:
    return f"http://localhost:{port()}"


def settings_path() -> Path:
    override = os.getenv("TRELLO_MCP_SETTINGS_FILE")
    if override:
        return Path(override).expanduser()
    local_app_data = os.getenv("LOCALAPPDATA")
    root = Path(local_app_data) if local_app_data else Path.home() / ".local" / "share"
    return root / "trello-mcp" / "settings.json"


def load_settings() -> dict[str, str]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_settings(app_key: str) -> None:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps({"trello_app_key": app_key}, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def matches_pending_state(candidate: object, expected: str | None) -> bool:
    # compare_digest rejects non-ASCII strings; malformed input must receive a
    # normal rejection rather than tearing down the consent HTTP connection.
    return (
        isinstance(candidate, str)
        and candidate.isascii()
        and isinstance(expected, str)
        and bool(expected)
        and expected.isascii()
        and secrets.compare_digest(candidate, expected)
    )


class ConnectHandler(BaseHTTPRequestHandler):
    server: "ConnectServer"

    def log_message(self, format: str, *args: object) -> None:
        # Do not put OAuth fragments or form data into the console log.
        return

    def _response(self, body: str, status: int = HTTPStatus.OK, content_type: str = "text/html; charset=utf-8") -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _local_request(self, require_origin: bool = False) -> bool:
        hosts = self.headers.get_all("Host", [])
        expected = {f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"}
        if self.server.server_port == 80:
            expected.update({"localhost", "127.0.0.1"})
        if len(hosts) != 1 or hosts[0].lower() not in expected:
            return False
        origins = self.headers.get_all("Origin", [])
        if not origins:
            return not require_origin
        return len(origins) == 1 and origins[0] == "http://" + hosts[0].lower()

    def do_GET(self) -> None:  # noqa: N802
        if not self._local_request():
            self._response("Local request authority did not match.", HTTPStatus.FORBIDDEN, "text/plain; charset=utf-8")
            return
        route = urlparse(self.path)
        if route.path in {"/", "/connect"}:
            app_key = load_settings().get("trello_app_key")
            if not app_key:
                self._redirect("/setup")
                return
            self.server.state = secrets.token_urlsafe(32)
            callback = f"{base_url()}/callback?state={self.server.state}"
            authorization = "https://trello.com/1/authorize?" + urlencode({
                "key": app_key,
                "name": "Trello ChatGPT Connector",
                "expiration": "never",
                "scope": "read",
                "response_type": "token",
                "callback_method": "fragment",
                "return_url": callback,
            })
            self._redirect(authorization)
            return
        if route.path == "/setup":
            self._response(f"""<!doctype html><title>Connect Trello</title>
<h1>Connect Trello</h1>
<p>Create or select a Trello Power-Up at <a href=\"https://trello.com/power-ups/admin\">Trello App Administration</a>. Add <code>{base_url()}</code> as an allowed origin, then enter its API key below.</p>
<form method=\"post\" action=\"/setup\"><label>Power-Up API key <input name=\"app_key\" required autocomplete=\"off\"></label><button>Continue to Trello</button></form>""")
            return
        if route.path == "/callback":
            supplied_state = parse_qs(route.query).get("state", [""])[0]
            if not matches_pending_state(supplied_state, self.server.state):
                self._response("Authorization state did not match.", HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8")
                return
            # Render only the server-generated nonce, never callback query text.
            state = self.server.state
            self._response(f"""<!doctype html><title>Connecting Trello</title><p id=\"status\">Finishing connection...</p>
<script>
const token = new URLSearchParams(location.hash.slice(1)).get("token");
const state = {json.dumps(state)};
const status = document.getElementById("status");
if (!token || !state) {{ status.textContent = "Trello did not return an authorization token."; }}
else {{ fetch("/complete", {{method:"POST",headers:{{"Content-Type":"application/json"}},body:JSON.stringify({{token,state}})}})
 .then(async r => {{ const p = await r.json(); status.textContent = r.ok ? "Connected. You can close this window." : (p.error || "Connection failed."); }})
 .catch(() => {{ status.textContent = "Connection failed."; }}); }}
</script>""")
            return
        self._response("Not found", HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if not self._local_request(require_origin=True):
            self._response("Local request origin did not match.", HTTPStatus.FORBIDDEN, "text/plain; charset=utf-8")
            return
        route = urlparse(self.path)
        if route.path not in {"/setup", "/complete"}:
            self._response("Not found", HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")
            return
        content_type = self.headers.get_content_type()
        expected_type = "application/json" if route.path == "/complete" else "application/x-www-form-urlencoded"
        if content_type != expected_type:
            self._response("Unsupported request content type.", HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "text/plain; charset=utf-8")
            return
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get_all("Transfer-Encoding", []) or len(lengths) != 1:
            self._response("A single bounded content length is required.", HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8")
            return
        declared = lengths[0].strip()
        if not declared.isascii() or not declared.isdigit():
            self._response("Invalid content length.", HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8")
            return
        length = int(declared)
        if length > 4096:
            self._response("Request body is too large.", HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "text/plain; charset=utf-8")
            return
        self.connection.settimeout(5)
        body = self.rfile.read(length)
        if route.path == "/setup":
            try:
                app_key = parse_qs(body.decode("utf-8")).get("app_key", [""])[0].strip()
            except UnicodeDecodeError:
                self._response("Invalid setup form.", HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8")
                return
            if len(app_key) < 8:
                self._response("Enter a valid Trello Power-Up API key.", HTTPStatus.BAD_REQUEST, "text/plain; charset=utf-8")
                return
            save_settings(app_key)
            self._redirect("/connect")
            return
        if route.path == "/complete":
            try:
                payload = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._response(json.dumps({"error": "Invalid authorization response."}), HTTPStatus.BAD_REQUEST, "application/json")
                return
            token = payload.get("token") if isinstance(payload, dict) else None
            state = payload.get("state") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not matches_pending_state(state, self.server.state):
                self._response(json.dumps({"error": "Authorization state did not match."}), HTTPStatus.BAD_REQUEST, "application/json")
                return
            app_key = load_settings().get("trello_app_key")
            try:
                query = urlencode({"key": app_key, "token": token, "fields": "username"})
                with urlopen(f"https://api.trello.com/1/members/me?{query}", timeout=20) as response:
                    if response.status != HTTPStatus.OK:
                        raise ValueError("Trello rejected the authorization token.")
                keyring.set_password(SERVICE, TOKEN_ACCOUNT, token)
            except Exception:
                self._response(json.dumps({"error": "Trello could not validate or securely store the authorization token."}), HTTPStatus.BAD_REQUEST, "application/json")
                return
            self._response(json.dumps({"connected": True}), content_type="application/json")
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self._response("Not found", HTTPStatus.NOT_FOUND, "text/plain; charset=utf-8")


class ConnectServer(ThreadingHTTPServer):
    state: str | None = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="start the local flow without opening a browser")
    args = parser.parse_args()
    server = ConnectServer((HOST, port()), ConnectHandler)
    print(f"Open {base_url()}/connect to link Trello. The server stops after success.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(f"{base_url()}/connect")).start()
    server.serve_forever()
    server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
