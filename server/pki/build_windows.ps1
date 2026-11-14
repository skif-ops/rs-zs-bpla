# Builds muhoed-pki.exe and dioneya-root-offline.exe on Windows (x64 or ARM64).
# Usage (PowerShell, from the repository root):
#   cd server
#   .\pki\build_windows.ps1
# Requirements: Python 3.11+ (matching the machine architecture), internet for pip.
$ErrorActionPreference = "Stop"
python -m venv .venv-pki
.\.venv-pki\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-pki.txt pyinstaller pytest
python -m pytest -q tests/test_pki.py
pyinstaller --clean --noconfirm pki/pyinstaller_muhoed_pki.spec
pyinstaller --clean --noconfirm pki/pyinstaller_root_offline.spec
Get-FileHash dist\muhoed-pki.exe, dist\dioneya-root-offline.exe -Algorithm SHA256 |
    ForEach-Object { "$($_.Hash.ToLower())  $(Split-Path $_.Path -Leaf)" } | Set-Content dist\SHA256SUMS.txt
Get-Content dist\SHA256SUMS.txt
