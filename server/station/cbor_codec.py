"""Compact CBOR codec shared with ZS-BPLA firmware protocol."""
from __future__ import annotations

import struct
from typing import Any

from station.schemas import (
    Classification,
    DetectionMessage,
    DoaEstimate,
    GnssStatus,
    HierarchicalClassification,
    PowerStatus,
    RouteStatus,
    SingleStationEstimate,
    SpatialInfo,
    StationPosition,
)

_MSG_DETECTION = 2
_SUPPORTED_DETECTION_SCHEMAS = frozenset({1, 3, 4})
_ROUTE = {0: "LTE", 1: "NB_IOT", 2: "2G", 3: "LORA", 4: "BLE", 5: "TEST"}
_PROFILE = {0: "generic", 1: "piston", 2: "reactive"}
_CLASS_LABEL = {
    0: "UNKNOWN",
    1: "PISTON_UAV",
    2: "REACTIVE_UAV",
    3: "ELECTRIC_UAV",
    10: "ROAD_TRAFFIC",
    11: "AIRCRAFT",
    12: "HELICOPTER",
    13: "GENERATOR",
    14: "AGRICULTURAL",
    15: "BIRDS",
    16: "INSECTS",
    17: "GUNFIRE",
    18: "WIND",
}
_FAMILY_LABEL = {0: "UNKNOWN", 1: "PROP_PISTON", 2: "ROTOR_ELECTRIC", 3: "TURBINE_JET"}
_TYPE_LABEL = {0: "UNKNOWN", 1: "LUTYI", 2: "FP1", 3: "FP2", 254: "OTHER"}
_DECISION_STATUS = {0: "UNKNOWN", 1: "CANDIDATE", 2: "PROVISIONAL", 3: "STABLE", 4: "UNSUPPORTED"}
_MOTION_HINT = {0: "UNKNOWN", 1: "APPROACH", 2: "PASSING", 3: "RECEDING"}
_POSITION_TRUST = {
    0: "UNCONFIGURED",
    1: "CONFIGURED_OK",
    2: "CONFIGURED_WARN",
    3: "CONFIGURED_SUSPECT",
    4: "REVALIDATION_REQUIRED",
}
_TIME_TRUST = {
    0: "UNKNOWN",
    1: "GNSS_TIME_TRUSTED",
    2: "HOLDOVER",
    3: "GNSS_TIME_SUSPECT",
    4: "UNSYNCED",
}


class _CborReader:
    def __init__(self, raw: bytes):
        self.raw = memoryview(raw)
        self.i = 0

    def take(self, n: int) -> bytes:
        if self.i + n > len(self.raw):
            raise ValueError("truncated CBOR")
        b = self.raw[self.i : self.i + n].tobytes()
        self.i += n
        return b

    def arg(self, ai: int) -> int:
        if ai < 24:
            return ai
        if ai == 24:
            return self.take(1)[0]
        if ai == 25:
            return int.from_bytes(self.take(2), "big")
        if ai == 26:
            return int.from_bytes(self.take(4), "big")
        if ai == 27:
            return int.from_bytes(self.take(8), "big")
        raise ValueError("indefinite/reserved CBOR not supported")

    def item(self):
        ib = self.take(1)[0]
        major, ai = ib >> 5, ib & 31
        if major in (0, 1):
            v = self.arg(ai)
            return v if major == 0 else -1 - v
        if major in (2, 3):
            n = self.arg(ai)
            b = self.take(n)
            return b if major == 2 else b.decode("utf-8")
        if major == 4:
            return [self.item() for _ in range(self.arg(ai))]
        if major == 5:
            return {self.item(): self.item() for _ in range(self.arg(ai))}
        if major == 7:
            if ai == 20:
                return False
            if ai == 21:
                return True
            if ai == 22:
                return None
            if ai == 25:
                return struct.unpack(">e", self.take(2))[0]
            if ai == 26:
                return struct.unpack(">f", self.take(4))[0]
            if ai == 27:
                return struct.unpack(">d", self.take(8))[0]
        raise ValueError(f"unsupported CBOR major={major} ai={ai}")


def decode_cbor(raw: bytes):
    r = _CborReader(raw)
    obj = r.item()
    if r.i != len(r.raw):
        raise ValueError("trailing CBOR bytes")
    return obj


def _as_map(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _f16_le_bytes(raw: bytes) -> list[float]:
    if len(raw) % 2:
        raise ValueError("float16 feature payload length must be even")
    return [float(x) for x in struct.unpack("<" + "e" * (len(raw) // 2), raw)]


def decode_detection_obj(obj: Any) -> DetectionMessage:
    if not isinstance(obj, dict):
        raise ValueError("compact detection must be a CBOR map")
    schema_ver = int(obj.get(0, -1))
    if schema_ver not in _SUPPORTED_DETECTION_SCHEMAS:
        raise ValueError(f"unsupported compact detection schema: {schema_ver}")
    if int(obj.get(1, -1)) != _MSG_DETECTION:
        raise ValueError("unsupported compact message type")

    payload = _as_map(obj.get(8))
    status = _as_map(obj.get(10))
    doa = _as_map(obj.get(11))
    hierarchy = _as_map(obj.get(12))
    single = _as_map(obj.get(13))
    spatial = _as_map(obj.get(14))

    raw_features = obj.get(9, b"")
    if raw_features and not isinstance(raw_features, (bytes, bytearray)):
        raise ValueError("compact features must be bytes")
    features = _f16_le_bytes(bytes(raw_features)) if raw_features else []
    if features and len(features) != 43:
        raise ValueError(f"expected 43 compact features, got {len(features)}")

    class_id = int(payload.get(4, 0))
    confidence = int(payload.get(5, 0))
    flags = int(obj.get(7, 0))
    configured_position = bool(flags & 0x04)

    family_id = int(hierarchy.get(0, 0))
    type_id = int(hierarchy.get(2, 0))
    valid_flags = int(single.get(5, 0))
    spatial_flags = int(spatial.get(6, 0))
    position_trust_id = int(payload.get(13, 1 if configured_position else 0))
    time_trust_id = int(payload.get(14, 0))

    return DetectionMessage(
        schema_ver=schema_ver,
        station_id=int(obj.get(2, 0)),
        seq_no=int(obj.get(3, 0)),
        boot_id=int(obj.get(4, 0)),
        event_id=int(obj.get(5, 0)),
        event_time_us=int(obj.get(6, 0)),
        station=StationPosition(
            lat_e7=int(payload.get(0, 0)),
            lon_e7=int(payload.get(1, 0)),
            alt_dm=int(payload.get(2, 0)),
            pos_accuracy_m=float(payload.get(15, 20)),
            altitude_source="configured_msl" if configured_position else "gnss_msl",
            position_source="configured_install" if configured_position else "gnss_live",
        ),
        gnss=GnssStatus(
            fix_type=int(payload.get(6, 0)),
            satellites=int(payload.get(7, 0)),
            hdop_x100=int(payload.get(8, 9999)),
            pps_ok=bool(payload.get(3, False)),
            expected_time_error_us=int(payload.get(9, 1_000_000)),
            jam=bool(flags & 0x01),
            spoof=bool(flags & 0x02),
            position_delta_m=int(payload.get(12, 0)),
            position_warn=bool(flags & 0x08),
            position_suspect=bool(flags & 0x10),
            time_suspect=bool(flags & 0x20),
            time_holdover=bool(flags & 0x40),
            position_trust=_POSITION_TRUST.get(position_trust_id, "UNCONFIGURED"),
            time_trust=_TIME_TRUST.get(time_trust_id, "UNKNOWN"),
        ),
        classification=Classification(
            class_id=class_id,
            label=_CLASS_LABEL.get(class_id, f"CLASS_{class_id}"),
            confidence_u8=confidence,
            unknown=(class_id == 0),
        ),
        hierarchy=HierarchicalClassification(
            family_id=family_id,
            family_label=_FAMILY_LABEL.get(family_id, f"FAMILY_{family_id}"),
            family_confidence_u8=int(hierarchy.get(1, 0)),
            family_status=_DECISION_STATUS.get(int(hierarchy.get(4, 0)), "UNKNOWN"),
            type_id=type_id,
            type_label=_TYPE_LABEL.get(type_id, f"TYPE_{type_id}"),
            type_confidence_u8=int(hierarchy.get(3, 0)),
            type_status=_DECISION_STATUS.get(int(hierarchy.get(5, 0)), "UNKNOWN"),
        ),
        single_station_estimate=SingleStationEstimate(
            height_dm=int(single.get(0, 0)),
            height_sigma_dm=int(single.get(1, 0)),
            speed_dmps=int(single.get(2, 0)),
            speed_sigma_dmps=int(single.get(3, 0)),
            confidence_u8=int(single.get(4, 0)),
            height_valid=bool(valid_flags & 0x01),
            speed_valid=bool(valid_flags & 0x02),
            motion_hint=_MOTION_HINT.get(int(single.get(6, 0)), "UNKNOWN"),
        ),
        features=features,
        doa=DoaEstimate(
            azimuth_cdeg=int(doa.get(0, 0)),
            elevation_cdeg=int(doa.get(1, 0)),
            sigma_cdeg=int(doa.get(2, 18000)),
            valid=bool(doa.get(3, False)),
        ),
        spatial=SpatialInfo(
            tdoa12_us=int(spatial.get(0, 0)),
            tdoa13_us=int(spatial.get(1, 0)),
            tdoa14_us=int(spatial.get(2, 0)),
            residual_us=int(spatial.get(3, 0)),
            confidence_u8=int(spatial.get(4, 0)),
            geometry_id=int(spatial.get(5, 0)),
            tdoa_valid=bool(spatial_flags & 0x01),
            direction_valid=bool(spatial_flags & 0x02),
        ),
        power=PowerStatus(
            battery_pct=int(status.get(0, 0)),
            battery_mv=int(status.get(1, 0)),
            solar_mv=int(status.get(2, 0)),
            temperature_c10=int(status.get(3, 200)),
            battery_bus_mv=int(status[9]) if 9 in status else None,
            battery_current_ma=int(status[10]) if 10 in status else None,
            battery_power_mw=int(status[11]) if 11 in status else None,
            monitor_status=int(status[12]) if 12 in status else None,
        ),
        route=RouteStatus(
            transport=_ROUTE.get(int(status.get(4, 5)), "TEST"),
            hop_count=int(status.get(5, 0)),
            rssi_dbm=int(status[6]) if 6 in status else None,
            snr_db10=int(status[7]) if 7 in status else None,
            gateway_id=int(status[8]) if 8 in status else None,
        ),
        detector_profile=_PROFILE.get(int(payload.get(10, 0)), "generic"),
        sample_rate_hz=int(payload.get(11, 32000)),
    )


def decode_detection_cbor(raw: bytes) -> DetectionMessage:
    return decode_detection_obj(decode_cbor(raw))
