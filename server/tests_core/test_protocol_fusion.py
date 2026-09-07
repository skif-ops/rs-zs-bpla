import math
import struct

import numpy as np
import pytest

from station.cbor_codec import decode_detection_cbor
from station.schemas import DetectionMessage, StationPosition, GnssStatus, Classification, DoaEstimate, PowerStatus, RouteStatus
from fusion.geodesy import EnuFrame
from fusion.kalman import ConstantVelocityKalman3D
from fusion.solver import speed_of_sound, solve_target


def _head(major, value):
    if value < 24:
        return bytes([(major << 5) | value])
    if value <= 255:
        return bytes([(major << 5) | 24, value])
    if value <= 65535:
        return bytes([(major << 5) | 25]) + value.to_bytes(2, "big")
    if value <= 0xFFFFFFFF:
        return bytes([(major << 5) | 26]) + value.to_bytes(4, "big")
    return bytes([(major << 5) | 27]) + value.to_bytes(8, "big")


def _enc(value):
    if isinstance(value, bool):
        return b"\xf5" if value else b"\xf4"
    if isinstance(value, int):
        return _head(0, value) if value >= 0 else _head(1, -1-value)
    if isinstance(value, bytes):
        return _head(2, len(value)) + value
    if isinstance(value, dict):
        return _head(5, len(value)) + b"".join(_enc(k) + _enc(v) for k, v in value.items())
    raise TypeError(type(value))


def _packet():
    feats = [i / 10.0 for i in range(43)]
    obj = {
        0: 1, 1: 2, 2: 7001, 3: 17, 4: 4, 5: 0x11223344,
        6: 1_780_000_000_000_000, 7: 0,
        8: {0: 557550000, 1: 376150000, 2: 1800, 3: True, 4: 1, 5: 230, 6: 3, 7: 18, 8: 85, 9: 80, 10: 1, 11: 32000},
        9: struct.pack("<" + "e" * 43, *feats),
        10: {0: 77, 1: 12600, 2: 18800, 3: -55, 4: 0, 5: 0, 6: -71, 7: 95, 8: 0},
        11: {0: 1234, 1: 550, 2: 900, 3: True},
        14: {0: -120, 1: 45, 2: -310, 3: 6, 4: 210, 5: 1, 6: 3},
    }
    return _enc(obj)


def test_compact_decoder_contract():
    msg = decode_detection_cbor(_packet())
    assert msg.station_id == 7001
    assert msg.station.alt_m == 180.0
    assert msg.gnss.pps_ok
    assert msg.classification.class_id == 1
    assert msg.classification.confidence_u8 == 230
    assert len(msg.features) == 43
    assert abs(msg.features[42] - 4.2) < 0.01
    assert msg.route.transport == "LTE"
    assert msg.power.temperature_c == -5.5
    assert msg.doa.valid
    assert msg.spatial.tdoa_valid
    assert msg.spatial.direction_valid
    assert msg.spatial.geometry_id == 1
    assert msg.spatial.tdoa14_us == -310
    assert msg.spatial.pair_tdoas_us["tdoa24_us"] == -190


def test_feature_count_rejected():
    with pytest.raises(ValueError):
        DetectionMessage(
            station_id=1, seq_no=1, event_id=1, event_time_us=1,
            station=StationPosition(lat_e7=0, lon_e7=0, alt_dm=0),
            features=[1.0],
        )


def test_geodesy_roundtrip():
    frame = EnuFrame(55.7558, 37.6173, 180.0)
    enu = frame.to_enu(55.7568, 37.6193, 450.0)
    lat, lon, alt = frame.to_geodetic(*enu)
    assert abs(lat - 55.7568) < 1e-6
    assert abs(lon - 37.6193) < 1e-6
    assert abs(alt - 450.0) < 0.1


def test_kalman_velocity_converges():
    k = ConstantVelocityKalman3D(process_accel_sigma=2.0)
    state = None
    for i in range(8):
        state = k.update(np.array([20.0 * i, 5.0 * i, 1000.0]), float(i), sigma_m=5.0)
    assert state is not None
    assert abs(state[3] - 20.0) < 3.0
    assert abs(state[4] - 5.0) < 3.0


def _det(station_id, lat, lon, azimuth):
    return DetectionMessage(
        station_id=station_id, seq_no=station_id, event_id=station_id,
        event_time_us=1_800_000_000_000_000,
        station=StationPosition(lat_e7=int(lat * 1e7), lon_e7=int(lon * 1e7), alt_dm=1000),
        gnss=GnssStatus(pps_ok=True, expected_time_error_us=80),
        classification=Classification(class_id=1, label="PISTON_UAV", confidence_u8=230, unknown=False),
        doa=DoaEstimate(azimuth_cdeg=int(azimuth * 100), elevation_cdeg=500, sigma_cdeg=300, valid=True),
        power=PowerStatus(temperature_c10=200), route=RouteStatus(transport="TEST"),
    )


def test_two_station_doa_produces_estimate():
    a = _det(1, 55.7500, 37.6000, 45.0)
    b = _det(2, 55.7500, 37.6200, 315.0)
    target = solve_target([a, b])
    assert target.quality in {"low", "medium", "high"}
    assert target.localization_method == "doa_intersection"
    assert target.lat is not None and target.lon is not None


def test_speed_of_sound_temperature():
    assert abs(speed_of_sound(20.0) - 343.42) < 0.01
