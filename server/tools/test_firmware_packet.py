#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import sys
from pathlib import Path
SERVER_ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(SERVER_ROOT))
from station.cbor_codec import decode_detection_cbor
RELEASE_ROOT=Path(__file__).resolve().parents[3]
exe=RELEASE_ROOT/'05_ПО_станции'/'firmware_evt_mb_v1_2'/'build-host-v1.2'/'zs_emit_detection'
raw=subprocess.check_output([str(exe)])
m=decode_detection_cbor(raw)
assert m.station_id==424242
assert m.event_id==0x0102030405060708
assert m.gnss.pps_ok and m.gnss.expected_time_error_us==65
assert m.route.transport=='LORA' and m.route.hop_count==3
assert m.power.temperature_c==-12.5
assert m.doa.valid and abs(m.doa.azimuth_deg-271.23)<1e-6
assert len(m.features)==43 and abs(m.features[42]-5.25)<0.01
print(f'firmware->server compact CBOR OK, {len(raw)} bytes')
