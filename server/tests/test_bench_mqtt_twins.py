"""The network sender can only use distinct bench identities."""
from pathlib import Path
import sys

import pytest

from pki import ca as pki

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import bench_mqtt_twins  # noqa: E402


def test_plan_requires_per_station_certificate_and_exact_cn(tmp_path: Path):
    issuing = pki.create_root(b"test-root-passphrase")
    # A certificate with any other CN must never be usable as a virtual station.
    station_dir = tmp_path / "DIO-TWIN-001"
    station_dir.mkdir()
    # The root is deliberately not used to sign: malformed certificate bytes fail closed.
    (station_dir / "DIO-TWIN-001.crt.pem").write_bytes(issuing.cert_pem)
    (station_dir / "DIO-TWIN-001.key.pem").write_bytes(b"key")
    with pytest.raises(ValueError, match="CN does not match"):
        bench_mqtt_twins.identities(3, tmp_path)
    with pytest.raises(ValueError, match="3, 20 or 40"):
        bench_mqtt_twins.identities(4, tmp_path)


def test_sender_publishes_only_its_bench_status_topic(monkeypatch, tmp_path: Path):
    published = []

    class Receipt:
        rc = bench_mqtt_twins.mqtt.MQTT_ERR_SUCCESS

        def wait_for_publish(self, timeout=None):
            pass

        def is_published(self):
            return True

    class Client:
        def __init__(self, *args, **kwargs):
            self.on_connect = None

        def tls_set(self, **kwargs):
            pass

        def tls_insecure_set(self, value):
            assert value is False

        def connect(self, *args, **kwargs):
            self.on_connect(self, None, None, 0, None)

        def loop_start(self):
            pass

        def publish(self, topic, payload, qos, retain):
            published.append((topic, payload, qos, retain))
            return Receipt()

        def disconnect(self):
            pass

        def loop_stop(self):
            pass

    monkeypatch.setattr(bench_mqtt_twins.mqtt, "Client", Client)
    bench_mqtt_twins.send_one("localhost", 8884, tmp_path / "ca", tmp_path / "cert", tmp_path / "key",
                             9001, b"heartbeat", 1)
    assert published == [("zs/v1/bench/9001/status", b"heartbeat", 1, False)]
