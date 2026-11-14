"""Delivery of dioneya.alert/1 over MQTT (integration/mqtt_alerts.py, protocols/DIONEYA_ALERT_API_v1.md, 4.4): every
message of the outbox to ``dioneya/alert/v1/{tenant}`` with QoS 1, in order, the cursor only after the broker's
acknowledgement; a retained heartbeat on an idle tenant; the tenant filter; a restart resumes after the cursor."""

import json

import pytest

from integration import mqtt_alerts
from integration.mqtt_alerts import MqttPublisher
from station.service import StationFusionService
from station.store import EventStore
from tests.test_alert_api import Clock, assert_valid
from tests.test_bearing_fusion import feed


class FakeInfo:
    def __init__(self, rc=0, published=True):
        self.rc, self._published = rc, published

    def wait_for_publish(self, timeout=None):
        pass

    def is_published(self):
        return self._published


class FakeClient:
    """A paho client as the publisher sees it: connected, every PUBLISH acknowledged unless told otherwise."""

    def __init__(self):
        self.connected = True
        self.published: list[tuple[str, dict, int, bool]] = []
        self.fail_next = 0                      # the next PUBLISH is refused (rc != 0)
        self.silent_next = 0                    # the next PUBLISH gets no PUBACK

    def is_connected(self):
        return self.connected

    def publish(self, topic, payload, qos, retain):
        if self.fail_next:
            self.fail_next -= 1
            return FakeInfo(rc=4)
        if self.silent_next:
            self.silent_next -= 1
            return FakeInfo(published=False)
        self.published.append((topic, json.loads(payload.decode("utf-8")), qos, retain))
        return FakeInfo()


@pytest.fixture
def scene(tmp_path):
    store = EventStore(tmp_path / "m.sqlite3")
    service = StationFusionService(store)
    service.alerts.tenant = "pilot1"
    service.alerts.clock = Clock()
    feed(store, service, (1, 2))
    return store, service


def messages_of(client, kind=None):
    return [m for _, m, _, _ in client.published if kind is None or m["type"] == kind]


def test_outbox_is_published_in_order_with_qos1_and_the_cursor_follows_the_puback(scene):
    store, service = scene
    client = FakeClient()
    publisher = MqttPublisher(store, client, start="earliest", clock=service.alerts.clock)
    outbox = store.list_alerts(0, limit=10000)
    assert publisher.step() == len(outbox)
    assert [m["seq"] for m in messages_of(client)] == [m["seq"] for m in outbox]
    assert messages_of(client) == outbox                                  # the message as it is, seq included
    assert all(topic == "dioneya/alert/v1/pilot1" and qos == 1 and not retain for topic, _, qos, retain in client.published)
    assert store.alert_cursor(mqtt_alerts.CURSOR) == outbox[-1]["seq"]
    assert publisher.step() == 0 and len(client.published) == len(outbox)   # nothing new, no heartbeat yet
    assert publisher.step() == 0 and len(client.published) == len(outbox)

    # a refused PUBLISH or one without PUBACK: nothing is skipped, the cursor stays, the same message goes again
    service.alerts.clock.offset = 200.0
    service.alerts.sweep(force=True)                                        # track.end, alert.end
    client.fail_next = 1
    assert publisher.step() == -1 and publisher.backoff() == 1.0
    assert store.alert_cursor(mqtt_alerts.CURSOR) == outbox[-1]["seq"]
    client.silent_next = 1
    assert publisher.step() == -1 and publisher.backoff() == 2.0
    assert publisher.step() == 2 and publisher.failures == 0
    assert [m["type"] for m in messages_of(client)[-2:]] == ["track.end", "alert.end"]
    assert store.alert_cursor(mqtt_alerts.CURSOR) == store.last_alert_seq()
    assert_valid(messages_of(client))


def test_heartbeat_is_retained_per_tenant_after_an_idle_period(scene):
    store, service = scene
    client = FakeClient()
    clock = service.alerts.clock
    publisher = MqttPublisher(store, client, start="earliest", heartbeat_s=30.0, clock=clock)
    publisher.step()
    sent = len(client.published)
    clock.offset = 10.0
    assert publisher.step() == 0 and len(client.published) == sent          # idle, but not for 30 s yet
    clock.offset = 31.0
    assert publisher.step() == 0
    topic, beat, qos, retain = client.published[-1]
    assert topic == "dioneya/alert/v1/pilot1" and beat["type"] == "heartbeat" and beat["tenant"] == "pilot1"
    assert beat["seq"] == store.last_alert_seq() and qos == 1 and retain
    assert_valid([beat])
    clock.offset = 40.0
    assert publisher.step() == 0 and client.published[-1][1] is beat          # one heartbeat per idle period
    clock.offset = 62.0
    publisher.step()
    assert client.published[-1][1]["type"] == "heartbeat" and client.published[-1][1] is not beat

    # a disconnected client delivers nothing and the publisher backs off
    client.connected = False
    clock.offset = 100.0
    assert publisher.step() == -1


def test_tenant_filter_start_latest_and_restart(scene):
    store, service = scene
    other = FakeClient()
    MqttPublisher(store, other, tenants=("pilot2",), start="earliest", cursor_name="mqtt:t").step()
    assert other.published == [] and store.alert_cursor("mqtt:t") == store.last_alert_seq()   # skipped, cursor passed

    latest = FakeClient()
    publisher = MqttPublisher(store, latest, start="latest", cursor_name="mqtt:l", clock=service.alerts.clock)
    assert publisher.step() == 0                                             # only what comes after it started...
    assert [m["type"] for m in messages_of(latest)] == ["heartbeat"]        # ...and the current seq at once
    assert messages_of(latest)[0]["seq"] == store.last_alert_seq()
    service.alerts.clock.offset = 200.0
    service.alerts.sweep(force=True)
    assert publisher.step() == 2 and [m["type"] for m in messages_of(latest)][1:] == ["track.end", "alert.end"]

    # a restarted publisher goes on after the cursor; the heartbeat tenants come from the outbox
    again = FakeClient()
    resumed = MqttPublisher(store, again, start="earliest", cursor_name="mqtt:l", clock=service.alerts.clock)
    assert resumed.seen == {"pilot1"}
    assert resumed.step() == 0 and [m["type"] for m in messages_of(again)] == ["heartbeat"]


def test_excluding_old_bench_outbox_does_not_hide_working_tenants(scene):
    store, service = scene
    pilot_count = len(store.list_alerts(0, limit=10000))
    store.append_alert("old-bench-message", "bench", "alert.start", 1,
                       {"type": "alert.start", "tenant": "bench"})
    client = FakeClient()
    publisher = MqttPublisher(store, client, exclude_tenants=("bench",), start="earliest",
                              cursor_name="mqtt:no-bench", clock=service.alerts.clock)
    assert publisher.seen == {"pilot1"}
    assert publisher.step() == pilot_count
    assert store.alert_cursor("mqtt:no-bench") == store.last_alert_seq()
    service.alerts.clock.offset = 1000.0
    assert publisher.step() == 0
    assert client.published and all(topic == "dioneya/alert/v1/pilot1" for topic, _, _, _ in client.published)


def test_arguments_tls_and_tenants():
    parser = mqtt_alerts.build_parser()
    args = parser.parse_args(["--ca", "a", "--cert", "b", "--key", "c"])
    with pytest.raises(ValueError, match="do not exist"):
        mqtt_alerts.tls_enabled(args)
    with pytest.raises(ValueError, match="missing: cert, key"):
        mqtt_alerts.tls_enabled(parser.parse_args(["--ca", "a"]))
    assert mqtt_alerts.tls_enabled(parser.parse_args(["--insecure-bench"])) is False
    with pytest.raises(ValueError, match="cannot be combined"):
        mqtt_alerts.tls_enabled(parser.parse_args(["--insecure-bench", "--ca", "a"]))
    assert mqtt_alerts.parse_tenants(" pilot1, pilot2 ") == ("pilot1", "pilot2") and mqtt_alerts.parse_tenants("") == ()
    with pytest.raises(ValueError):
        mqtt_alerts.parse_tenants("pilot/1")
    with pytest.raises(ValueError):
        MqttPublisher(None, None, start="now")
