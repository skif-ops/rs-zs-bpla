"""Station label QR (protocols/STATION_LABEL_QR_v0_1.md).

Payload printed on the enclosure label and scanned by the commissioning app:

    DIO1;S=<serial>;ID=<station_id>;T=<tenant>;K=<pairing secret, base32 no padding>;C=<crc16 hex>

The pairing secret (16 random bytes) is generated per unit in the registry, printed
only on the label and loaded into the station at EOL (station package); it never
enters the APK or Git.  CRC-16/CCITT-FALSE over everything before ";C=" guards
against manual retyping errors (QR itself carries Reed-Solomon ECC).
"""
from __future__ import annotations

import base64
import re
import secrets
from dataclasses import dataclass

from .ca import PkiError, lot_for_serial, station_id_for_serial

VERSION_TAG = "DIO1"
SECRET_BYTES = 16
_B32 = re.compile(r"[A-Z2-7]{26}")
_TENANT = re.compile(r"[A-Za-z0-9._-]{1,16}")


def crc16_ccitt(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def new_pairing_secret() -> str:
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode("ascii").rstrip("=")


def secret_bytes(secret_b32: str) -> bytes:
    return base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))


@dataclass(frozen=True)
class StationLabel:
    serial: str
    station_id: int
    tenant: str
    pairing_secret_b32: str

    def encode(self) -> str:
        if not _B32.fullmatch(self.pairing_secret_b32):
            raise PkiError("pairing secret must be 26 base32 characters")
        if not _TENANT.fullmatch(self.tenant):
            raise PkiError("invalid tenant")
        if station_id_for_serial(self.serial) != self.station_id:
            raise PkiError("station_id does not match the serial")
        body = f"{VERSION_TAG};S={self.serial};ID={self.station_id};T={self.tenant};K={self.pairing_secret_b32}"
        return f"{body};C={crc16_ccitt(body.encode('ascii')):04X}"

    @staticmethod
    def decode(text: str) -> "StationLabel":
        text = text.strip()
        if ";C=" not in text:
            raise PkiError("label has no checksum")
        body, crc_hex = text.rsplit(";C=", 1)
        if not re.fullmatch(r"[0-9A-Fa-f]{4}", crc_hex) or int(crc_hex, 16) != crc16_ccitt(body.encode("ascii", "strict")):
            raise PkiError("label checksum mismatch")
        parts = body.split(";")
        if parts[0] != VERSION_TAG or len(parts) != 5:
            raise PkiError("unsupported label version")
        fields = {}
        for p in parts[1:]:
            k, _, v = p.partition("=")
            fields[k] = v
        if set(fields) != {"S", "ID", "T", "K"}:
            raise PkiError("label fields")
        serial = fields["S"]
        lot_for_serial(serial)  # validates the pilot serial
        station_id = int(fields["ID"])
        if station_id_for_serial(serial) != station_id:
            raise PkiError("station_id does not match the serial")
        if not _TENANT.fullmatch(fields["T"]) or not _B32.fullmatch(fields["K"]):
            raise PkiError("label fields")
        return StationLabel(serial, station_id, fields["T"], fields["K"])


def render_svg(label: StationLabel, box_mm: float = 30.0) -> str:
    """Label as a self-contained SVG: QR (EC level M) plus the human-readable serial and station_id."""
    import qrcode
    import qrcode.image.svg

    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=2)
    qr.add_data(label.encode())
    qr.make(fit=True)
    modules = qr.get_matrix()
    n = len(modules)
    px = box_mm / n
    cells = "".join(
        f'<rect x="{x * px:.3f}" y="{y * px:.3f}" width="{px:.3f}" height="{px:.3f}"/>'
        for y, row in enumerate(modules) for x, dark in enumerate(row) if dark
    )
    text_h = 6.0
    width, height = box_mm + 4.0, box_mm + text_h + 4.0
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}">'
        f'<rect width="{width}" height="{height}" fill="white"/>'
        f'<g transform="translate(2,2)" fill="black">{cells}</g>'
        f'<text x="{width / 2:.2f}" y="{box_mm + 6.5:.2f}" font-family="monospace" font-size="3.2" text-anchor="middle">'
        f'{label.serial}  id {label.station_id}  {label.tenant}</text></svg>'
    )


def render_sheet_svg(labels: list[StationLabel], columns: int = 4, box_mm: float = 30.0) -> str:
    """A4 sheet (210x297 mm) of labels for printing; each cell is a full label."""
    cell_w, cell_h = box_mm + 10.0, box_mm + 16.0
    parts = []
    for i, lab in enumerate(labels):
        col, row = i % columns, i // columns
        inner = render_svg(lab, box_mm)
        inner = inner[inner.index(">") + 1:inner.rindex("</svg>")]
        parts.append(f'<g transform="translate({10 + col * cell_w:.2f},{10 + row * cell_h:.2f})">{inner}</g>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="297mm" viewBox="0 0 210 297">'
            '<rect width="210" height="297" fill="white"/>' + "".join(parts) + "</svg>")
