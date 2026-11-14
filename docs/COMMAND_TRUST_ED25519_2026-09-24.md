# Command trust on the station: Ed25519 verification — 2026-09-24

`zs_ed25519` (portable C99, TweetNaCl-style arithmetic, own SHA-512) verifies the server's command signatures
on the STM32: `zs_ed25519_verify(pk, msg, len, sig)` with canonical-S and on-curve checks. Host test
`test_ed25519.c` runs `cryptography` vectors (empty, short, 200-byte and 300-byte messages), bit flips in
message / signature / key, a non-canonical `S + L`, an off-curve key, a zero signature, and SHA-512 against
`hashlib` (including the 111/112-byte padding edge).

Wiring: the comms task builds `zs_command_trust` with the Ed25519 public key of the server's command signer
from the station secrets record (ICD BLE v0.3 key 4 → `app_comms_set_command_key`); key id = SHA-256(pk)[0..7]
as in `station/command_codec.py`. Without a provisioned key the trust set holds a placeholder (0xff…, backend
rejects everything) so the down channel subscribes and every command is refused as unverified.

This also fixes a latent B2 bug: `zs_command_trust_init` refuses an all-zero key set, so `start_session`
could never succeed and the comms task would have sat in FAULT on the bench.

Not yet: command execution — verified commands are acknowledged `REJECTED / detail 1` ("not implemented")
until the command executor lands (config push, service window, reboot). Console `comms` shows
`commands key set|none verified N rejected N`.

Cost: FLASH +5.6 KB (162 KB total), comms task stack 1536 → 2048 words, FreeRTOS heap 40 → 44 KB (RAM 84.3 %).
A verify takes tens of ms on the M33 (no precomputed tables); commands are rare.
