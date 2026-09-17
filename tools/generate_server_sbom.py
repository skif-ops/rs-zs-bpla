#!/usr/bin/env python3
"""Generate a deterministic CycloneDX 1.6 inventory from the hashed lockfile."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import quote
import uuid


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "server" / "requirements.lock.txt"
DEFAULT_OUTPUT = ROOT / "server" / "sbom" / "server.cdx.json"
APP_NAME = "muhoed-server"
APP_VERSION = "1.2.0-evt-pre-20.1"
ENTRY = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)(?:\s*;\s*(.+))?$")
HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


def normalized_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def purl(name: str, version: str) -> str:
    return f"pkg:pypi/{normalized_name(name)}@{quote(version, safe='.-_')}"


def parse_lock(text: str) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw_line in text.splitlines():
        header = raw_line.strip()
        if header.endswith("\\"):
            header = header[:-1].rstrip()
        match = ENTRY.fullmatch(header)
        if match:
            current = {
                "name": normalized_name(match.group(1)),
                "version": match.group(2),
                "marker": match.group(3),
                "hashes": [],
            }
            entries.append(current)
            continue
        if current is not None:
            current["hashes"].extend(HASH.findall(raw_line))

    if not entries:
        raise ValueError("lockfile contains no pinned packages")
    for entry in entries:
        if not entry["hashes"]:
            raise ValueError(f"lock entry has no SHA-256 hashes: {entry['name']}")
    return entries


def build_bom(lock_bytes: bytes) -> dict[str, object]:
    lock_sha = hashlib.sha256(lock_bytes).hexdigest()
    entries = parse_lock(lock_bytes.decode("utf-8"))
    root_ref = f"pkg:generic/{APP_NAME}@{quote(APP_VERSION, safe='.-_')}"
    components = []
    for entry in sorted(entries, key=lambda item: str(item["name"])):
        component = {
            "type": "library",
            "bom-ref": purl(str(entry["name"]), str(entry["version"])),
            "name": entry["name"],
            "version": entry["version"],
            "hashes": [
                {"alg": "SHA-256", "content": value}
                for value in sorted(set(entry["hashes"]))
            ],
            "purl": purl(str(entry["name"]), str(entry["version"])),
        }
        if entry["marker"]:
            component["properties"] = [
                {
                    "name": "zs:python:environment-marker",
                    "value": entry["marker"],
                }
            ]
        components.append(component)

    component_refs = [component["bom-ref"] for component in components]
    return {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, lock_sha)}",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "bom-ref": root_ref,
                "name": APP_NAME,
                "version": APP_VERSION,
                "properties": [
                    {"name": "zs:python:lock-sha256", "value": lock_sha},
                    {"name": "zs:python:target-version", "value": "3.12"},
                ],
            }
        },
        "components": components,
        "dependencies": [
            {"ref": root_ref, "dependsOn": component_refs},
            *({"ref": ref} for ref in component_refs),
        ],
    }


def rendered_bom(lock_path: Path) -> str:
    return json.dumps(build_bom(lock_path.read_bytes()), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    rendered = rendered_bom(args.lock)
    if args.check:
        if not args.output.is_file() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"SBOM is stale; regenerate with {Path(__file__).name}")
        print(f"Server CycloneDX SBOM is current: {args.output.relative_to(ROOT)}")
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.output.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
