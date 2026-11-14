"""Operator authentication quality gates in the server CI job (`pytest tests`): QG-1 (contract/traceability,
tools/validate_operator_auth.py) and QG-2 (route-sweep runtime audit, tools/audit_operator_auth_technical.py), each
in a fresh interpreter so the test bench opt-out of conftest.py cannot leak into the audit."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_gate(script: str) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("ZS_OPERATOR_") and k != "ZS_STATION_HTTP_INSECURE_BENCH"}
    done = subprocess.run([sys.executable, str(ROOT / "tools" / script)], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def test_qg1_operator_auth_contract():
    assert "QG-1 completeness/traceability: PASS" in run_gate("validate_operator_auth.py")


def test_qg2_operator_auth_route_sweep():
    assert "QG-2 independent runtime audit: PASS" in run_gate("audit_operator_auth_technical.py")
