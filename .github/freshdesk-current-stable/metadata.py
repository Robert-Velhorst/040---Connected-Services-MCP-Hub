"""Guard an owned hosted normal-resolution candidate; never publish its outputs."""

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess


TARGETS = {
    "cachetools": "7.2.6",
    "cyclopts": "5.3.1",
    "fastmcp": "4.1.4",
    "fastmcp-slim": "4.1.4",
    "keyring": "25.7.0",
    "ruff": "0.17.3",
    "sse-starlette": "3.6.0",
    "starlette": "1.10.0",
}
GENERATED = {
    "freshdesk/pyproject.toml",
    "freshdesk/uv.lock",
    "freshdesk/requirements.txt",
    "freshdesk/requirements-build.lock",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["prepare", "installed", "verify"], required=True)
    args = parser.parse_args()
    assert os.environ.get("GITHUB_ACTIONS") == "true"
    assert os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    assert os.environ.get("RUNNER_OS") == "Linux"
    # This helper owns exactly one checkout and one sibling report directory.
    # Neither path is accepted through CLI arguments or the environment.
    root = Path(__file__).resolve(strict=True).parents[2]
    reports = root.parent / "freshdesk-current-stable-evidence"
    assert not reports.is_symlink()
    assert reports.resolve().parent == root.parent
    reports.mkdir(parents=True, exist_ok=True)

    def git(*values):
        return subprocess.check_output(["git", "-C", str(root), *values])

    def payloads():
        result = {}
        for item in git("ls-files", "-z").split(b"\0"):
            if not item:
                continue
            name = item.decode("utf-8")
            relative = PurePosixPath(name)
            if relative.is_absolute() or any(part in {".", ".."} for part in relative.parts):
                raise ValueError("Tracked source path must stay inside the checkout")
            path = root.joinpath(*(os.path.basename(part) for part in relative.parts))
            if not path.parent.resolve(strict=True).is_relative_to(root):
                raise ValueError("Tracked source parent escapes the checkout")
            data = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
            result[name] = hashlib.sha256(data).hexdigest()
        return result

    candidate = Path(__file__).with_name("pyproject.toml").read_bytes()
    if args.phase == "prepare":
        assert not git("status", "--porcelain").strip()
        record = {
            "worker_head": git("rev-parse", "HEAD").decode().strip(),
            "worker_tree": git("rev-parse", "HEAD^{tree}").decode().strip(),
            "source_payloads": payloads(),
            "candidate_manifest_sha256": hashlib.sha256(candidate).hexdigest(),
            "operator_data_read": False,
        }
        (reports / "source-before.json").write_text(json.dumps(record, indent=2) + "\n")
        (root / "freshdesk/pyproject.toml").write_bytes(candidate)
        return

    if args.phase == "installed":
        # Import only: do not construct a store or read/write any credential.
        from key_value.aio.stores.keyring import KeyringStore

        versions = {
            re.sub(r"[-_.]+", "-", dist.metadata["Name"]).lower(): dist.version
            for dist in importlib.metadata.distributions()
        }
        for name, version in TARGETS.items():
            assert versions.get(name) == version, (name, versions.get(name), version)
        assert all(re.fullmatch(r"(?:\d+!)?\d+(?:\.\d+)*(?:\.post\d+)?", value)
                   for value in versions.values()), "Non-release version selected"
        (reports / "actual-installed-package-versions.json").write_text(
            json.dumps({"versions": versions, "required_targets": TARGETS,
                        "retained_keyring_backend_import": KeyringStore.__module__ + "." + KeyringStore.__name__,
                        "credential_store_constructed_or_accessed": False,
                        "full_native_SDK_image_provider_and_data_acceptance": False}, indent=2) + "\n"
        )
        return

    before = json.loads((reports / "source-before.json").read_text())
    after = payloads()
    assert set(after) == set(before["source_payloads"])
    changed = {name for name in after if after[name] != before["source_payloads"][name]}
    assert changed <= GENERATED, changed
    assert (root / "freshdesk/pyproject.toml").read_bytes() == candidate
    diff_names = set(git("diff", "--name-only").decode().splitlines())
    assert diff_names <= GENERATED, diff_names
    for name in sorted(GENERATED):
        shutil.copyfile(root / name, reports / Path(name).name)
    for name in ["source-results.xml", "transport-security-results.xml", "native-runtime.json",
                 "python-audit.json", "requirements-audit.lock"]:
        path = root / "freshdesk" / name
        if path.is_file():
            shutil.copyfile(path, reports / name)
    (reports / "source-after.json").write_text(json.dumps({
        "source_payloads": after,
        "changed_generated_inputs": sorted(changed),
        "all_other_original_cases_helpers_assertions_fixtures_source_and_workflows_unchanged": True,
        "normal_resolution_and_case_results_require_separate_success": True,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
