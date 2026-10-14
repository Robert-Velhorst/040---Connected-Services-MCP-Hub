"""Register this server with the ChatGPT desktop app / Codex CLI.

The ChatGPT desktop app, Codex CLI and the IDE extension share one MCP
configuration file, ``~/.codex/config.toml``. Adding an entry there makes the
server appear under Settings -> Plugins -> MCPs with an on/off toggle; the app
spawns the process itself, so there is nothing to start manually, no tunnel and
no background service to babysit.

Usage:
    .venv\\Scripts\\python.exe setup_codex.py            # install / update
    .venv\\Scripts\\python.exe setup_codex.py --check    # show current state
    .venv\\Scripts\\python.exe setup_codex.py --remove   # unregister

The script is idempotent, backs the file up before touching it, and validates
the result parses as TOML before keeping it.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path

SERVER_NAME = "trello"
PACKAGE_ROOT = Path(__file__).resolve().parent


def config_path() -> Path:
    return Path.home() / ".codex" / "config.toml"


def python_executable() -> Path:
    """Prefer the project venv so the app never depends on a global install."""
    candidates = [
        PACKAGE_ROOT / ".venv" / "Scripts" / "python.exe",  # Windows
        PACKAGE_ROOT / ".venv" / "bin" / "python",          # POSIX
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def _toml_str(value: Path | str) -> str:
    """Single-quoted TOML literal string: Windows paths keep their backslashes."""
    text = str(value)
    if "'" in text:
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"'{text}'"


DOCKER_IMAGE = "trello-mcp:latest"
DOCKER_VOLUME = "trello-mcp-data"


def build_docker_block() -> str:
    """Register `docker run` as the server command.

    No Python is needed on the host. `-i` attaches stdin, which is the MCP
    channel; `-t` must NOT be used, as a TTY would corrupt the protocol.
    The named volume keeps the local index between runs -- without it the
    connector would re-crawl every board on each launch.
    """
    env_file = PACKAGE_ROOT / ".env"
    return f"""
[mcp_servers.{SERVER_NAME}]
command = "docker"
args = [
    "run", "--rm", "-i",
    "--env-file", {_toml_str(env_file)},
    "-v", "{DOCKER_VOLUME}:/data",
    "{DOCKER_IMAGE}",
]
# Higher than the Python install: a cold container start adds a few seconds.
startup_timeout_sec = 90
tool_timeout_sec = 120
enabled = true

[mcp_servers.{SERVER_NAME}.env]
# Credentials come from the --env-file above, so none are stored here.
DOCKER_CLI_HINTS = "false"
""".rstrip() + "\n"


def build_block() -> str:
    python = python_executable()
    entry = PACKAGE_ROOT / "main.py"
    return f"""
[mcp_servers.{SERVER_NAME}]
command = {_toml_str(python)}
args = [{_toml_str(entry)}]
cwd = {_toml_str(PACKAGE_ROOT)}
# Default is 10s; a cold start behind antivirus can exceed that and the app
# would mark the server failed.
startup_timeout_sec = 60
# Default is 60s. Cached reads answer in milliseconds, but this leaves room
# for a first-run call that arrives while the initial crawl is still going.
tool_timeout_sec = 120
enabled = true

[mcp_servers.{SERVER_NAME}.env]
USE_CLAUDE_APP = "true"
# Hard server-side boundary: no mutation tool is registered or advertised.
TRELLO_READ_ONLY = "true"
# Trello data contains characters a Windows cp1252 console cannot encode.
PYTHONIOENCODING = "utf-8"
PYTHONUTF8 = "1"
# Credentials deliberately live in {PACKAGE_ROOT / '.env'} rather than here,
# so this shared config file never holds secrets.
""".rstrip() + "\n"


_BLOCK_RE = re.compile(
    rf"(?ms)^\[mcp_servers\.{re.escape(SERVER_NAME)}\].*?(?=^\[(?!mcp_servers\.{re.escape(SERVER_NAME)}\.)|\Z)"
)


def strip_existing(text: str) -> str:
    cleaned = _BLOCK_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", cleaned).rstrip() + "\n"


def backup(path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = path.with_suffix(f".toml.bak-{stamp}")
    shutil.copy2(path, target)
    return target


def check() -> int:
    path = config_path()
    print(f"config      : {path}")
    if not path.exists():
        print("status      : config.toml does not exist yet")
        return 1
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    servers = data.get("mcp_servers", {})
    print(f"mcp_servers : {sorted(servers)}")
    entry = servers.get(SERVER_NAME)
    if not entry:
        print(f"status      : '{SERVER_NAME}' is NOT registered")
        return 1
    print(f"status      : '{SERVER_NAME}' registered")
    for key in ("command", "args", "cwd", "enabled", "startup_timeout_sec", "tool_timeout_sec"):
        if key in entry:
            print(f"  {key:20}= {entry[key]}")
    for key, value in (entry.get("env") or {}).items():
        print(f"  env.{key:16}= {value}")

    env_file = PACKAGE_ROOT / ".env"
    raw_command = str(entry.get("command", ""))

    if raw_command == "docker":
        # Docker mode: nothing on the host filesystem to verify except the
        # env-file, so check the daemon and the image instead.
        print("  mode                 : Docker")
        docker_ok = shutil.which("docker") is not None
        print(f"  docker on PATH       : {docker_ok}")
        daemon = image = False
        if docker_ok:
            daemon = subprocess.run(
                ["docker", "info"], capture_output=True, text=True
            ).returncode == 0
            print(f"  Docker Desktop running: {daemon}")
            if daemon:
                image = subprocess.run(
                    ["docker", "image", "inspect", DOCKER_IMAGE],
                    capture_output=True, text=True,
                ).returncode == 0
                print(f"  image {DOCKER_IMAGE} built : {image}")
        print(f"  .env present         : {env_file.exists()}")
        return 0 if (docker_ok and daemon and image and env_file.exists()) else 1

    command = Path(raw_command)
    script = Path(str((entry.get("args") or [""])[0]))
    ok = command.exists() and script.exists()
    print(f"  interpreter exists   : {command.exists()}")
    print(f"  main.py exists       : {script.exists()}")
    print(f"  .env present         : {env_file.exists()}")
    return 0 if ok else 1


def install(remove: bool = False, docker: bool = False) -> int:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    original = path.read_text(encoding="utf-8") if path.exists() else ""
    if original.strip():
        saved = backup(path)
        print(f"backed up   : {saved}")

    updated = strip_existing(original) if original.strip() else ""
    if not remove:
        block = build_docker_block() if docker else build_block()
        updated = (updated.rstrip() + "\n" + block) if updated.strip() else block.lstrip()

    # Never leave a corrupt config behind: validate before writing.
    try:
        parsed = tomllib.loads(updated)
    except tomllib.TOMLDecodeError as error:
        print(f"ABORTED: generated config is not valid TOML: {error}", file=sys.stderr)
        return 2

    if not remove and SERVER_NAME not in parsed.get("mcp_servers", {}):
        print("ABORTED: server block did not survive validation", file=sys.stderr)
        return 2

    path.write_text(updated, encoding="utf-8")
    action = "removed from" if remove else "registered in"
    print(f"{SERVER_NAME} {action} {path}")

    if not remove:
        if docker:
            print(f"mode        : Docker (image {DOCKER_IMAGE}, volume {DOCKER_VOLUME})")
            print("              Docker Desktop must be running when you use ChatGPT.")
        print("\nNext: fully quit and reopen the ChatGPT app, then")
        print("Settings -> Plugins -> MCPs -> 'trello' should be listed and enabled.")
        env_file = PACKAGE_ROOT / ".env"
        if not env_file.exists():
            print(f"\nWARNING: {env_file} is missing; add TRELLO_API_KEY and TRELLO_TOKEN.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report current registration")
    parser.add_argument("--remove", action="store_true", help="unregister the server")
    parser.add_argument("--docker", action="store_true",
                        help="register the Docker image instead of local Python")
    args = parser.parse_args()

    if args.check:
        return check()
    return install(remove=args.remove, docker=args.docker)


if __name__ == "__main__":
    raise SystemExit(main())
