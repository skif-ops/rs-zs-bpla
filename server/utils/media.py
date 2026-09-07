"""Video helpers: extract an audio track from an uploaded video via ffmpeg."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
SUPPORTED_VIDEO_EXTENSIONS_TEXT = "MP4, MOV, MKV, AVI, M4V or WEBM"


def is_supported_video_filename(filename: str | None) -> bool:
    """Return True if a filename has a supported video extension."""

    if not filename:
        return False
    return Path(filename).suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def extract_audio_to_wav(video_path: Path, out_dir: Path) -> Path:
    """Extract the audio track of a video to a 48 kHz mono WAV via ffmpeg.

    48 kHz keeps the rate above the analysis minimum (no quality warning) and
    mono matches the loader's downmix. The resulting WAV then flows through the
    normal ``add_recording`` path. Raises ValueError (Russian message) when
    ffmpeg is missing, fails, or the video has no audio track.
    """

    if shutil.which("ffmpeg") is None:
        raise ValueError("ffmpeg не найден — извлечение звука из видео недоступно.")

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{video_path.stem}_audio.wav"
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "48000",
        "-ac",
        "1",
        str(out_path),
    ]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Извлечение звука из {video_path.name} превысило лимит времени.") from exc

    if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        tail = (proc.stderr or "")[-400:]
        raise ValueError(
            f"Не удалось извлечь звук из {video_path.name} "
            "(возможно, в видео нет аудиодорожки). " + tail
        )
    return out_path
