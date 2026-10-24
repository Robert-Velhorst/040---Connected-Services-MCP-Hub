"""Inspect installed code without starting the connector or opening its mirror."""

import hashlib
import importlib.metadata
import json
import os
import platform
import sqlite3
import ssl
import subprocess
from pathlib import Path


def main():
    if platform.python_version() != "3.15.1":
        raise RuntimeError("Expected the selected CPython security release")
    packages = sorted(
        [
            {"name": item.metadata["Name"], "version": item.version}
            for item in importlib.metadata.distributions()
        ],
        key=lambda item: item["name"].lower(),
    )
    native_modules = {}
    for name in ["_ssl", "_hashlib", "_sqlite3"]:
        module = __import__(name)
        file = Path(module.__file__)
        native_modules[name] = {
            "path": str(file),
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        }
    installed_os = subprocess.check_output(
        ["dpkg-query", "-W", "-f=${Package}\t${Version}\n"],
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "sqlite": sqlite3.sqlite_version,
                "python_ssl": ssl.OPENSSL_VERSION,
                "ca_roots": len(ssl.create_default_context().get_ca_certs()),
                "os_release": Path("/etc/os-release").read_text(encoding="utf-8"),
                "installed_os": installed_os,
                "installed_python": packages,
                "native_modules": native_modules,
                "uid": os.getuid(),
                "application_started": False,
                "operator_database_opened": False,
                "provider_requests": 0,
                "all_components_current": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
