"""Audio upload (ICD addendum B): shared vector with the firmware, IMA-ADPCM mirror, assembly, rejections."""
import hashlib
import importlib.util
import math
from pathlib import Path

import pytest

from station import audio_chunk_codec as ac

ROOT = Path(__file__).resolve().parents[2]


def _generator():
    spec = importlib.util.spec_from_file_location("gen_audio_vector", ROOT / "tools" / "generate_audio_chunk_vector.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_firmware_vector_is_current():
    gen = _generator()
    assert (ROOT / "firmware" / "generated" / "zs_audio_chunk_vector.h").read_text() == gen.render()


def test_vector_decodes_to_the_tone():
    gen = _generator()
    c = ac.decode_chunk(gen.chunk())
    assert (c.station_id, c.event_id, c.chunk_count, c.sample_rate) == (17, (5 << 32) | 42, 1, 1000)
    seg = ac.AudioAssembler().add(c)
    assert seg is not None and seg.segment == "pre" and len(seg.pcm) == 2000
    ref = gen.pcm()
    err = sum((a - b) ** 2 for a, b in zip(seg.pcm, ref)); sig = sum(b * b for b in ref)
    assert 10 * math.log10(sig / err) > 18
    wav = ac.pcm_to_wav(seg.pcm, seg.sample_rate)
    assert wav[:4] == b"RIFF" and len(wav) == 44 + 4000


def _chunks(segment: bytes, rate: int = 32000, cmd: bytes = bytes(16)):
    digest = hashlib.sha256(segment).digest()
    n = ac.chunk_count(len(segment))
    return [ac.AudioChunk(17, cmd, 99, 1, i, n, ac.CODEC_IMA_ADPCM_1S, rate, 5_000_000, digest,
                          segment[i * ac.AUDIO_CHUNK_DATA_MAX:(i + 1) * ac.AUDIO_CHUNK_DATA_MAX]) for i in range(n)]


def test_multi_chunk_out_of_order_with_duplicates():
    tone = [int(8000 * math.sin(2 * math.pi * 185 * i / 32000)) for i in range(64000)]
    segment = ac.ima_encode_block(tone[:32000]) + ac.ima_encode_block(tone[32000:])
    parts = _chunks(segment)
    assert len(parts) == 11 and all(len(ac.encode_chunk(p)) < 4096 for p in parts)
    asm = ac.AudioAssembler()
    order = list(reversed(parts))
    for p in order[:-1]:
        assert asm.add(ac.decode_chunk(ac.encode_chunk(p))) is None
    assert asm.add(order[3]) is None and asm.duplicates == 1                 # QoS 1 redelivery
    assert asm.missing(17, bytes(16), 1) == [0]
    seg = asm.add(order[-1])
    assert seg is not None and seg.segment == "post" and seg.adpcm == segment and len(seg.pcm) == 64000


def test_rejections():
    segment = ac.ima_encode_block([0] * 1000)
    good = _chunks(segment, rate=1000)[0]
    raw = ac.encode_chunk(good)
    with pytest.raises(ValueError):
        ac.decode_chunk(raw[:-1])                                          # truncated
    with pytest.raises(ValueError):
        ac.encode_chunk(ac.AudioChunk(**{**good.__dict__, "segment": 2}))
    with pytest.raises(ValueError):
        ac.encode_chunk(ac.AudioChunk(**{**good.__dict__, "data": bytes(ac.AUDIO_CHUNK_DATA_MAX + 1)}))
    bad_digest = ac.AudioChunk(**{**good.__dict__, "segment_sha256": bytes(32)})
    with pytest.raises(ValueError):
        ac.AudioAssembler().add(bad_digest)                               # assembly digest mismatch
    asm = ac.AudioAssembler()
    parts = _chunks(bytes(ac.ima_encode_block([0] * 32000)) * 2)
    asm.add(parts[0])
    with pytest.raises(ValueError):
        asm.add(ac.AudioChunk(**{**parts[1].__dict__, "event_id": 100}))  # metadata disagrees
    with pytest.raises(ValueError):
        ac.decode_segment(b"\x00" * 10, 1000)                            # not whole blocks
    assert ac.chunk_count(30 * ac.ima_block_bytes(32000)) == 157 and ac.chunk_count(0) == 0
