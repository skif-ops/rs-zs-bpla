"""The PKI registry of the pilot's stations, read by the server: every unit with its serial, lot, tenant and status,
before it ever connects (server/pki, ``registry.sqlite3`` in the PKI directory: ``ZS_PKI_DIR``, default ``data/pki``).
The admin catalog (station/access_api.py) and the monitoring page (station/health.py) list stations by it; without a
registry they list only the stations that reported."""
from __future__ import annotations

import os
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
PKI_DIR_ENV = "ZS_PKI_DIR"
PKI_TENANTS_ENV = "ZS_PKI_TENANTS"
PKI_INCLUDE_TWINS_ENV = "ZS_PKI_INCLUDE_TWINS"


def registry_path() -> Path:
    return Path(os.environ.get(PKI_DIR_ENV) or BASE / "data" / "pki") / "registry.sqlite3"


def registry_rows() -> tuple[list[dict], set[str]]:
    """The registered stations (``station_id``, ``serial``, ``tenant``, ``lot``, ``status``) and the tenants of the
    registry's lots; empty when there is no registry or it cannot be read."""
    path = registry_path()
    if not path.exists():
        return [], set()
    try:
        from pki.registry import Registry

        registry = Registry(path)
        selected = {t.strip() for t in os.environ.get(PKI_TENANTS_ENV, "").split(",") if t.strip()}
        include_twins = os.environ.get(PKI_INCLUDE_TWINS_ENV) == "1"
        rows = [{"station_id": r.station_id, "serial": r.serial, "tenant": r.tenant, "lot": r.lot, "status": r.status}
                for r in registry.list()
                if (not selected or r.tenant in selected) and (include_twins or r.lot != "TWIN-BENCH")]
        tenants = ({r["tenant"] for r in rows} if selected else set(registry.tenant_by_lot.values()))
        return rows, tenants
    except Exception:          # noqa: BLE001 - a registry this server cannot read: the callers list what reported
        return [], set()
