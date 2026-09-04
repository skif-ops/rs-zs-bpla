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

full_raw = subprocess.check_output([str(exe)])
full = decode_detection_cbor(full_raw)
summary_raw = subprocess.check_output([str(exe), "--summary"])
summary = decode_detection_cbor(summary_raw)

for msg in (full, summary):
    assert msg.schema_ver == 3
    assert msg.station_id == 424242
    assert msg.event_id == 0x0102030405060708
    assert msg.gnss.pps_ok and msg.gnss.expected_time_error_us == 65
    assert msg.route.transport == "LORA" and msg.route.hop_count == 3
    assert msg.power.temperature_c == -12.5
    assert msg.hierarchy.family_label == "PROP_PISTON"
    assert msg.hierarchy.family_status == "PROVISIONAL"
    assert msg.hierarchy.type_label == "UNKNOWN"
    assert msg.hierarchy.type_status == "UNKNOWN"
    assert msg.hierarchy.family_confidence_u8 == 220
    single = msg.single_station_estimate
    assert single.height_valid and single.speed_valid
    assert abs(single.height_m - 125.0) < 1e-6
    assert abs(single.height_sigma_m - 45.0) < 1e-6
    assert abs(single.speed_mps - 12.5) < 1e-6
    assert abs(single.speed_sigma_mps - 4.5) < 1e-6
    assert single.motion_hint == "APPROACH"
    spatial = msg.spatial
    assert spatial.tdoa_valid and spatial.direction_valid
    assert spatial.geometry_id == 1
    assert spatial.tdoa12_us == -117
    assert spatial.tdoa13_us == 46
    assert spatial.tdoa14_us == -311
    assert spatial.residual_us == 7
    assert spatial.confidence_u8 == 209
    assert spatial.pair_tdoas_us["tdoa24_us"] == -194

# Full packet carries both precomputed DOA and raw spatial TDOA.
assert full.doa.valid and abs(full.doa.azimuth_deg - 271.23) < 1e-6
# P0 omits redundant key 11. Server reconstructs direction from key 14 + geometry_id.
assert not summary.doa.valid
assert len(full.features) == 43 and abs(full.features[42] - 5.25) < 0.01
assert summary.features == []
assert len(summary_raw) <= 220, f"P0 LoRa summary too large: {len(summary_raw)} bytes"
assert len(full_raw) > len(summary_raw)

print(
    "firmware->server protocol v1.3 compact CBOR OK, "
    f"P0 summary={len(summary_raw)} bytes, full={len(full_raw)} bytes"
)
