"""MQTT delivery of dioneya.alert/1 (protocols/DIONEYA_ALERT_API_v1.md, section 4.4).

One publisher process beside the bridges, on the same database: it reads the outbox by ``seq`` from its cursor and
publishes every message of its tenants to ``dioneya/alert/v1/{tenant}`` with QoS 1, in outbox order, one PUBLISH per
message, the message body as it is (JSON, ``seq`` included).  The cursor advances only after the broker's PUBACK, so
a restart re-publishes what the broker did not confirm: at least once, consumers drop repeats by ``msg_id``.  On a
tenant without messages for ``heartbeat_s`` a ``heartbeat`` with the last delivered seq is published, retained: a
consumer sees the current seq as soon as it subscribes and can catch up over HTTP (``/api/v1/alerts?after_seq=``)
when its session missed more than the broker queued for it.

Consumers connect to the stations' TLS listener with a client certificate of the Muhoed issuing CA (CN = consumer
name, ``python -m pki.cli consumer-cert``); the ACL rendered from the registry gives them ``read`` on the topics of
their tenants and the bridge ``write`` on them.  A persistent session (``clean_session`` false, QoS 1 subscription)
receives what was published while the consumer was offline, up to the broker's queue.

    python -m integration.mqtt_alerts --host mqtt --port 8883 --ca /run/tls/ca-chain.pem \\
        --cert /run/tls/bridge.crt.pem --key /run/tls/bridge.key.pem [--tenants pilot1,pilot2] [--start earliest]
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path

from integration import dioneya_alert

log = logging.getLogger("dioneya.mqtt")

TOPIC_PREFIX = "dioneya/alert/v1"
TENANT_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}")     # as station/mqtt_bridge.py
QOS = 1
MAX_BACKOFF_S = 60.0
BATCH = 200
PUBLISH_TIMEOUT_S = 10.0
CURSOR = "mqtt:alerts"


def topic(tenant: str) -> str:
    return f"{TOPIC_PREFIX}/{tenant}"


def encode(message: dict) -> bytes:
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class MqttPublisher:
    """Publishes the outbox to the broker through a connected paho client (or anything with ``publish`` and
    ``is_connected``)."""

    def __init__(self, store, client, *, tenants: tuple[str, ...] = (), start: str = "latest",
                 heartbeat_s: float = 60.0, cursor_name: str = CURSOR, clock=time.time,
                 publish_timeout_s: float = PUBLISH_TIMEOUT_S):
        if start not in ("latest", "earliest"):
            raise ValueError("start must be 'latest' or 'earliest'")
        self.store, self.client = store, client
        self.tenants = tuple(tenants)
        self.start, self.heartbeat_s, self.cursor_name, self.clock = start, heartbeat_s, cursor_name, clock
        self.publish_timeout_s = publish_timeout_s
        self.failures = 0
        self.last_publish_us: dict[str, int] = {}          # tenant -> wall time of its last message or heartbeat
        self.seen: set[str] = set(self.tenants) or set(store.alert_tenants())   # tenants that get heartbeats

    def cursor(self) -> int:
        seq = self.store.alert_cursor(self.cursor_name)
        if seq is None:
            seq = self.store.last_alert_seq() if self.start == "latest" else 0
            self.store.set_alert_cursor(self.cursor_name, seq)
        return seq

    def _publish(self, tenant: str, message: dict, retain: bool = False) -> bool:
        """One PUBLISH, acknowledged by the broker (QoS 1) before it counts as delivered."""
        if not self.client.is_connected():
            log.warning("mqtt: not connected, %s of %s waits", message["type"], tenant)
            return False
        try:
            info = self.client.publish(topic(tenant), encode(message), qos=QOS, retain=retain)
            if info.rc != 0:
                log.warning("mqtt: publish of %s seq %s refused: rc=%s", message["type"], message.get("seq"), info.rc)
                return False
            info.wait_for_publish(timeout=self.publish_timeout_s)
            if not info.is_published():
                log.warning("mqtt: no PUBACK for %s seq %s within %.0f s", message["type"], message.get("seq"),
                            self.publish_timeout_s)
                return False
        except (ValueError, RuntimeError, OSError) as exc:
            log.warning("mqtt: publish of %s seq %s failed: %s", message["type"], message.get("seq"), exc)
            return False
        return True

    def step(self) -> int:
        """Publish what is due: the number of messages delivered, or -1 after a failure (retry after backoff())."""
        cursor = self.cursor()
        messages, next_after = self.store.read_alerts(cursor, limit=BATCH)
        delivered = 0
        for m in messages:
            tenant = m["tenant"]
            if self.tenants and tenant not in self.tenants:
                self.store.set_alert_cursor(self.cursor_name, m["seq"])
                continue
            if not self._publish(tenant, m):
                self.failures += 1
                return -1
            self.failures = 0
            delivered += 1
            self.seen.add(tenant)
            self.last_publish_us[tenant] = int(self.clock() * 1e6)
            self.store.set_alert_cursor(self.cursor_name, m["seq"])
        if next_after > cursor and (not messages or next_after > messages[-1]["seq"]):
            self.store.set_alert_cursor(self.cursor_name, next_after)
        if not messages:
            now = int(self.clock() * 1e6)
            seq = self.cursor()
            for tenant in sorted(self.seen):
                if now - self.last_publish_us.get(tenant, 0) < self.heartbeat_s * 1e6:
                    continue
                if not self._publish(tenant, dioneya_alert.heartbeat(seq, now, tenant), retain=True):
                    self.failures += 1
                    return -1
                self.failures = 0
                self.last_publish_us[tenant] = now
        return delivered

    def backoff(self) -> float:
        return min(MAX_BACKOFF_S, 2.0 ** max(self.failures - 1, 0))

    def run_forever(self, poll_s: float = 0.5, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.is_set():
            try:
                delivered = self.step()
            except Exception:                       # a database hiccup must not end delivery
                log.exception("mqtt: step failed")
                delivered = -1
                self.failures += 1
            if delivered < 0:
                stop.wait(self.backoff())
            elif delivered < BATCH:
                stop.wait(poll_s)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m integration.mqtt_alerts",
                                     description="dioneya.alert/1 delivery to the MQTT broker")
    parser.add_argument("--host", default=os.getenv("ZS_MQTT_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("ZS_MQTT_PORT", "8883")))
    parser.add_argument("--ca", default=os.getenv("ZS_MQTT_CA"))
    parser.add_argument("--cert", default=os.getenv("ZS_MQTT_CERT"))
    parser.add_argument("--key", default=os.getenv("ZS_MQTT_KEY"))
    parser.add_argument("--tenants", default=os.getenv("ZS_ALERT_TENANTS", ""),
                        help="comma-separated tenants to publish (default: every tenant of the outbox)")
    parser.add_argument("--client-id", default="dioneya-alerts",
                        help="unique MQTT client ID (use a separate one for each publisher)")
    parser.add_argument("--start", default="latest", choices=("latest", "earliest"),
                        help="where a new publisher starts: only new messages, or the whole outbox")
    parser.add_argument("--heartbeat-s", type=float, default=60.0)
    parser.add_argument("--db", default=str(Path(__file__).resolve().parents[1] / "data" / "zs_bpla.sqlite3"))
    parser.add_argument("--insecure-bench", action="store_true",
                        default=os.getenv("ZS_MQTT_INSECURE_BENCH", "0") == "1",
                        help="plain MQTT without TLS on an isolated bench only")
    return parser


def parse_tenants(text: str) -> tuple[str, ...]:
    tenants = tuple(t.strip() for t in text.split(",") if t.strip())
    for tenant in tenants:
        if TENANT_PATTERN.fullmatch(tenant) is None:
            raise ValueError(f"tenant {tenant!r}: 1..32 safe identifier characters")
    return tenants


def tls_enabled(args: argparse.Namespace) -> bool:
    """TLS with the CA, the client certificate and its key, or (bench only) plain MQTT; as station/mqtt_bridge.py."""
    files = {"ca": args.ca, "cert": args.cert, "key": args.key}
    configured = [name for name, value in files.items() if value]
    if args.insecure_bench:
        if configured:
            raise ValueError("--insecure-bench cannot be combined with TLS arguments")
        return False
    if len(configured) != len(files):
        missing = ", ".join(name for name, value in files.items() if not value)
        raise ValueError(f"the publisher requires CA, client certificate and private key; missing: {missing}. "
                         "Use --insecure-bench only on an isolated bench.")
    absent = [name for name, value in files.items() if not Path(value).is_file()]
    if absent:
        raise ValueError(f"MQTT TLS files do not exist: {', '.join(absent)}")
    return True


def main(argv: list[str] | None = None) -> None:
    import paho.mqtt.client as mqtt

    from station.store import EventStore

    args = build_parser().parse_args(argv)
    secure = tls_enabled(args)
    tenants = parse_tenants(args.tenants)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=args.client_id, clean_session=True)
    if secure:
        client.tls_set(ca_certs=args.ca, certfile=args.cert, keyfile=args.key)
        client.tls_insecure_set(False)
    client.reconnect_delay_set(min_delay=1, max_delay=60)

    def on_connect(client_obj, userdata, flags, reason_code, properties=None):
        del client_obj, userdata, flags, properties
        log.info("mqtt: connected to %s:%s (%s)", args.host, args.port, reason_code)

    def on_disconnect(client_obj, userdata, flags, reason_code, properties=None):
        del client_obj, userdata, flags, properties
        log.warning("mqtt: disconnected (%s), reconnecting", reason_code)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.connect_async(args.host, args.port, 60)       # the loop connects and reconnects; the publisher waits
    client.loop_start()
    for _ in range(100):                                  # the first step usually finds the broker connected
        if client.is_connected():
            break
        time.sleep(0.1)
    store = EventStore(Path(args.db))
    publisher = MqttPublisher(store, client, tenants=tenants, start=args.start, heartbeat_s=args.heartbeat_s)
    log.info("publishing dioneya.alert/1 to %s/{%s}", TOPIC_PREFIX, ",".join(tenants) or "tenant")
    try:
        publisher.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    main()
