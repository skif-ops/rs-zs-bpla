import shutil
import subprocess

import numpy as np
import pytest
import soundfile as sf

from utils.media import extract_audio_to_wav, is_supported_video_filename


def test_is_supported_video_filename():
    assert is_supported_video_filename("clip.mp4")
    assert is_supported_video_filename("CLIP.MOV")
    assert is_supported_video_filename("x.webm")
    assert not is_supported_video_filename("x.wav")
    assert not is_supported_video_filename(None)


def test_extract_audio_raises_on_missing_audio(tmp_path):
    bad = tmp_path / "not_a_video.mp4"
    bad.write_bytes(b"\x00\x01\x02not a real video")
    with pytest.raises(ValueError):
        extract_audio_to_wav(bad, tmp_path)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_extract_audio_to_wav_roundtrip(tmp_path):
    video = tmp_path / "tone.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=300:duration=0.6",
            "-f", "lavfi", "-i", "color=c=black:s=32x32:r=10:d=0.6",
            "-shortest", "-pix_fmt", "yuv420p", str(video),
        ],
        capture_output=True,
        check=True,
    )
    wav = extract_audio_to_wav(video, tmp_path)
    assert wav.exists()
    signal, sr = sf.read(wav)
    assert sr == 48000
    assert len(signal) > 0
    assert np.max(np.abs(signal)) > 0
