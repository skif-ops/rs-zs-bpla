# server/pki - Muhoed internal PKI

Root CA offline, issuing CA on the server, station certificates by CSR (CN = serial),
registry for the 41-unit pilot (2 lots x 20 + bench), generated mosquitto ACL,
enclosure label QR with the per-unit pairing secret.

```
pip install -r requirements-pki.txt
python -m pki.cli --help
```

Offline machine (root only):
```
python -m pki.offline_tool root-init --out /media/offline/dioneya-root
python -m pki.offline_tool issuing-sign --root /media/offline/dioneya-root/root --csr issuing.csr.pem --out issuing.crt.pem
```

Server:
```
python -m pki.cli issuing-request
python -m pki.cli issuing-install --cert issuing.crt.pem --root-cert root.crt.pem
python -m pki.cli server-cert --dns muhoed.example.ru --ip 203.0.113.10
python -m pki.cli bridge-cert
python -m pki.cli station-add --all-lots
python -m pki.cli station-sign DIO-EVT-012 --csr DIO-EVT-012.csr.pem
python -m pki.cli bundle --mqtt-host muhoed.example.ru
python -m pki.cli station-package DIO-EVT-012 --out /media/eol
python -m pki.cli mosquitto-acl --out deploy/mosquitto/station_acl.conf
```

Labels (protocols/STATION_LABEL_QR_v0_1.md):
```
python -m pki.cli label-qr DIO-EVT-012 --out labels --png      # SVG + payload text (+ PNG with Pillow)
python -m pki.cli label-sheet --out labels/sheet.svg --lot EVT-LOT-2
python -m pki.cli pairing-secret-rotate DIO-EVT-012 --reason "label lost"   # then reprint + reload the package
```

Windows executables: `pki\build_windows.ps1` or the `ci-dispatch` GitHub Actions workflow
(`muhoed-pki.exe`, `dioneya-root-offline.exe`, x64 and arm64, with SHA256SUMS.txt).

Full procedure, roles, backups and rotation: document "Инструкция PKI ключи и сертификаты Мухоед Дионея v0.1".
