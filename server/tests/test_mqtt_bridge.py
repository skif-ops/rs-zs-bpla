from argparse import Namespace

import pytest

from station.mqtt_bridge import decode_status_obj, station_id_from_topic, validate_transport


def args(**overrides):
    values = {"ca": None, "cert": None, "key": None, "insecure_bench": False}
    values.update(overrides)
    return Namespace(**values)


def test_topic_binding_accepts_up_and_status():
    assert station_id_from_topic("zs/v1/pilot/17/up", "pilot") == (17, "up")
    assert station_id_from_topic("zs/v1/pilot/17/status", "pilot") == (17, "status")


@pytest.mark.parametrize(
    "topic",
    [
        "zs/v1/other/17/up",
        "zs/v1/pilot/17/down",
        "zs/v2/pilot/17/up",
        "zs/v1/pilot/not-a-number/up",
    ],
)
def test_topic_binding_rejects_wrong_scope(topic):
    with pytest.raises(ValueError):
        station_id_from_topic(topic, "pilot")


def test_transport_fails_closed_without_tls_material():
    with pytest.raises(ValueError, match="requires CA"):
        validate_transport(args())


def test_transport_rejects_partial_tls_material(tmp_path):
    ca = tmp_path / "ca.crt"
    ca.write_text("test", encoding="utf-8")
    with pytest.raises(ValueError, match="missing: cert, key"):
        validate_transport(args(ca=str(ca)))


def test_transport_rejects_missing_files(tmp_path):
    with pytest.raises(ValueError, match="do not exist"):
        validate_transport(
            args(
                ca=str(tmp_path / "ca.crt"),
                cert=str(tmp_path / "client.crt"),
                key=str(tmp_path / "client.key"),
            )
        )


def test_transport_accepts_complete_tls_material(tmp_path):
    paths = []
    for name in ("ca.crt", "client.crt", "client.key"):
        path = tmp_path / name
        path.write_text("test", encoding="utf-8")
        paths.append(str(path))
    assert validate_transport(args(ca=paths[0], cert=paths[1], key=paths[2])) is True


def test_insecure_bench_requires_explicit_clean_mode():
    assert validate_transport(args(insecure_bench=True)) is False
    with pytest.raises(ValueError, match="cannot be combined"):
        validate_transport(args(ca="ca.crt", insecure_bench=True))


def test_full_cellular_identity_requires_mutual_tls():
    heartbeat = {
        "station_id": 17,
        "time_us": 1,
        "station": {"lat_e7": 0, "lon_e7": 0, "alt_dm": 0},
        "cellular": {
            "imsi": "250011234567890",
            "iccid": "89701012345678901234",
            "apn": "network.apn",
            "local_address": "10.10.0.2",
            "gateway": "10.10.0.1",
            "primary_dns": "1.1.1.1",
            "apn_source": "NETWORK",
            "settings_valid": True,
        },
    }
    with pytest.raises(ValueError, match="requires mutual TLS"):
        decode_status_obj(heartbeat, tls_enabled=False)
    decoded = decode_status_obj(heartbeat, tls_enabled=True)
    assert decoded.cellular is not None
    assert decoded.cellular.imsi == "250011234567890"
