#!/usr/bin/env bash
# EVT build release audit (hardware/EVT_BUILD_RELEASE_GATE_REV_A.md).
# Reports blockers without failing; the gate is enforced with --strict at handoff.
set -euo pipefail
python -m pip install --disable-pip-version-check kiutils==1.4.8
python tools/audit_evt_pre_20_evt_build_release.py
