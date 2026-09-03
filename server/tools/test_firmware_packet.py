#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVER_ROOT.parent
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from station.cbor_codec import decode_detection_cbor

exe = REPO_ROOT / "firmware" / "build" / "zs_emit_detection"
raw = subprocess.check_output([str(exe)])
msg = decode_detection_cbor(raw)
assert msg.station_id == 424242
assert msg.event_id == 0x0102030405060708
assert msg.gnss.pps_ok and msg.gnss.expected_time_error_us == 65
assert msg.route.transport == "LORA" and msg.route.hop_count == 3
assert msg.power.temperature_c == -12.5
assert msg.doa.valid and abs(msg.doa.azimuth_deg - 271.23) < 1e-6
assert len(msg.features) == 43 and abs(msg.features[42] - 5.25) < 0.01
print(f"firmware->server compact CBOR OK, {len(raw)} bytes")
