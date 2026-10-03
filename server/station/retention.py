"""Retention of the event store (docs/SERVER_RETENTION_2026-10-03.md).

The server process runs ``EventStore.cleanup`` once at startup and then every ``interval_s`` (a day): events,
bearings, tracks, commands and ingress records older than ``ZS_RETENTION_DAYS`` (90), the outbox of dioneya.alert/1
older than ``ZS_ALERT_OUTBOX_DAYS`` (30) and the audio of events older than ``ZS_AUDIO_RETENTION_DAYS`` (30) are
removed, a day per transaction.  The last run (when, what was removed, or the error) is reported by
``/api/v1/health`` together with the storage usage, so a disk that fills up is seen without the logs.
``ZS_RETENTION_INTERVAL_S=0`` disables the periodic run (bench only).
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from dataclasses import dataclass, replace
from typing import Any, Mapping

from station.store import ALERT_OUTBOX_DAYS, AUDIO_RETENTION_DAYS, RETENTION_DAYS, EventStore

log = logging.getLogger(__name__)
DAY_S = 86_400


@dataclass(frozen=True)
class RetentionSettings:
    events_days: int = RETENTION_DAYS
    audio_days: int = AUDIO_RETENTION_DAYS
    outbox_days: int = ALERT_OUTBOX_DAYS
    interval_s: float = float(DAY_S)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RetentionSettings":
        """ZS_RETENTION_DAYS, ZS_AUDIO_RETENTION_DAYS, ZS_ALERT_OUTBOX_DAYS (whole days, at least 1) and
        ZS_RETENTION_INTERVAL_S (seconds, 0 = no periodic run); unset keeps the default."""
        env = os.environ if env is None else env
        settings = cls()
        for name, field, lowest in (("ZS_RETENTION_DAYS", "events_days", 1), ("ZS_AUDIO_RETENTION_DAYS", "audio_days", 1),
                                    ("ZS_ALERT_OUTBOX_DAYS", "outbox_days", 1), ("ZS_RETENTION_INTERVAL_S", "interval_s", 0)):
            text = env.get(name)
            if text is None or not text.strip():
                continue
            try:
                value = float(text) if field == "interval_s" else int(text)
            except ValueError:
                raise ValueError(f"{name} must be a number, not {text!r}") from None
            if value < lowest:
                raise ValueError(f"{name} must be at least {lowest}")
            settings = replace(settings, **{field: value})
        return settings

    def as_dict(self) -> dict[str, Any]:
        return {"events_days": self.events_days, "audio_days": self.audio_days, "outbox_days": self.outbox_days,
                "interval_s": self.interval_s}


class RetentionRunner:
    """Runs the cleanup and remembers its last outcome for /api/v1/health."""

    def __init__(self, settings: RetentionSettings):
        self.settings = settings
        self.last: dict[str, Any] | None = None

    def run_once(self, store: EventStore, now_us: int | None = None) -> dict[str, int]:
        started = time.time()
        try:
            removed = store.cleanup(self.settings.events_days, audio_retention_days=self.settings.audio_days,
                                    outbox_days=self.settings.outbox_days, now_us=now_us)
        except Exception as exc:  # noqa: BLE001 - the periodic run must survive and report
            self.last = {"at": started, "error": f"{type(exc).__name__}: {exc}"}
            log.exception("retention cleanup failed")
            raise
        self.last = {"at": started, "duration_s": round(time.time() - started, 3), "removed": removed}
        log.info("retention cleanup: %s in %.1f s", {k: v for k, v in removed.items() if v}, time.time() - started)
        return removed

    def status(self) -> dict[str, Any]:
        return {"settings": self.settings.as_dict(), "last_run": self.last}

    async def run_forever(self, store_of, stop: asyncio.Event | None = None) -> None:
        """Cleanup now and then every interval until ``stop`` is set (``store_of()`` gives the current store, so a
        store replaced in tests is picked up).  A failed run is reported and retried at the next interval."""
        stop = stop or asyncio.Event()
        while not stop.is_set():
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self.run_once, store_of())
            if self.settings.interval_s <= 0:
                return
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self.settings.interval_s)


RUNNER: RetentionRunner | None = None       # the server's runner, read by /api/v1/health


def lifespan(runner: RetentionRunner, store_of):
    """FastAPI lifespan that runs the periodic cleanup while the application is up (``interval_s`` > 0): the first
    run starts right after startup, a stop at shutdown ends the wait."""
    global RUNNER
    RUNNER = runner

    @contextlib.asynccontextmanager
    async def _lifespan(app):
        task = stop = None
        if runner.settings.interval_s > 0:
            stop = asyncio.Event()
            task = asyncio.create_task(runner.run_forever(store_of, stop))
        try:
            yield
        finally:
            if task is not None:
                stop.set()
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    return _lifespan
