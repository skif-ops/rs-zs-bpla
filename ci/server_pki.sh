#!/usr/bin/env bash
# PKI test suite in a PKI-only environment (no server stack), as the executables are built.
set -euo pipefail
cd server
python -m pip install -q -r requirements-pki.txt
python -m pytest -q tests/test_pki.py tests/test_pki_labels.py
