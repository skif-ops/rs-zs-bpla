"""Server profile QR (protocols/STATION_LABEL_QR_v0_1.md, section 6).

One QR printed for the installer team carries everything the app needs on the
"Server" screen for every station: host and MQTT port, HTTPS port, CA reference,
the pinned SHA-256 fingerprint of the server certificate and the topic prefix.
Nothing secret is inside (all of it is public pinning data), so it may be printed
on the field checklist.

    DIOS1;H=<host[:port]>;P=<https_port>;CA=<ca_reference>;F=<fingerprint hex64>;T=<topic_prefix>;C=<crc16>
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .ca import PkiError
from .label import crc16_ccitt

VERSION_TAG = "DIOS1"
_HOST = re.compile(r"[A-Za-z0-9.\-]{1,120}|\[[0-9A-Fa-f:.]{2,45}\]")
_CA = re.compile(r"[A-Za-z0-9._\-]{1,32}")
_FP = re.compile(r"[0-9a-f]{64}")
_PREFIX = re.compile(r"[A-Za-z0-9/_\-]{1,24}")


@dataclass(frozen=True)
class ServerProfile:
    host: str
    mqtt_port: int
    https_port: int
    ca_reference: str
    fingerprint_hex: str
    topic_prefix: str = "zs/v1"

    @staticmethod
    def from_bundle(bundle_path: Path, https_port: int = 0, topic_prefix: str = "zs/v1") -> "ServerProfile":
        b = json.loads(Path(bundle_path).read_text())
        if b.get("schema") != "dioneya-pki-bundle-v1":
            raise PkiError("unsupported bundle schema")
        return ServerProfile(b["mqtt_host"], int(b["mqtt_port"]), https_port, b["ca_reference"], b["server_fingerprint_sha256"], topic_prefix)

    def encode(self) -> str:
        host = self.host if _HOST.fullmatch(self.host) else None
        if host is None or not (1 <= self.mqtt_port <= 65535) or not (0 <= self.https_port <= 65535):
            raise PkiError("invalid host/port")
        if not _CA.fullmatch(self.ca_reference) or not _FP.fullmatch(self.fingerprint_hex) or not _PREFIX.fullmatch(self.topic_prefix):
            raise PkiError("invalid profile field")
        body = f"{VERSION_TAG};H={host}:{self.mqtt_port};P={self.https_port};CA={self.ca_reference};F={self.fingerprint_hex};T={self.topic_prefix}"
        return f"{body};C={crc16_ccitt(body.encode('ascii')):04X}"

    @staticmethod
    def decode(text: str) -> "ServerProfile":
        text = text.strip()
        if ";C=" not in text:
            raise PkiError("profile has no checksum")
        body, crc_hex = text.rsplit(";C=", 1)
        if not re.fullmatch(r"[0-9A-Fa-f]{4}", crc_hex) or int(crc_hex, 16) != crc16_ccitt(body.encode("ascii", "strict")):
            raise PkiError("profile checksum mismatch")
        parts = body.split(";")
        if parts[0] != VERSION_TAG or len(parts) != 6:
            raise PkiError("unsupported profile version")
        fields = dict(p.partition("=")[::2] for p in parts[1:])
        if set(fields) != {"H", "P", "CA", "F", "T"}:
            raise PkiError("profile fields")
        host, _, port = fields["H"].rpartition(":")
        if not host or not port.isdigit():
            raise PkiError("profile host")
        profile = ServerProfile(host, int(port), int(fields["P"]), fields["CA"], fields["F"], fields["T"])
        profile.encode()  # re-validates every field
        return profile
