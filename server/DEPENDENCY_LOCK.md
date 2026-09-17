# Server dependency lock and SBOM

The server targets Python 3.12. `requirements.txt`, `requirements-ci.txt` and
`requirements-protocol.txt` remain the reviewed input constraints. The
corresponding `*.lock.txt` files are universal, fully pinned resolutions with
distribution SHA-256 hashes.

Production images and CI install only the hashed locks with
`pip install --require-hashes`. Refreshing a lock is a reviewed dependency
change, not an automatic build step:

```bash
cd server
uv pip compile requirements.txt --python-version 3.12 --universal \
  --generate-hashes -o requirements.lock.txt
uv pip compile requirements-ci.txt --python-version 3.12 --universal \
  --generate-hashes -o requirements-ci.lock.txt
uv pip compile requirements-protocol.txt --python-version 3.12 --universal \
  --generate-hashes -o requirements-protocol.lock.txt
cd ..
python tools/generate_server_sbom.py
python tools/validate_server_supply_chain.py
python tools/audit_server_sbom_technical.py
```

The checked-in `sbom/server.cdx.json` is a deterministic CycloneDX 1.6
inventory bound to the byte-exact runtime lock SHA-256. It intentionally omits
a generation timestamp so identical reviewed inputs produce identical output.
It inventories the locked Python distributions; the container base image and
operating-system packages require a separate image SBOM at release time.
