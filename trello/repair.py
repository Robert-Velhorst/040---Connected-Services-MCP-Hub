"""Diagnose and repair every known cause of "Trello connector unavailable".

Checks each failure mode in the order it breaks the chain, fixes what it can,
and prints exactly what a human must do for the rest. Safe to run repeatedly.

Deliberately dependency-free (standard library only) so it still runs when the
virtual environment or the Docker image is the thing that is broken.

    python repair.py            diagnose and repair
    python repair.py --dry-run  diagnose only, change nothing
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

APP = Path(__file__).resolve().parent
ROOT = APP.parent
ENV_FILE = APP / ".env"
CONFIG = Path.home() / ".codex" / "config.toml"
IMAGE = "trello-mcp:latest"
VOLUME = "trello-mcp-data"

DRY = "--dry-run" in sys.argv

fixed: list[str] = []
manual: list[str] = []


def say(status: str, text: str, detail: str = "") -> None:
    mark = {"ok": "[ok]  ", "fix": "[FIXED]", "stop": "[STOP]", "info": "      "}[status]
    print(f"  {mark} {text}")
    if detail:
        for chunk in detail.splitlines():
            print(f"          {chunk}")


def run(cmd: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


# --------------------------------------------------------------------- checks

def registered_mode() -> str | None:
    """Which install the ChatGPT app is currently pointed at, if any."""
    if not CONFIG.exists():
        return None
    text = CONFIG.read_text(encoding="utf-8", errors="replace")
    block = re.search(
        r"(?ms)^\[mcp_servers\.trello\].*?(?=^\[(?!mcp_servers\.trello\.)|\Z)", text
    )
    if not block:
        return None
    body = block.group(0)
    if re.search(r"^\s*url\s*=", body, re.M):
        return "remote"
    command = re.search(r'^\s*command\s*=\s*[\'"]([^\'"]+)', body, re.M)
    if not command:
        return None
    return "docker" if command.group(1) == "docker" else "python"


def _docker_usable() -> bool:
    return bool(shutil.which("docker")) and run(["docker", "info"]).returncode == 0


def check_docker() -> str | None:
    """Returns 'docker' | 'python' | None(blocked).

    Honours whatever is already registered when that install still works, so
    running this on a machine with both Docker and Python does not flip the
    registration back and forth on every run.
    """
    py = APP / ".venv" / "Scripts" / "python.exe"
    current = registered_mode()

    if current == "docker" and _docker_usable():
        say("ok", "Docker is installed and running (matches the registered setup)")
        return "docker"
    if current == "python" and py.exists():
        say("ok", "Local Python install found (matches the registered setup)")
        return "python"

    if py.exists():
        say("ok", f"Local Python install found ({py.parent.parent.name})")
        return "python"

    if not shutil.which("docker"):
        say("stop", "Neither Python nor Docker is set up on this computer.")
        manual.append(
            "Install Docker Desktop (https://www.docker.com/products/docker-desktop/) "
            "then run install-docker.bat"
        )
        return None

    say("ok", "Docker is installed")
    if run(["docker", "info"]).returncode != 0:
        say("stop", "Docker Desktop is installed but NOT RUNNING")
        manual.append(
            "Start Docker Desktop from the Start menu. Wait until the whale icon "
            "says 'Engine running', then run this again."
        )
        return None
    say("ok", "Docker Desktop is running")
    return "docker"


def check_image() -> bool:
    if run(["docker", "image", "inspect", IMAGE]).returncode == 0:
        say("ok", f"Container image present ({IMAGE})")
        return True

    say("info", f"Container image {IMAGE} is MISSING (this alone breaks the connector)")
    if DRY:
        manual.append(f"docker build -t {IMAGE} \"{APP}\"")
        return False

    print("          building it now, this takes 2-4 minutes...")
    built = run(["docker", "build", "-t", IMAGE, str(APP)], timeout=1800)
    if built.returncode != 0:
        say("stop", "Image build FAILED", (built.stderr or built.stdout or "")[-600:])
        manual.append(f'Run manually to see the error:  docker build -t {IMAGE} "{APP}"')
        return False
    say("fix", "Container image rebuilt")
    fixed.append("rebuilt the container image")
    return True


def check_volume() -> None:
    if run(["docker", "volume", "inspect", VOLUME]).returncode == 0:
        say("ok", f"Storage volume present ({VOLUME})")
        return
    if DRY:
        manual.append(f"docker volume create {VOLUME}")
        return
    run(["docker", "volume", "create", VOLUME])
    say("fix", f"Storage volume created ({VOLUME})")
    fixed.append("created the storage volume")


def check_env() -> bool:
    if not ENV_FILE.exists():
        say("stop", "Trello credentials file is missing (trello\\.env)")
        manual.append("Run install-docker.bat (or install.bat) and paste the key and token.")
        return False

    text = ENV_FILE.read_text(encoding="utf-8", errors="replace")
    key = re.search(r"^TRELLO_API_KEY=(.*)$", text, re.M)
    token = re.search(r"^TRELLO_TOKEN=(.*)$", text, re.M)
    if not key or not token or not key.group(1).strip() or not token.group(1).strip():
        say("stop", "Credentials file exists but the key or token is blank")
        manual.append("Delete trello\\.env and run install-docker.bat again.")
        return False

    # Quotes/spaces break docker --env-file, which parses the file literally.
    bad = [
        line for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
        and re.match(r'^\s*\w+\s*=\s*["\']', line)
    ]
    if bad:
        say("stop", "Credentials file has quoted values, which Docker cannot read")
        manual.append("Remove the quotation marks around the values in trello\\.env")
        return False

    say("ok", "Credentials file looks well-formed")
    return _check_trello(key.group(1).strip(), token.group(1).strip())


def _check_trello(key: str, token: str) -> bool:
    """Validate the credentials, tolerating Trello's random bot-check blocks.

    Trello's edge answers roughly 1 in 10 valid requests with HTTP 405 and an
    HTML "Human Verification" page. Without retrying, this tool would tell the
    user their credentials are broken when they are perfectly fine -- the worst
    possible failure for a diagnostic. Retry before believing any 405/503.
    """
    import time

    url = "https://api.trello.com/1/members/me?" + urllib.parse.urlencode(
        {"key": key, "token": token, "fields": "username,fullName"}
    )

    last_code: int | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                me = json.loads(r.read().decode())
            say("ok", f"Trello accepted the credentials (signed in as {me.get('username')})")
            return True
        except urllib.error.HTTPError as e:
            last_code = e.code
            if e.code in (401, 400):
                # An unambiguous auth rejection: no point retrying.
                say("stop", "Trello REJECTED the API key or token")
                manual.append(
                    "Get fresh values from https://trello.com/power-ups/admin, then "
                    "delete trello\\.env and run install-docker.bat again."
                )
                return False
            if e.code in (405, 429, 503) and attempt < 4:
                time.sleep(1.5 * (attempt + 1))
                continue
            break
        except Exception as error:  # noqa: BLE001
            say("stop", "Could not reach Trello at all", str(error)[:200])
            manual.append("Check the internet connection / firewall for api.trello.com")
            return False

    say("stop", f"Trello kept returning HTTP {last_code} after 5 attempts")
    manual.append(
        "Trello's anti-bot filter is blocking this computer right now. It usually "
        "clears within a few minutes - wait, then run fix.bat again. The connector "
        "itself retries automatically, so this does not affect normal use."
    )
    return False


def check_registration(mode: str) -> bool:
    """The cause behind the tunnel 404: a stale or URL-based server entry."""
    if not CONFIG.exists():
        say("info", "Not registered with the ChatGPT app yet")
        return _register(mode)

    text = CONFIG.read_text(encoding="utf-8", errors="replace")
    block = re.search(
        r"(?ms)^\[mcp_servers\.trello\].*?(?=^\[(?!mcp_servers\.trello\.)|\Z)", text
    )
    if not block:
        say("info", "No 'trello' entry in the ChatGPT config")
        return _register(mode)

    body = block.group(0)

    # A url = line means this is the OLD remote/tunnel server. That is what
    # produces "MCP SSE probe returned 404" - there is no local process at all.
    if re.search(r"^\s*url\s*=", body, re.M):
        say("info", "Found an OLD remote 'trello' entry that points at a URL/tunnel")
        say("info", "  -> this is the cause of 'MCP SSE probe returned 404'")
        if DRY:
            manual.append("Re-run install-docker.bat to replace the old remote entry")
            return False
        return _register(mode, replacing_remote=True)

    command = re.search(r'^\s*command\s*=\s*[\'"]([^\'"]+)', body, re.M)
    cmd = command.group(1) if command else ""
    if mode == "docker" and cmd != "docker":
        say("info", f"Entry points at '{cmd}' but this machine uses Docker")
        return _register(mode)
    if mode == "python" and cmd == "docker":
        say("info", "Entry points at Docker but a local Python install is present")
        return _register(mode)
    if mode == "python" and cmd and not Path(cmd).exists():
        say("info", "Entry points at a Python that no longer exists (folder moved?)")
        return _register(mode)

    say("ok", f"Registered correctly with the ChatGPT app (mode: {mode})")
    return True


def _register(mode: str, replacing_remote: bool = False) -> bool:
    if DRY:
        manual.append("Run install-docker.bat (or install.bat) to register")
        return False

    if CONFIG.exists() and CONFIG.read_text(encoding="utf-8", errors="replace").strip():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(CONFIG, CONFIG.with_suffix(f".toml.bak-{stamp}"))

    if mode == "docker":
        ps1 = APP / "register-docker.ps1"
        result = run([
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(ps1), "-EnvFile", str(ENV_FILE),
            "-Image", IMAGE, "-Volume", VOLUME,
        ])
    else:
        py = APP / ".venv" / "Scripts" / "python.exe"
        result = run([str(py), str(APP / "setup_codex.py")])

    if result.returncode != 0:
        say("stop", "Could not update the ChatGPT config",
            (result.stderr or result.stdout or "")[-400:])
        manual.append("Run install-docker.bat manually")
        return False

    what = "Replaced the dead remote entry with the local connector" if replacing_remote \
        else "Registered the connector with the ChatGPT app"
    say("fix", what)
    fixed.append(what.lower())
    return True


def check_launch(mode: str) -> bool:
    """Actually start the server the way the app does, and see if it responds."""
    if mode == "docker":
        cmd = ["docker", "run", "--rm", "--env-file", str(ENV_FILE),
               "-v", f"{VOLUME}:/data", IMAGE, "python", "-c",
               "import server.settings as s; print('OK', bool(s.api_key()))"]
    else:
        py = APP / ".venv" / "Scripts" / "python.exe"
        cmd = [str(py), "-c",
               "import sys; sys.path.insert(0, r'%s'); "
               "import server.settings as s; print('OK', bool(s.api_key()))" % APP]

    result = run(cmd, timeout=300)
    if result.returncode == 0 and "OK True" in (result.stdout or ""):
        say("ok", "The connector starts and can read its credentials")
        return True
    say("stop", "The connector failed to start",
        (result.stderr or result.stdout or "")[-500:])
    manual.append("Send the message above to your developer.")
    return False


def main() -> int:
    print("\n" + "=" * 62)
    print("  Trello connector - diagnose and repair")
    if DRY:
        print("  (dry run: nothing will be changed)")
    print("=" * 62 + "\n")

    mode = check_docker()
    if mode is None:
        return report()

    if mode == "docker":
        if not check_image():
            return report()
        check_volume()

    if not check_env():
        return report()

    check_registration(mode)
    check_launch(mode)
    return report()


def report() -> int:
    print("\n" + "=" * 62)
    if fixed:
        print("  REPAIRED:")
        for f in fixed:
            print(f"    - {f}")
    if manual:
        print("  STILL NEEDS YOU TO DO THIS:")
        for m in manual:
            print(f"    - {m}")
    if not manual:
        print("  Everything checks out.")
        print()
        print("  NEXT: fully QUIT the ChatGPT app (right-click its taskbar icon")
        print("        near the clock -> Quit) and open it again.")
        print("        Then ask ChatGPT:")
        print('          "Use trello_account_overview and tell me how many')
        print('           workspaces and boards I have."')
    print("=" * 62 + "\n")
    return 1 if manual else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(1)
