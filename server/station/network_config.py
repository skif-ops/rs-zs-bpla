"""Remote network configuration of a station (MQTT ICD addendum G, CMD_SET_NETWORK_CONFIG, code 6).

The command payload (key 7) is ``{0: patch}``: a station configuration patch in the BLE ``config_write`` format
(STATION_CONFIG_CBOR_v0_1 §2-3, canonical CBOR with integer keys), limited to the fields a server may change: server
host, MQTT/HTTPS ports, server certificate pin, tenant, topic prefix, preferred SIM and the two APNs, plus the
mandatory version.  The CA reference (the trust anchor in the modem), the region and the station id stay service-mode
or factory fields.  The station tries the new configuration on its next bring-up and keeps it only when a session comes
online with it; otherwise it rolls back to the stored one (heartbeat keys 21..23).

The JSON payload of the command (``StationCommand.payload``) names the fields; the checks mirror
firmware/src/zs_station_config.c so an operator error is refused before a command is queued.
"""
from __future__ import annotations

import ipaddress
import re

import cbor2

NETWORK_COMMAND = "CMD_SET_NETWORK_CONFIG"
PATCH_MAX_BYTES = 240
MQTT_TLS_PORTS = (8883, 443)            # the BG95 driver opens MQTT over TLS on these only (zs_bg95_configure_mqtt_tls)

# field -> patch key (STATION_CONFIG_CBOR_v0_1 §2); 5 (ca_reference) and 12 (region) are not remotely settable
PATCH_KEYS = {"version": 1, "server_host": 2, "mqtt_port": 3, "https_port": 4, "server_fingerprint": 6, "tenant": 7,
              "topic_prefix": 8, "preferred_sim": 9, "apn1": 10, "apn2": 11}
PATCH_FIELDS = {value: key for key, value in PATCH_KEYS.items()}
NETWORK_FIELDS = tuple(name for name in PATCH_KEYS if name != "version")

# heartbeat key 22 (addendum G)
NET_STATE = {0: "STABLE", 1: "ACCEPTED", 2: "TRIAL", 3: "ROLLED_BACK"}
# ACK REJECTED details (addendum G §2)
REJECT_DETAILS = {1: "unsupported", 2: "malformed patch", 3: "version not above the stored one",
                  4: "invalid configuration", 5: "field not remotely settable", 6: "another configuration on trial",
                  7: "no network field changes"}

_TOKEN = re.compile(r"^[A-Za-z0-9._-]*$")
_PREFIX = re.compile(r"^[A-Za-z0-9._/-]*$")
_APN = re.compile(r"^[A-Za-z0-9.-]*$")
_LABEL = re.compile(r"^[A-Za-z0-9-]{1,63}$")


def host_valid(host: str) -> bool:
    """IPv4 literal (no leading zeroes), IPv6 literal or RFC 1123 hostname of up to 64 characters (the station's rule)."""
    if not isinstance(host, str) or not 0 < len(host) <= 64:
        return False
    if re.fullmatch(r"[0-9.]+", host):
        parts = host.split(".")
        return len(parts) == 4 and all(p and len(p) <= 3 and (p == "0" or p[0] != "0") and int(p) <= 255 for p in parts)
    if ":" in host:
        if not re.fullmatch(r"[0-9A-Fa-f:]+", host) or "." in host:
            return False
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return False
        return all(len(g) <= 4 for g in host.split(":"))
    labels = host.split(".")
    if not all(_LABEL.match(label) and label[0] != "-" and label[-1] != "-" for label in labels):
        return False
    return not labels[-1].isdigit()


def _uint(value: object, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"network config {name} is outside {low}..{high}")
    return value


def _text(value: object, pattern: re.Pattern, limit: int, name: str, required: bool) -> str:
    if not isinstance(value, str) or len(value) > limit or not pattern.match(value) or (required and not value):
        raise ValueError(f"network config {name} is not a valid value")
    return value


def payload_to_wire(payload: dict) -> dict[int, object]:
    """``StationCommand.payload`` -> key 7 ``{0: patch}``; raises ValueError on anything the station would refuse."""
    if not isinstance(payload, dict) or set(payload) - set(PATCH_KEYS):
        raise ValueError("unsupported network config field (ca_reference and region are service-mode only)")
    if "version" not in payload:
        raise ValueError("network config needs a version above the station's current one")
    if not set(payload) & set(NETWORK_FIELDS):
        raise ValueError("network config changes no network field")
    patch: dict[int, object] = {1: _uint(payload["version"], 1, 0xFFFFFFFF, "version")}
    if "server_host" in payload:
        if not host_valid(payload["server_host"]):
            raise ValueError("network config server_host is not an IPv4/IPv6 literal or hostname")
        patch[2] = payload["server_host"]
    if "mqtt_port" in payload:
        patch[3] = _uint(payload["mqtt_port"], 1, 65535, "mqtt_port")
        if patch[3] not in MQTT_TLS_PORTS:
            raise ValueError("network config mqtt_port must be one the station's modem opens TLS on (8883 or 443)")
    if "https_port" in payload:
        patch[4] = _uint(payload["https_port"], 0, 65535, "https_port")
        if patch[4] and patch[4] == patch.get(3):
            raise ValueError("network config https_port equals mqtt_port")
    if "server_fingerprint" in payload:
        raw = payload["server_fingerprint"]
        try:
            pin = bytes.fromhex(raw) if isinstance(raw, str) else b""
        except ValueError:
            pin = b""
        if len(pin) != 32:
            raise ValueError("network config server_fingerprint is 64 hex characters (all zero = not pinned)")
        patch[6] = pin
    if "tenant" in payload:
        patch[7] = _text(payload["tenant"], _TOKEN, 16, "tenant", True)
    if "topic_prefix" in payload:
        prefix = _text(payload["topic_prefix"], _PREFIX, 32, "topic_prefix", True)
        if prefix.startswith("/") or prefix.endswith("/"):
            raise ValueError("network config topic_prefix has a leading or trailing '/'")
        patch[8] = prefix
    if "preferred_sim" in payload:
        patch[9] = _uint(payload["preferred_sim"], 1, 2, "preferred_sim")
    if "apn1" in payload:
        patch[10] = _text(payload["apn1"], _APN, 32, "apn1", False)
    if "apn2" in payload:
        patch[11] = _text(payload["apn2"], _APN, 32, "apn2", False)
        if patch[11] and patch.get(10) == "":
            raise ValueError("network config apn2 needs apn1")
    encoded = cbor2.dumps(patch, canonical=True)
    if len(encoded) > PATCH_MAX_BYTES:
        raise ValueError(f"network config patch exceeds {PATCH_MAX_BYTES} bytes")
    return {0: encoded}


def payload_from_wire(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict) or set(payload) != {0} or not isinstance(payload[0], bytes):
        raise ValueError("invalid network config payload keys")
    try:
        patch = cbor2.loads(payload[0])
    except Exception:  # noqa: BLE001 - any decoding error is a malformed patch
        raise ValueError("network config patch is not CBOR") from None
    if not isinstance(patch, dict) or not all(type(k) is int and k in PATCH_FIELDS for k in patch):
        raise ValueError("invalid network config patch keys")
    normalized = {PATCH_FIELDS[k]: (v.hex() if isinstance(v, bytes) else v) for k, v in sorted(patch.items())}
    if payload_to_wire(normalized)[0] != payload[0]:
        raise ValueError("network config patch is not canonical")
    return normalized


def next_version(heartbeat) -> int:
    """Version for the next patch: one above what the station reports (key 21); ValueError without a report."""
    detector = getattr(heartbeat, "detector", None) if heartbeat is not None else None
    current = getattr(detector, "net_config_version", 0) if detector is not None else 0
    if not current:
        raise ValueError("the station has not reported its network configuration version yet (heartbeat key 21)")
    return current + 1
