# ci/ - job definitions for the ci-dispatch workflow

`.github/workflows/ci-dispatch.yml` is a single static workflow: it reads `ci/jobs.json`, builds a
matrix from it and runs each job's script on its runner, uploading `artifacts` when set.
Everything that changes over time (which checks run, on which runners, what gets uploaded) lives
here and needs no change to the workflow file itself.

- `jobs.json` - matrix entries: `name`, `runner`, `shell` (bash | pwsh), `script`, `artifacts` (glob or empty)
- `firmware.sh` - host tests (ctest) + STM32U585 target build with gcc-arm-none-eabi
- `twin_field.sh` - three station twins in one field through the real server path (positions, event ids, fused track,
  acceptance metrics; `server/tools/test_twin_field_e2e.py`)
- `server_pki.sh` - PKI tests in a PKI-only Python environment
- `pki_windows.ps1` - Windows executables of the PKI tools (x64 and arm64 runners)
