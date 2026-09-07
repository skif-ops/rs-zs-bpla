"""Compact CBOR codec shared with ZS-BPLA firmware protocol.

Only a small deterministic CBOR subset is needed on the station wire: integers,
byte/text strings, arrays, maps, booleans and IEEE floats.  The built-in decoder
keeps the server independent of the optional ``cbor2`` package; if cbor2 is
installed it can still be used elsewhere.
"""
from __future__ import annotations

import struct
from typing import Any

from station.schemas import (
    Classification, DetectionMessage, DoaEstimate, GnssStatus, PowerStatus,
    RouteStatus, SpatialEstimate, StationPosition, TimeStatus,
)

_MSG_DETECTION = 2
_ROUTE = {0: "LTE", 1: "NB_IOT", 2: "2G", 3: "LORA", 4: "BLE", 5: "TEST"}
_PROFILE = {0: "generic", 1: "piston", 2: "reactive"}
_TIME_SOURCE = {0: "NONE", 1: "GNSS_PPS", 2: "HOLDOVER", 3: "NTP", 4: "NITZ"}
_TIME_QUALITY = {0: "INVALID", 1: "LOW", 2: "MID", 3: "HIGH"}
_CLASS_LABEL = {
    0: "UNKNOWN", 1: "PISTON_UAV", 2: "REACTIVE_UAV", 3: "ELECTRIC_UAV",
    10: "ROAD_TRAFFIC", 11: "AIRCRAFT", 12: "HELICOPTER", 13: "GENERATOR",
    14: "AGRICULTURAL", 15: "BIRDS", 16: "INSECTS", 17: "GUNFIRE", 18: "WIND",
}

class _CborReader:
    def __init__(self, raw: bytes): self.raw=memoryview(raw); self.i=0
    def take(self,n:int)->bytes:
        if self.i+n>len(self.raw): raise ValueError("truncated CBOR")
        b=self.raw[self.i:self.i+n].tobytes(); self.i+=n; return b
    def arg(self,ai:int)->int:
        if ai<24:return ai
        if ai==24:return self.take(1)[0]
        if ai==25:return int.from_bytes(self.take(2),'big')
        if ai==26:return int.from_bytes(self.take(4),'big')
        if ai==27:return int.from_bytes(self.take(8),'big')
        raise ValueError("indefinite/reserved CBOR not supported")
    def item(self):
        ib=self.take(1)[0]; major=ib>>5; ai=ib&31
        if major in (0,1):
            v=self.arg(ai); return v if major==0 else -1-v
        if major in (2,3):
            n=self.arg(ai); b=self.take(n); return b if major==2 else b.decode('utf-8')
        if major==4:
            return [self.item() for _ in range(self.arg(ai))]
        if major==5:
            return {self.item():self.item() for _ in range(self.arg(ai))}
        if major==7:
            if ai==20:return False
            if ai==21:return True
            if ai==22:return None
            if ai==25:return struct.unpack('>e',self.take(2))[0]
            if ai==26:return struct.unpack('>f',self.take(4))[0]
            if ai==27:return struct.unpack('>d',self.take(8))[0]
        raise ValueError(f"unsupported CBOR major={major} ai={ai}")

def decode_cbor(raw:bytes):
    r=_CborReader(raw); obj=r.item()
    if r.i!=len(r.raw): raise ValueError("trailing CBOR bytes")
    return obj

def _as_map(value: Any) -> dict: return value if isinstance(value, dict) else {}
def _f16_le_bytes(raw: bytes) -> list[float]:
    if len(raw)%2: raise ValueError("float16 feature payload length must be even")
    return [float(x) for x in struct.unpack('<'+'e'*(len(raw)//2),raw)]

def decode_detection_obj(obj: Any) -> DetectionMessage:
    if not isinstance(obj,dict): raise ValueError("compact detection must be a CBOR map")
    if int(obj.get(1,-1))!=_MSG_DETECTION: raise ValueError("unsupported compact message type")
    payload=_as_map(obj.get(8)); status=_as_map(obj.get(10)); doa=_as_map(obj.get(11))
    timing=_as_map(obj.get(12)); spatial=_as_map(obj.get(14))
    raw_features=obj.get(9,b'')
    if raw_features and not isinstance(raw_features,(bytes,bytearray)): raise ValueError("compact features must be bytes")
    features=_f16_le_bytes(bytes(raw_features)) if raw_features else []
    if features and len(features)!=43: raise ValueError(f"expected 43 compact features, got {len(features)}")
    class_id=int(payload.get(4,0)); confidence=int(payload.get(5,0)); flags=int(obj.get(7,0))
    return DetectionMessage(
        schema_ver=int(obj.get(0,1)), station_id=int(obj.get(2,0)), seq_no=int(obj.get(3,0)), boot_id=int(obj.get(4,0)), event_id=int(obj.get(5,0)), event_time_us=int(obj.get(6,0)),
        station=StationPosition(lat_e7=int(payload.get(0,0)),lon_e7=int(payload.get(1,0)),alt_dm=int(payload.get(2,0)),pos_accuracy_m=20.0,altitude_source='gnss_msl'),
        gnss=GnssStatus(fix_type=int(payload.get(6,0)),satellites=int(payload.get(7,0)),hdop_x100=int(payload.get(8,9999)),pps_ok=bool(payload.get(3,False)),expected_time_error_us=int(payload.get(9,1_000_000)),jam=bool(flags&1),spoof=bool(flags&2)),
        classification=Classification(class_id=class_id,label=_CLASS_LABEL.get(class_id,f'CLASS_{class_id}'),confidence_u8=confidence,unknown=(class_id==0)),
        features=features,
        doa=DoaEstimate(azimuth_cdeg=int(doa.get(0,0)),elevation_cdeg=int(doa.get(1,0)),sigma_cdeg=int(doa.get(2,18000)),valid=bool(doa.get(3,False))),
        spatial=SpatialEstimate(azimuth_cdeg=int(spatial.get(0,0)),elevation_cdeg=int(spatial.get(1,0)),sigma_azimuth_cdeg=int(spatial.get(2,18000)),sigma_elevation_cdeg=int(spatial.get(3,18000)),mic_health_mask=int(spatial.get(4,0)),valid=bool(spatial.get(5,False))),
        time_status=TimeStatus(source=_TIME_SOURCE.get(int(timing.get(0,0)),"NONE"),quality=_TIME_QUALITY.get(int(timing.get(1,0)),"INVALID"),uncertainty_us=int(timing.get(2,payload.get(9,1_000_000)))),
        power=PowerStatus(battery_pct=int(status.get(0,0)),battery_mv=int(status.get(1,0)),solar_mv=int(status.get(2,0)),temperature_c10=int(status.get(3,200))),
        route=RouteStatus(transport=_ROUTE.get(int(status.get(4,5)),'TEST'),hop_count=int(status.get(5,0)),rssi_dbm=int(status[6]) if 6 in status else None,snr_db10=int(status[7]) if 7 in status else None,gateway_id=int(status[8]) if 8 in status else None),
        detector_profile=_PROFILE.get(int(payload.get(10,0)),'generic'), sample_rate_hz=int(payload.get(11,32000)),
    )

def decode_detection_cbor(raw:bytes)->DetectionMessage: return decode_detection_obj(decode_cbor(raw))
