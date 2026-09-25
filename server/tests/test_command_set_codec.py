"""ICD addendum D (CMD_REBOOT, CMD_SET_PARAMS): round trip, parameter whitelist and ranges, shared firmware vector."""
import importlib.util
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from station.command_codec import STATION_PARAMS, CommandSigner, decode_signed_command, encode_signed_command
from station.schemas import StationCommand

ROOT = Path(__file__).resolve().parents[2]


def _gen():
    spec = importlib.util.spec_from_file_location("gen_command_set", ROOT / "tools" / "generate_command_set_vector.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cmd(name, payload):
    return StationCommand(command_id="2b0f1c3a-0000-4000-8000-00000000000a", station_id=17, command=name, payload=payload,
                          created_time_us=1_000_000, expires_time_us=2_000_000)


def test_firmware_vector_is_current():
    gen = _gen()
    assert (ROOT / "firmware" / "generated" / "zs_command_set_vector.h").read_text() == gen.render()


def test_round_trip_both_commands():
    signer = CommandSigner(Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33))))
    keys = {signer.key_id: signer.public_key}
    reboot = decode_signed_command(encode_signed_command(_cmd("CMD_REBOOT", {"delay_s": 45}), signer), keys, now_us=1_500_000)
    assert reboot.command == "CMD_REBOOT" and reboot.payload == {"delay_s": 45}
    payload = {"reset": True, "params": {"gsm_probe_s": 600, "mic_channel": 3}}
    params = decode_signed_command(encode_signed_command(_cmd("CMD_SET_PARAMS", payload), signer), keys, now_us=1_500_000)
    assert params.command == "CMD_SET_PARAMS" and params.payload == payload
    reset_only = decode_signed_command(encode_signed_command(_cmd("CMD_SET_PARAMS", {"reset": True}), signer), keys, now_us=1_500_000)
    assert reset_only.payload == {"reset": True, "params": {}}


@pytest.mark.parametrize("name,payload,match", [
    ("CMD_REBOOT", {"delay_s": 601}, "delay_s"),
    ("CMD_REBOOT", {"delay_s": -1}, "delay_s"),
    ("CMD_REBOOT", {"when": 1}, "unsupported reboot"),
    ("CMD_SET_PARAMS", {"params": {}}, "1..8"),
    ("CMD_SET_PARAMS", {"params": {"volume": 3}}, "unknown station parameter"),
    ("CMD_SET_PARAMS", {"params": {"mic_channel": 4}}, "outside"),
    ("CMD_SET_PARAMS", {"params": {"heartbeat_period_s": 60}}, "outside"),
    ("CMD_SET_PARAMS", {"reset": 1, "params": {"mic_channel": 1}}, "reset: bool"),
    ("CMD_SET_PARAMS", {"params": {"mic_channel": True}}, "outside"),
])
def test_rejections(name, payload, match):
    signer = CommandSigner(Ed25519PrivateKey.generate())
    with pytest.raises(ValueError, match=match):
        encode_signed_command(_cmd(name, payload), signer)


def test_whitelist_ids_are_unique_and_defaults_in_range():
    ids = [spec[0] for spec in STATION_PARAMS.values()]
    assert len(ids) == len(set(ids)) and all(0 < i < 65536 for i in ids)
    for lo_hi_default in STATION_PARAMS.values():
        _, lo, hi, default = lo_hi_default
        assert lo <= default <= hi
