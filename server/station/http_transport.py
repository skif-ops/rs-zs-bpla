"""Fail-closed policy for the legacy station HTTP transport.

Production stations use the MQTT mutual-TLS bridge.  The HTTP routes remain
available only for an explicitly enabled, isolated integration bench.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, status


INSECURE_BENCH_ENV = "ZS_STATION_HTTP_INSECURE_BENCH"


def insecure_station_http_bench_enabled() -> bool:
    """Return true only for the single documented opt-in value."""

    return os.getenv(INSECURE_BENCH_ENV) == "1"


async def require_insecure_station_http_bench() -> None:
    """Reject station HTTP traffic unless an isolated bench opts in."""

    if not insecure_station_http_bench_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "station HTTP transport is disabled; use mutual-TLS MQTT in production "
                f"or set {INSECURE_BENCH_ENV}=1 only on an isolated bench"
            ),
        )
