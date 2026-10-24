# Source verification adapted from 026-YT-automator-fixed at a67c432ff328bbdbb3aa10c0bc709f02699c2abd.
"""Build pinned client libraries in a disposable Linux image stage.

No database server is built, started or contacted. The selected prefix must be
absent; this command never replaces the host SDK or system crypto libraries.
"""

import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "native-client-runtime.json").read_text(encoding="utf-8"))
PREFIX = Path(SPEC["prefix"])


def validate_source_url(url):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.hostname
        not in {
            "github.com",
            "release-assets.githubusercontent.com",
            "www.sqlite.org",
            "www.python.org",
        }
    ):
        raise RuntimeError("Native source URL is outside the verified upstream hosts")


class SourceRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_source_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def run(command, cwd, env=None):
    subprocess.run(command, cwd=cwd, env=env, check=True, timeout=1200)


def source_archive(component, directory):
    archive = directory / (component["version"] + ".archive")
    digest = hashlib.new(component.get("digest_algorithm", "sha256"))
    size = 0
    validate_source_url(component["url"])
    with (
        build_opener(SourceRedirects()).open(component["url"], timeout=60) as response,
        archive.open("xb") as output,
    ):
        validate_source_url(response.url)
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > 100 * 1024 * 1024:
                raise RuntimeError("Native source archive exceeds its download limit")
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != component["sha256"]:
        raise RuntimeError("Native source archive checksum mismatch")
    destination = directory / "source"
    destination.mkdir()
    with tarfile.open(archive) as source:
        members = source.getmembers()
        if len(members) > 50000 or sum(item.size for item in members) > 1024**3:
            raise RuntimeError("Native source archive exceeds its extraction limit")
        source.extractall(destination, filter="data")
    roots = list(destination.iterdir())
    if len(roots) != 1 or not roots[0].is_dir() or roots[0].is_symlink():
        raise RuntimeError("Native archive must contain one source directory")
    return roots[0]


def package(name, version, source_name, directory, output, architecture):
    control = directory / "DEBIAN"
    control.mkdir()
    control.joinpath("control").write_text(
        f"Package: {name}\nVersion: {version}-0local1\nArchitecture: {architecture}\n"
        f"Source: {source_name} ({version}-0local1)\nSection: libs\nPriority: optional\n"
        + ("Multi-Arch: same\n" if name == "libsqlite3-0" else "")
        + "Maintainer: MCP Hub runtime contributors\nDepends: libc6\n"
        f"Description: Source-verified {source_name} runtime for MCP Hub\n",
        encoding="utf-8",
    )
    run(
        ["dpkg-deb", "--root-owner-group", "--build", str(directory), str(output)], ROOT
    )


def main():
    if (
        sys.platform != "linux"
        or ROOT != Path("/native-build")
        or os.environ.get("MCPHUB_DISPOSABLE_BUILD_SDK") != "1"
        or SPEC["schema_version"] != 1
        or PREFIX != Path("/opt/mcphub-native")
        or PREFIX.exists()
    ):
        raise RuntimeError(
            "Native builds require the fresh disposable SDK and dedicated prefix"
        )
    output = Path("/native-output")
    output.mkdir()
    architecture = subprocess.check_output(
        ["dpkg", "--print-architecture"], text=True
    ).strip()
    multiarch = subprocess.check_output(
        ["dpkg-architecture", "-qDEB_HOST_MULTIARCH"], text=True
    ).strip()
    if not all(
        re.fullmatch(r"[a-z0-9_-]+", value) for value in [architecture, multiarch]
    ):
        raise RuntimeError("Unsupported Debian architecture")
    with tempfile.TemporaryDirectory(prefix="mcphub-native-source-") as temporary:
        root = Path(temporary)
        ssl_dir = root / "openssl"
        ssl_dir.mkdir()
        source = source_archive(SPEC["openssl"], ssl_dir)
        run(
            [
                "./Configure",
                "shared",
                "--prefix=" + str(PREFIX),
                "--libdir=lib",
                "--openssldir=/usr/lib/ssl",
                "-Wl,-rpath," + str(PREFIX / "lib"),
            ],
            source,
        )
        run(["make", "-j2"], source)
        run(["make", "install_sw"], source)
        ssl_package = root / "ssl-package"
        lib_dir = ssl_package / str(PREFIX / "lib").lstrip("/")
        lib_dir.mkdir(parents=True)
        libraries = {}
        for name in ["libssl.so.4", "libcrypto.so.4"]:
            file = PREFIX / "lib" / name
            if not file.is_file() or file.is_symlink():
                raise RuntimeError("Expected actual OpenSSL runtime libraries")
            shutil.copyfile(file, lib_dir / name)
            libraries[str(file)] = hashlib.sha256(file.read_bytes()).hexdigest()
        doc = ssl_package / "usr/share/doc/libssl4"
        doc.mkdir(parents=True)
        shutil.copyfile(source / "LICENSE.txt", doc / "copyright")
        provenance = {"source": SPEC["openssl"], "libraries": libraries}
        doc.joinpath("source-provenance.json").write_text(
            json.dumps(provenance, indent=2) + "\n"
        )
        package(
            "libssl4",
            SPEC["openssl"]["version"],
            "openssl",
            ssl_package,
            output / "mcphub-openssl.deb",
            architecture,
        )

        sqlite_dir = root / "sqlite"
        sqlite_dir.mkdir()
        sqlite = source_archive(SPEC["sqlite"], sqlite_dir)
        library_dir = f"/usr/lib/{multiarch}"
        flags = [
            "-O2",
            "-fPIC",
            "-shared",
            "-Wl,-soname,libsqlite3.so.0",
            "-DSQLITE_THREADSAFE=1",
            "-DSQLITE_USE_URI=1",
            "-DSQLITE_ENABLE_COLUMN_METADATA",
            "-DSQLITE_SECURE_DELETE",
            "-DSQLITE_ENABLE_UNLOCK_NOTIFY",
            "-DSQLITE_ENABLE_RTREE",
            "-DSQLITE_ENABLE_GEOPOLY",
            "-DSQLITE_ENABLE_DBSTAT_VTAB",
            "-DSQLITE_SOUNDEX",
            "-DSQLITE_MAX_VARIABLE_NUMBER=250000",
            "-DSQLITE_ENABLE_FTS3",
            "-DSQLITE_ENABLE_FTS3_PARENTHESIS",
            "-DSQLITE_ENABLE_FTS4",
            "-DSQLITE_ENABLE_FTS5",
            "-DSQLITE_ENABLE_SESSION",
            "-DSQLITE_ENABLE_PREUPDATE_HOOK",
            "-DSQLITE_ENABLE_MATH_FUNCTIONS",
        ]
        sqlite_package = root / "sqlite-package"
        target_dir = sqlite_package / library_dir.lstrip("/")
        target_dir.mkdir(parents=True)
        library = target_dir / "libsqlite3.so.0.8.6"
        run(
            [
                "cc",
                *flags,
                str(sqlite / "sqlite3.c"),
                "-lm",
                "-ldl",
                "-pthread",
                "-o",
                str(library),
            ],
            sqlite,
        )
        library.chmod(0o644)
        (target_dir / "libsqlite3.so.0").symlink_to(library.name)
        actual = target_dir / "libsqlite3.so.0"
        engine = ctypes.CDLL(str(actual))
        engine.sqlite3_libversion.restype = ctypes.c_char_p
        if engine.sqlite3_libversion().decode("ascii") != SPEC["sqlite"]["version"]:
            raise RuntimeError(
                "Compiled SQLite version differs from the selected source"
            )
        sqlite_doc = sqlite_package / "usr/share/doc/libsqlite3-0"
        sqlite_doc.mkdir(parents=True)
        header = re.search(
            r"/\*.*?\*/", (sqlite / "sqlite3.c").read_text(encoding="utf-8"), re.DOTALL
        )[0]
        sqlite_doc.joinpath("copyright").write_text(
            header + "\nhttps://www.sqlite.org/copyright.html\n"
        )
        sqlite_provenance = {
            "source": SPEC["sqlite"],
            "cflags": flags,
            "library_sha256": hashlib.sha256(actual.read_bytes()).hexdigest(),
        }
        sqlite_doc.joinpath("source-provenance.json").write_text(
            json.dumps(sqlite_provenance, indent=2) + "\n"
        )
        package(
            "libsqlite3-0",
            SPEC["sqlite"]["version"],
            "sqlite3",
            sqlite_package,
            output / "mcphub-sqlite.deb",
            architecture,
        )
        output.joinpath("build-provenance.json").write_text(
            json.dumps({"openssl": provenance, "sqlite": sqlite_provenance}, indent=2)
            + "\n"
        )


if __name__ == "__main__":
    main()
