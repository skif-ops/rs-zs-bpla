#!/usr/bin/env python3
"""QG-2 independent technical audit of the server lock and CycloneDX SBOM."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote
import uuid


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "server" / "requirements.lock.txt"
SBOM = ROOT / "server" / "sbom" / "server.cdx.json"
ENTRY = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)")
HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_lock(text: str) -> dict[str, tuple[str, set[str]]]:
    packages: dict[str, tuple[str, set[str]]] = {}
    current = None
    for line in text.splitlines():
        match = ENTRY.match(line)
        if match:
            current = normalized(match.group(1))
            require(current not in packages, f"duplicate package in lock: {current}")
            packages[current] = (match.group(2), set())
        elif current is not None:
            packages[current][1].update(HASH.findall(line))
    for name, (_, hashes) in packages.items():
        require(hashes, f"missing lock hashes: {name}")
    return packages


def main() -> int:
    lock_bytes = LOCK.read_bytes()
    lock = parse_lock(lock_bytes.decode("utf-8"))
    bom = json.loads(SBOM.read_text(encoding="utf-8"))

    require(bom.get("bomFormat") == "CycloneDX", "not a CycloneDX BOM")
    require(bom.get("specVersion") == "1.6", "CycloneDX version drift")
    require(bom.get("version") == 1, "unexpected BOM revision")
    require("timestamp" not in bom.get("metadata", {}), "SBOM is not reproducible")
    lock_sha = hashlib.sha256(lock_bytes).hexdigest()
    require(
        bom.get("serialNumber") == f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, lock_sha)}",
        "content-derived serial number mismatch",
    )

    root = bom["metadata"]["component"]
    require(root["name"] == "muhoed-server" and root["version"] == "1.2.0-evt-pre-20.1",
            "SBOM root identity drift")
    properties = {item["name"]: item["value"] for item in root.get("properties", [])}
    require(properties.get("zs:python:lock-sha256") == lock_sha,
            "SBOM is not bound to the runtime lock")
    require(properties.get("zs:python:target-version") == "3.12",
            "SBOM Python target drift")

    components = {}
    for component in bom.get("components", []):
        name = normalized(component["name"])
        require(name not in components, f"duplicate SBOM component: {name}")
        components[name] = component
    require(set(components) == set(lock), "SBOM and lock package sets differ")
    for name, (version, hashes) in lock.items():
        component = components[name]
        expected_purl = f"pkg:pypi/{name}@{quote(version, safe='.-_')}"
        require(component.get("type") == "library", f"wrong component type: {name}")
        require(component.get("version") == version, f"version mismatch: {name}")
        require(component.get("purl") == expected_purl and component.get("bom-ref") == expected_purl,
                f"PURL mismatch: {name}")
        sbom_hashes = {
            item["content"] for item in component.get("hashes", [])
            if item.get("alg") == "SHA-256"
        }
        require(sbom_hashes == hashes, f"distribution hash set mismatch: {name}")

    refs = {component["bom-ref"] for component in components.values()}
    dependency_rows = {row["ref"]: set(row.get("dependsOn", [])) for row in bom["dependencies"]}
    require(dependency_rows.get(root["bom-ref"]) == refs,
            "root dependency inventory is incomplete")
    require(set(dependency_rows) == refs | {root["bom-ref"]},
            "SBOM dependency references are incomplete")

    print(f"Server CycloneDX SBOM QG-2 independent audit: PASS ({len(lock)} components)")
    print(f"runtime lock SHA-256: {lock_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
