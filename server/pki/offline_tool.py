"""Offline root-CA tool: the only two operations the air-gapped machine performs.

Built as ``dioneya-root-offline.exe``; it deliberately has no server-side
commands so the root key can never be used for anything but creating the root
and signing the issuing CA request.
"""

from __future__ import annotations

import sys

from pki.cli import main as full_main

ALLOWED = ("root-init", "issuing-sign")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print("dioneya-root-offline: offline root CA tool\n\n"
              "  root-init --out DIR                         create the root CA (asks for a passphrase)\n"
              "  issuing-sign --root DIR --csr FILE --out FILE   sign the issuing CA request\n\n"
              "Run this on the air-gapped machine only. Never copy root.key.pem anywhere else.")
        return 0
    if argv[0] not in ALLOWED:
        print(f"error: '{argv[0]}' is not an offline operation (allowed: {', '.join(ALLOWED)})", file=sys.stderr)
        return 2
    return full_main(argv)


if __name__ == "__main__":
    sys.exit(main())
