"""Who sees a file analysis (docs/SERVER_ACCESS_CONTROL_2026-10-02.md, §11).

The pages of one file and of localization (``/single``, ``/localization``, the API routes ``/api/analyze-single`` and
``/api/localize``) work with uploaded recordings, not with stations, so the station scope of an account says nothing
about them.  Instead every analysis (one ``output/<id>`` directory with its plots, reports and separated audio, which
may carry speech like event audio does) belongs to the account that ran it:

* ``record_owner`` writes ``output/<id>/.owner.json`` (the account, its tenants and stations) when the analysis
  starts;
* ``may_read`` lets an analysis be seen by the account that made it, by an account without limits (no tenants, no
  stations: the security admin, ``skif_root``, an unlimited operator), and by an account whose tenants include every
  tenant of the maker; an analysis of an account limited only by stations, or of an unlimited account, is its own;
* an analysis without an owner file (made before this, or on the isolated bench where no operator is checked) is
  seen by unlimited accounts only.

``resolve_analysis_file`` is what ``/artifact`` and ``/download`` serve: a file inside an analysis directory the
account may see.  Anything else under ``output`` (``output/backups`` of station/backup.py, the log, a hidden file, a
path outside) answers like a missing file (404): nothing there is a page artifact.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from config import settings

OWNER_FILE = ".owner.json"
ANALYSIS_ID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def operator_of(request) -> dict[str, Any] | None:
    """The account of a request (``request.state.operator`` of operator_auth), or None on the bench."""
    return getattr(request.state, "operator", None)


def record_owner(output_dir: Path, operator: dict[str, Any] | None) -> dict[str, Any]:
    """Writes who made the analysis in ``output_dir`` and returns the record."""
    owner = {"name": None, "tenants": [], "stations": [], "created_us": int(time.time() * 1_000_000)}
    if operator:
        owner.update(name=operator.get("name"), tenants=sorted(str(t) for t in operator.get("tenants") or [] if t),
                     stations=sorted(int(s) for s in operator.get("stations") or []))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / OWNER_FILE).write_text(json.dumps(owner, ensure_ascii=False), encoding="utf-8")
    return owner


def owner_of(analysis_dir: Path) -> dict[str, Any] | None:
    """The owner record of an analysis directory, or None when there is none that can be read."""
    try:
        owner = json.loads((Path(analysis_dir) / OWNER_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return owner if isinstance(owner, dict) else None


def may_read(operator: dict[str, Any] | None, owner: dict[str, Any] | None) -> bool:
    """Whether the account ``operator`` sees the analysis of ``owner`` (see the module docstring)."""
    if operator is None:                                            # the bench: no operator is checked
        return True
    tenants = {str(t) for t in operator.get("tenants") or [] if t}
    stations = {int(s) for s in operator.get("stations") or []}
    if not tenants and not stations:                                # an unlimited account sees every analysis
        return True
    if not owner or not owner.get("name"):                          # no owner known: unlimited accounts only
        return False
    if owner["name"] == operator.get("name"):
        return True
    owner_tenants = {str(t) for t in owner.get("tenants") or [] if t}
    if not owner_tenants:                                           # unlimited or station-limited maker: its own
        return False
    return bool(tenants) and owner_tenants <= tenants


def resolve_analysis_file(path: str, operator: dict[str, Any] | None) -> Path | None:
    """The artifact ``path`` when it lies inside an analysis directory the account may see, else None."""
    root = settings.output_dir.resolve()
    try:
        target = Path(path).resolve(strict=True)
        rel = target.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return None
    parts = rel.parts
    if len(parts) < 2 or not ANALYSIS_ID_RE.match(parts[0]) or any(p.startswith(".") for p in parts):
        return None
    if not target.is_file() or not may_read(operator, owner_of(root / parts[0])):
        return None
    return target
