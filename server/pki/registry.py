"""Station registry for the Muhoed PKI.

One row per station serial.  Lifecycle:

    created -> provisioned (certificate issued) -> commissioned (installer
    finished on site) -> revoked (certificate on CRL)

Lots: ``EVT-LOT-1`` = DIO-EVT-001..020, ``EVT-LOT-2`` = DIO-EVT-021..040,
``BENCH`` = DIO-EVT-B01 (station_id 901).  Each lot maps to an MQTT tenant
(topic segment) so the two groups and the bench unit never share topics.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from .ca import BENCH_LOT, BENCH_SERIAL, LOT_BY_SERIAL, PkiError, lot_for_serial, station_id_for_serial

DEFAULT_TENANT_BY_LOT = {"EVT-LOT-1": "pilot1", "EVT-LOT-2": "pilot2", BENCH_LOT: "bench"}
STATUSES = ("created", "provisioned", "commissioned", "revoked")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS stations (
  serial TEXT PRIMARY KEY,
  station_id INTEGER NOT NULL UNIQUE,
  lot TEXT NOT NULL,
  tenant TEXT NOT NULL,
  status TEXT NOT NULL,
  cert_serial_number TEXT,
  cert_fingerprint_sha256 TEXT,
  cert_not_after TEXT,
  created_at TEXT NOT NULL,
  provisioned_at TEXT,
  commissioned_at TEXT,
  revoked_at TEXT,
  revoke_reason TEXT,
  note TEXT,
  pairing_secret TEXT,
  engineer_key TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  serial TEXT,
  action TEXT NOT NULL,
  detail TEXT
);
"""


@dataclass(frozen=True)
class StationRow:
    serial: str
    station_id: int
    lot: str
    tenant: str
    status: str
    cert_serial_number: str | None
    cert_fingerprint_sha256: str | None
    cert_not_after: str | None
    created_at: str
    provisioned_at: str | None
    commissioned_at: str | None
    revoked_at: str | None
    revoke_reason: str | None
    note: str | None
    pairing_secret: str | None = None
    engineer_key: str | None = None


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


class Registry:
    def __init__(self, path: Path, tenant_by_lot: dict[str, str] | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.tenant_by_lot = dict(DEFAULT_TENANT_BY_LOT)
        if tenant_by_lot:
            self.tenant_by_lot.update(tenant_by_lot)
        self.lock = threading.Lock()
        with self._conn() as c:
            c.executescript(_SCHEMA)
            columns = {r[1] for r in c.execute("PRAGMA table_info(stations)")}
            if "pairing_secret" not in columns:  # registries created before labels (2026-09-22)
                c.execute("ALTER TABLE stations ADD COLUMN pairing_secret TEXT")
            if "engineer_key" not in columns:  # registries created before the B.9 session role (2026-09-23)
                c.execute("ALTER TABLE stations ADD COLUMN engineer_key TEXT")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        return c

    def _audit(self, c: sqlite3.Connection, serial: str | None, action: str, detail: str = "") -> None:
        c.execute("INSERT INTO audit(at, serial, action, detail) VALUES (?,?,?,?)", (_now(), serial, action, detail))

    # ---- creation
    def add(self, serial: str, note: str = "") -> StationRow:
        station_id = station_id_for_serial(serial)
        lot = lot_for_serial(serial)
        tenant = self.tenant_by_lot[lot]
        with self.lock, self._conn() as c:
            if c.execute("SELECT 1 FROM stations WHERE serial=?", (serial,)).fetchone():
                raise PkiError(f"{serial} already registered")
            c.execute(
                "INSERT INTO stations(serial, station_id, lot, tenant, status, created_at, note) VALUES (?,?,?,?,?,?,?)",
                (serial, station_id, lot, tenant, "created", _now(), note or None),
            )
            self._audit(c, serial, "add", f"lot={lot} tenant={tenant} station_id={station_id}")
        return self.get(serial)

    def add_all_lots(self) -> list[StationRow]:
        """Registers every serial of both lots plus the bench unit (idempotent)."""
        rows = []
        for _lot, numbers in LOT_BY_SERIAL:
            for n in numbers:
                serial = f"DIO-EVT-{n:03d}"
                rows.append(self.get(serial) if self.exists(serial) else self.add(serial))
        rows.append(self.get(BENCH_SERIAL) if self.exists(BENCH_SERIAL) else self.add(BENCH_SERIAL, "bench unit"))
        return rows

    # ---- queries
    def exists(self, serial: str) -> bool:
        with self._conn() as c:
            return c.execute("SELECT 1 FROM stations WHERE serial=?", (serial,)).fetchone() is not None

    def get(self, serial: str) -> StationRow:
        with self._conn() as c:
            row = c.execute("SELECT * FROM stations WHERE serial=?", (serial,)).fetchone()
        if row is None:
            raise PkiError(f"{serial} is not registered")
        return StationRow(**dict(row))

    def list(self, lot: str | None = None, status: str | None = None) -> list[StationRow]:
        query, args = "SELECT * FROM stations", []
        clauses = []
        if lot:
            clauses.append("lot=?"); args.append(lot)
        if status:
            clauses.append("status=?"); args.append(status)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY station_id"
        with self._conn() as c:
            return [StationRow(**dict(r)) for r in c.execute(query, args).fetchall()]

    # ---- label / pairing secret
    def ensure_pairing_secret(self, serial: str) -> str:
        """Returns the unit's pairing secret, generating it on first use (audited)."""
        from .label import new_pairing_secret
        with self.lock, self._conn() as c:
            row = c.execute("SELECT pairing_secret FROM stations WHERE serial=?", (serial,)).fetchone()
            if row is None:
                raise PkiError(f"{serial} is not registered")
            if row["pairing_secret"]:
                return row["pairing_secret"]
            secret = new_pairing_secret()
            c.execute("UPDATE stations SET pairing_secret=? WHERE serial=?", (secret, serial))
            self._audit(c, serial, "pairing_secret", "generated")
        return secret

    # ---- B.9 engineer key: 32 random bytes per station, hex. Goes to the station (station.json) and to the
    # engineer's app export; never on the label. Rotation invalidates both sides at once.
    def ensure_engineer_key(self, serial: str) -> str:
        import secrets
        with self.lock, self._conn() as c:
            row = c.execute("SELECT engineer_key FROM stations WHERE serial=?", (serial,)).fetchone()
            if row is None:
                raise PkiError(f"{serial} is not registered")
            if row["engineer_key"]:
                return row["engineer_key"]
            key = secrets.token_hex(32)
            c.execute("UPDATE stations SET engineer_key=? WHERE serial=?", (key, serial))
            self._audit(c, serial, "engineer_key", "generated")
        return key

    def rotate_engineer_key(self, serial: str, reason: str) -> str:
        import secrets
        key = secrets.token_hex(32)
        with self.lock, self._conn() as c:
            if c.execute("UPDATE stations SET engineer_key=? WHERE serial=?", (key, serial)).rowcount != 1:
                raise PkiError(f"{serial} is not registered")
            self._audit(c, serial, "engineer_key", f"rotated: {reason}")
        return key

    def audit_engineer_key_export(self, serial: str, who: str) -> None:
        with self.lock, self._conn() as c:
            self._audit(c, serial, "engineer_key", f"exported to {who}")

    def rotate_pairing_secret(self, serial: str, reason: str) -> str:
        from .label import new_pairing_secret
        secret = new_pairing_secret()
        with self.lock, self._conn() as c:
            if c.execute("UPDATE stations SET pairing_secret=? WHERE serial=?", (secret, serial)).rowcount != 1:
                raise PkiError(f"{serial} is not registered")
            self._audit(c, serial, "pairing_secret", f"rotated: {reason}")
        return secret

    def active(self) -> list[StationRow]:
        return [r for r in self.list() if r.status in ("provisioned", "commissioned")]

    def revoked(self) -> list[StationRow]:
        return self.list(status="revoked")

    # ---- lifecycle
    def mark_provisioned(self, serial: str, cert_serial_number: int, fingerprint_hex: str, not_after: str) -> StationRow:
        with self.lock, self._conn() as c:
            row = c.execute("SELECT status FROM stations WHERE serial=?", (serial,)).fetchone()
            if row is None:
                raise PkiError(f"{serial} is not registered")
            if row["status"] not in ("created", "revoked"):
                raise PkiError(f"{serial} already has an active certificate; revoke it first")
            c.execute(
                "UPDATE stations SET status='provisioned', cert_serial_number=?, cert_fingerprint_sha256=?, "
                "cert_not_after=?, provisioned_at=?, commissioned_at=NULL, revoked_at=NULL, revoke_reason=NULL WHERE serial=?",
                (format(cert_serial_number, "x"), fingerprint_hex, not_after, _now(), serial),
            )
            self._audit(c, serial, "provision", f"cert={cert_serial_number:x} fp={fingerprint_hex[:16]}")
        return self.get(serial)

    def mark_commissioned(self, serial: str, detail: str = "") -> StationRow:
        with self.lock, self._conn() as c:
            row = c.execute("SELECT status FROM stations WHERE serial=?", (serial,)).fetchone()
            if row is None or row["status"] != "provisioned":
                raise PkiError(f"{serial} must be provisioned before commissioning")
            c.execute("UPDATE stations SET status='commissioned', commissioned_at=? WHERE serial=?", (_now(), serial))
            self._audit(c, serial, "commission", detail)
        return self.get(serial)

    def revoke(self, serial: str, reason: str) -> StationRow:
        if not reason.strip():
            raise PkiError("revocation reason is required")
        with self.lock, self._conn() as c:
            row = c.execute("SELECT status, cert_serial_number FROM stations WHERE serial=?", (serial,)).fetchone()
            if row is None or row["status"] not in ("provisioned", "commissioned"):
                raise PkiError(f"{serial} has no active certificate to revoke")
            c.execute("UPDATE stations SET status='revoked', revoked_at=?, revoke_reason=? WHERE serial=?",
                      (_now(), reason.strip(), serial))
            self._audit(c, serial, "revoke", reason.strip())
        return self.get(serial)

    def revoked_cert_serials(self) -> list[tuple[int, dt.datetime]]:
        out = []
        for r in self.revoked():
            if r.cert_serial_number and r.revoked_at:
                out.append((int(r.cert_serial_number, 16), dt.datetime.fromisoformat(r.revoked_at)))
        return out

    def audit_log(self, limit: int = 200) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
