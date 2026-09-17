#!/usr/bin/env python3
"""QG-1 completeness check for hashed Python locks and CycloneDX SBOM."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


ROOT = Path(__file__).resolve().parents[1]
ENTRY = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)")
HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def locked_versions(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        match = ENTRY.match(line)
        if match:
            name = canonicalize_name(match.group(1))
            require(name not in result, f"duplicate lock entry: {name}")
            result[name] = match.group(2)
    return result


def validate_lock(source_path: str, lock_path: str) -> dict[str, str]:
    source = read(source_path)
    lock = read(lock_path)
    versions = locked_versions(lock)
    require(versions, f"empty lock: {lock_path}")
    require("--index-url" not in lock and "--extra-index-url" not in lock,
            f"index or credentials must not be embedded: {lock_path}")

    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        name = canonicalize_name(requirement.name)
        require(name in versions, f"direct dependency is absent from lock: {name}")
        require(Version(versions[name]) in requirement.specifier,
                f"locked {name}=={versions[name]} violates {requirement.specifier}")

    current = None
    hashes: dict[str, set[str]] = {}
    for raw_line in lock.splitlines():
        match = ENTRY.match(raw_line)
        if match:
            current = canonicalize_name(match.group(1))
            hashes[current] = set()
        elif current is not None:
            hashes[current].update(HASH.findall(raw_line))
    require(set(hashes) == set(versions), f"hash coverage drift: {lock_path}")
    for name, values in hashes.items():
        require(values, f"locked dependency has no SHA-256: {name}")
    return versions


def main() -> int:
    runtime = validate_lock("server/requirements.txt", "server/requirements.lock.txt")
    core = validate_lock("server/requirements-ci.txt", "server/requirements-ci.lock.txt")
    protocol = validate_lock(
        "server/requirements-protocol.txt",
        "server/requirements-protocol.lock.txt",
    )
    dockerfile = read("server/Dockerfile")
    ci = read(".github/workflows/ci.yml")
    server_ci = read(".github/workflows/server-core.yml")
    audit = read("server/EVT_PRE_20_RELEASE_AUDIT.md")

    require("COPY requirements.lock.txt ." in dockerfile and
            "pip install --no-cache-dir --require-hashes -r requirements.lock.txt" in dockerfile,
            "Docker image does not install the hashed runtime lock")
    for lock in (
        "requirements.lock.txt",
        "requirements-ci.lock.txt",
        "requirements-protocol.lock.txt",
    ):
        require(lock in ci, f"EVT CI does not consume {lock}")
    require("requirements-protocol.lock.txt" in server_ci,
            "server protocol workflow does not consume its minimal lock")
    require("--require-hashes" in ci and "--require-hashes" in server_ci,
            "CI does not enforce lock hashes")
    require("generate_server_sbom.py --check" in ci,
            "reproducible SBOM check is not bound to CI")
    require("3. ЗАКРЫТО" in audit and "requirements.lock.txt" in audit,
            "release audit does not record dependency blocker closure")

    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "generate_server_sbom.py"), "--check"],
        cwd=ROOT,
        check=True,
    )
    print(
        "Server supply-chain QG-1: PASS "
        f"({len(runtime)} runtime, {len(core)} core, {len(protocol)} protocol packages)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
