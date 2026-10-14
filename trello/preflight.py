"""Check whether this machine is ready, BEFORE changing anything.

Pure standard library and no dependencies, so it runs on whatever Python the
machine already has. Run this first in a live setup session: it turns unknown
territory into a 20-second report.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

OK, WARN, BAD = "ok", "warn", "BAD"
issues: list[str] = []
warnings: list[str] = []

# Missing Python only blocks the Python install route. With Docker running,
# install-docker.bat needs no Python at all, so it must not report NOT READY.
docker_ready = False


def line(status: str, label: str, detail: str = "") -> None:
    mark = {OK: "[ok]  ", WARN: "[warn]", BAD: "[STOP]"}[status]
    print(f"  {mark} {label}")
    if detail:
        print(f"         {detail}")
    if status == BAD:
        issues.append(label)
    elif status == WARN:
        warnings.append(label)


def check_windows() -> None:
    line(OK if platform.system() == "Windows" else WARN,
         f"OS: {platform.system()} {platform.release()}")


def check_pythons() -> None:
    """The py launcher lists every installed interpreter."""
    found: list[str] = []
    try:
        out = subprocess.run(["py", "-0p"], capture_output=True, text=True, timeout=20)
        for raw in (out.stdout or "").splitlines():
            raw = raw.strip()
            if raw.startswith("-V:") or raw.startswith("-3"):
                found.append(raw)
    except Exception:
        pass

    # With Docker available the Python route is optional, so downgrade to WARN.
    missing = WARN if docker_ready else BAD
    hint = (" (or just use install-docker.bat - no Python needed)"
            if docker_ready else "")

    usable = [f for f in found if "3.12" in f or "3.13" in f]
    if usable:
        line(OK, f"Python 3.12/3.13 available ({len(usable)} match)",
             usable[0][:90])
    elif found:
        line(missing, "Python is installed but not a usable version",
             "Need 3.12 or 3.13. Found: "
             + "; ".join(f.split()[0] for f in found[:4]) + hint)
    else:
        # py launcher missing - try bare python
        exe = shutil.which("python")
        if exe:
            try:
                v = subprocess.run([exe, "-c", "import sys;print('%d.%d'%sys.version_info[:2])"],
                                   capture_output=True, text=True, timeout=20).stdout.strip()
                if v in ("3.12", "3.13"):
                    line(OK, f"Python {v} on PATH", exe)
                else:
                    line(missing, f"Python {v} is not supported",
                         "Need 3.12 or 3.13" + hint)
            except Exception:
                line(missing, "Python found but could not be run", exe + hint)
        else:
            line(missing, "No Python installed",
                 ("Use install-docker.bat instead - no Python needed"
                  if docker_ready
                  else "install.bat can install it automatically via winget"))


def check_docker() -> None:
    """Docker is the no-Python route, so report it as a first-class option."""
    if not shutil.which("docker"):
        line(WARN, "Docker not installed",
             "Only needed if you want the no-Python install (install-docker.bat)")
        return
    try:
        running = subprocess.run(["docker", "info"], capture_output=True,
                                 text=True, timeout=60).returncode == 0
    except Exception:
        running = False
    if running:
        global docker_ready
        docker_ready = True
        line(OK, "Docker is installed and running",
             "You can use install-docker.bat - no Python needed")
        try:
            built = subprocess.run(["docker", "image", "inspect", "trello-mcp:latest"],
                                   capture_output=True, text=True, timeout=60).returncode == 0
            if built:
                line(OK, "Connector image already built (trello-mcp:latest)")
        except Exception:
            pass
    else:
        line(WARN, "Docker is installed but NOT running",
             "Start Docker Desktop and wait for 'Engine running' before install-docker.bat")


def check_winget() -> None:
    if shutil.which("winget"):
        line(OK, "winget available (can auto-install Python if needed)")
    else:
        line(WARN, "winget not available",
             "Python would have to be installed manually from python.org")


def _reachable(host: str, url: str, label: str) -> None:
    try:
        socket.gethostbyname(host)
    except Exception:
        line(BAD, f"{label} unreachable (DNS)", host)
        return
    try:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            line(OK, f"{label} reachable", f"HTTP {r.status}")
    except urllib.error.HTTPError as error:
        # Any HTTP status means the host answered, which is all we are
        # testing here. Trello returns 400/401 to an unauthenticated probe.
        line(OK, f"{label} reachable", f"HTTP {error.code} (auth not tested here)")
    except Exception as error:
        line(BAD, f"{label} blocked or unreachable", str(error)[:110])


def check_network() -> None:
    _reachable("pypi.org", "https://pypi.org/simple/", "PyPI (needed to install)")
    _reachable("api.trello.com", "https://api.trello.com/1/members/me", "Trello API")


def check_chatgpt() -> None:
    codex = Path.home() / ".codex"
    cfg = codex / "config.toml"
    if cfg.exists():
        line(OK, "ChatGPT/Codex config found", str(cfg))
    elif codex.exists():
        line(OK, "ChatGPT/Codex folder found (config will be created)", str(codex))
    else:
        line(WARN, "No ~/.codex folder yet",
             "Normal if MCP servers were never used. It will be created. "
             "Confirm the ChatGPT DESKTOP app is installed and has been opened once.")

    for name in ("ChatGPT.exe", "chatgpt.exe"):
        try:
            out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {name}"],
                                 capture_output=True, text=True, timeout=20)
            if name.lower() in (out.stdout or "").lower():
                line(OK, "ChatGPT app is currently running",
                     "Remember: it must be fully QUIT and reopened after setup")
                return
        except Exception:
            break


def check_disk_and_paths() -> None:
    here = Path(__file__).resolve().parent
    try:
        free = shutil.disk_usage(here).free / 1e9
        line(OK if free > 1.5 else BAD, f"Free disk space: {free:.1f} GB",
             "" if free > 1.5 else "Need at least ~1.5 GB")
    except Exception:
        line(WARN, "Could not read disk space")

    if any(part.lower() in {"temp", "tmp"} for part in here.parts):
        line(WARN, "Running from a temporary folder",
             "Move the folder somewhere permanent (Desktop/Documents) first - "
             "the ChatGPT app remembers this path")
    else:
        line(OK, "Folder location looks permanent", str(here.parent))

    # Mark of the Web: files extracted from a downloaded zip can be blocked.
    blocked = []
    for candidate in (here.parent / "install.bat", here / "main.py"):
        if candidate.exists() and Path(str(candidate) + ":Zone.Identifier").exists():
            blocked.append(candidate.name)
    if blocked:
        line(WARN, "Files are marked as downloaded from the internet",
             "Windows may block them. Right-click the ZIP -> Properties -> "
             "tick Unblock -> extract again.")


def check_existing_install() -> None:
    here = Path(__file__).resolve().parent
    venv = here / ".venv" / "Scripts" / "python.exe"
    env = here / ".env"
    if venv.exists():
        line(OK, "Already installed here (setup will reuse/update it)")
    if env.exists():
        line(OK, "Trello credentials already present (.env)")
    else:
        line(WARN, "No credentials yet",
             "Have the Trello API key and token ready: https://trello.com/power-ups/admin")


def main() -> int:
    print("\nTrello connector - machine readiness check")
    print("=" * 62)
    print(f"  running on: {sys.version.split()[0]}  ({sys.executable})")
    print("=" * 62 + "\n")

    check_windows()
    check_docker()
    check_pythons()
    check_winget()
    check_network()
    check_chatgpt()
    check_disk_and_paths()
    check_existing_install()

    print("\n" + "=" * 62)
    if issues:
        print(f"  NOT READY - {len(issues)} blocking issue(s):")
        for i in issues:
            print(f"    - {i}")
        print("\n  Fix these before running install.bat.")
    elif warnings:
        print(f"  READY, with {len(warnings)} thing(s) to be aware of.")
    else:
        print("  READY - run install.bat")
    print("=" * 62 + "\n")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
