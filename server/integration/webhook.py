"""Webhook delivery of dioneya.alert/1 over HTTPS with mutual TLS (protocols/DIONEYA_ALERT_API_v1.md, section 4).

Every consumer gets every message of its tenants in outbox order, one HTTP POST per message, at least once: the
cursor (the last seq the consumer answered 2xx) is stored in the database, so a restart resumes where delivery
stopped; a failed POST is retried with growing pauses (1 s .. 60 s) and later messages wait (order is kept).  The
consumer drops repeats by ``msg_id`` (also sent as ``Idempotency-Key``).  On an idle channel a ``heartbeat`` is posted
every ``heartbeat_s``.  The server presents its client certificate and trusts only the consumer's CA.

    python -m integration.webhook --config data/webhooks.json [--db data/zs_bpla.sqlite3]

``webhooks.json``::

    {"consumers": [{"name": "platform", "url": "https://platform.example/dioneya/alerts", "tenants": ["pilot1"],
                    "ca": "/run/tls/platform-ca.pem", "cert": "/run/tls/alert-client.crt.pem",
                    "key": "/run/tls/alert-client.key.pem", "start": "latest"}]}
"""
from __future__ import annotations

import argparse
import json
import logging
import ssl
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from integration import dioneya_alert

log = logging.getLogger("dioneya.webhook")

MAX_BACKOFF_S = 60.0
BATCH = 200


@dataclass(frozen=True)
class Consumer:
    name: str
    url: str
    ca: str
    cert: str
    key: str
    tenants: tuple[str, ...] = ()          # empty: every tenant
    start: str = "latest"                   # where a new consumer starts: "latest" (only new) or "earliest"
    timeout_s: float = 5.0
    heartbeat_s: float = 60.0

    def __post_init__(self):
        if not self.name or not all(ch.isalnum() or ch in "-_." for ch in self.name):
            raise ValueError(f"consumer name {self.name!r}: letters, digits, '-', '_', '.' only")
        if not self.url.startswith("https://"):
            raise ValueError(f"consumer {self.name}: webhooks are delivered over HTTPS with mutual TLS only")
        if self.start not in ("latest", "earliest"):
            raise ValueError(f"consumer {self.name}: start must be 'latest' or 'earliest'")
        for label, path in (("ca", self.ca), ("cert", self.cert), ("key", self.key)):
            if not path:
                raise ValueError(f"consumer {self.name}: {label} is required (mutual TLS)")

    @property
    def cursor_name(self) -> str:
        return f"webhook:{self.name}"


def load_config(path: str | Path) -> list[Consumer]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    consumers = []
    for item in raw.get("consumers", []):
        item = dict(item)
        item["tenants"] = tuple(item.get("tenants") or ())
        consumers.append(Consumer(**item))
    names = [c.name for c in consumers]
    if len(set(names)) != len(names):
        raise ValueError("consumer names must be unique")
    return consumers


def tls_context(consumer: Consumer) -> ssl.SSLContext:
    """Trust the consumer's CA only, present the server's client certificate, TLS 1.2+."""
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=consumer.ca)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(consumer.cert, consumer.key)
    return context


@dataclass
class WebhookDispatcher:
    store: object
    consumer: Consumer
    client: httpx.Client | None = None
    clock: object = time.time
    failures: int = 0
    last_post_us: int = field(default=0)

    def __post_init__(self):
        if self.client is None:
            self.client = httpx.Client(verify=tls_context(self.consumer), timeout=self.consumer.timeout_s)

    def cursor(self) -> int:
        seq = self.store.alert_cursor(self.consumer.cursor_name)
        if seq is None:
            seq = self.store.last_alert_seq() if self.consumer.start == "latest" else 0
            self.store.set_alert_cursor(self.consumer.cursor_name, seq)
        return seq

    def _post(self, message: dict) -> bool:
        headers = {"X-Dioneya-Schema": dioneya_alert.SCHEMA, "X-Dioneya-Seq": str(message["seq"]),
                   "Idempotency-Key": message["msg_id"]}
        try:
            response = self.client.post(self.consumer.url, json=message, headers=headers)
        except httpx.HTTPError as exc:
            log.warning("webhook %s: seq %s not delivered: %s", self.consumer.name, message["seq"], exc)
            return False
        if 200 <= response.status_code < 300:
            return True
        log.warning("webhook %s: seq %s answered %s", self.consumer.name, message["seq"], response.status_code)
        return False

    def step(self) -> int:
        """Deliver what is due: the number of messages delivered, or -1 after a failure (retry after backoff())."""
        cursor = self.cursor()
        messages, next_after = self.store.read_alerts(cursor, limit=BATCH)
        delivered = 0
        for m in messages:
            if self.consumer.tenants and m["tenant"] not in self.consumer.tenants:
                self.store.set_alert_cursor(self.consumer.cursor_name, m["seq"])
                continue
            if not self._post(m):
                self.failures += 1
                return -1
            self.failures = 0
            delivered += 1
            self.last_post_us = int(self.clock() * 1e6)
            self.store.set_alert_cursor(self.consumer.cursor_name, m["seq"])
        if next_after > cursor and (not messages or next_after > messages[-1]["seq"]):
            self.store.set_alert_cursor(self.consumer.cursor_name, next_after)
        now = int(self.clock() * 1e6)
        if not messages and now - self.last_post_us >= self.consumer.heartbeat_s * 1e6:
            if not self._post(dioneya_alert.heartbeat(self.cursor(), now)):
                self.failures += 1
                return -1
            self.failures = 0
            self.last_post_us = now
        return delivered

    def backoff(self) -> float:
        return min(MAX_BACKOFF_S, 2.0 ** max(self.failures - 1, 0))

    def run_forever(self, poll_s: float = 0.5, stop: threading.Event | None = None) -> None:
        stop = stop or threading.Event()
        while not stop.is_set():
            try:
                delivered = self.step()
            except Exception:                       # a database hiccup must not end delivery
                log.exception("webhook %s: step failed", self.consumer.name)
                delivered = -1
                self.failures += 1
            if delivered < 0:
                stop.wait(self.backoff())
            elif delivered < BATCH:
                stop.wait(poll_s)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m integration.webhook", description="dioneya.alert/1 webhook delivery")
    parser.add_argument("--config", required=True, help="JSON file with the consumers")
    parser.add_argument("--db", default=str(Path(__file__).resolve().parents[1] / "data" / "zs_bpla.sqlite3"))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from station.store import EventStore

    store = EventStore(Path(args.db))
    consumers = load_config(args.config)
    if not consumers:
        raise SystemExit("no consumers configured")
    stop = threading.Event()
    threads = [threading.Thread(target=WebhookDispatcher(store, c).run_forever, kwargs={"stop": stop}, name=c.name, daemon=True)
               for c in consumers]
    for t in threads:
        t.start()
    log.info("delivering dioneya.alert/1 to %s", ", ".join(c.name for c in consumers))
    try:
        while any(t.is_alive() for t in threads):
            time.sleep(1.0)
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
