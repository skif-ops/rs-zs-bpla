# Builds muhoed-pki.exe and dioneya-root-offline.exe (x64 or arm64 depending on the runner).
$ErrorActionPreference = "Stop"
Set-Location server
python -m pip install -r requirements-pki.txt pyinstaller pytest
python -m pytest -q tests/test_pki.py
pyinstaller --clean --noconfirm pki/pyinstaller_muhoed_pki.spec
pyinstaller --clean --noconfirm pki/pyinstaller_root_offline.spec
.\dist\muhoed-pki.exe --help
.\dist\dioneya-root-offline.exe --help
Get-FileHash dist\muhoed-pki.exe, dist\dioneya-root-offline.exe -Algorithm SHA256 |
    ForEach-Object { "$($_.Hash.ToLower())  $(Split-Path $_.Path -Leaf)" } | Set-Content dist\SHA256SUMS.txt
Get-Content dist\SHA256SUMS.txt
