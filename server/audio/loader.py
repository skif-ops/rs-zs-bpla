"""Audio loading helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from audio.preprocessing import AudioPreprocessor
from config import settings
from utils.file_utils import assert_audio_path


@dataclass(slots=True)
class LoadedAudio:
    """Loaded mono audio with quality metadata."""

    path: Path
    signal: np.ndarray
    sample_rate: int
    channels: int
    duration_seconds: float
    warnings: list[str]


class AudioLoader:
    """Load WAV/MP3/M4A files and convert them to normalized mono arrays."""

    def __init__(self, preprocessor: AudioPreprocessor | None = None) -> None:
        self.preprocessor = preprocessor or AudioPreprocessor()

    def load_audio(self, path: Path) -> LoadedAudio:
        """Load one supported audio file from disk."""

        assert_audio_path(path)
        data, sample_rate, read_warnings = self._read_audio(path)
        channels = int(data.shape[1])
        mono = np.mean(data, axis=1)
        signal, warnings = self.preprocessor.prepare(mono, sample_rate)
        warnings = read_warnings + warnings
        duration = len(signal) / float(sample_rate)
        return LoadedAudio(
            path=path,
            signal=signal,
            sample_rate=int(sample_rate),
            channels=channels,
            duration_seconds=duration,
            warnings=warnings,
        )

    def load_wav(self, path: Path) -> LoadedAudio:
        """Backward-compatible wrapper for older WAV-oriented call sites."""

        return self.load_audio(path)

    def load_many(self, paths: list[Path]) -> list[LoadedAudio]:
        """Load multiple supported audio files."""

        return [self.load_audio(path) for path in paths]

    def load_many_resampled(self, paths: list[Path]) -> tuple[list[LoadedAudio], list[str]]:
        """Load files and resample them to the first file's sample rate if needed."""

        loaded = self.load_many(paths)
        warnings: list[str] = []
        if not loaded:
            return loaded, warnings

        target_sr = loaded[0].sample_rate
        normalized: list[LoadedAudio] = []
        for item in loaded:
            if item.sample_rate == target_sr:
                normalized.append(item)
                continue

            warnings.append(
                f"{item.path.name}: sample rate {item.sample_rate} Hz was resampled "
                f"to {target_sr} Hz for localization."
            )
            resampled = librosa.resample(
                y=item.signal.astype(np.float32),
                orig_sr=item.sample_rate,
                target_sr=target_sr,
            )
            signal, prep_warnings = self.preprocessor.prepare(resampled, target_sr)
            normalized.append(
                LoadedAudio(
                    path=item.path,
                    signal=signal,
                    sample_rate=target_sr,
                    channels=item.channels,
                    duration_seconds=len(signal) / float(target_sr),
                    warnings=item.warnings + prep_warnings,
                )
            )

        if target_sr < settings.min_sample_rate_hz:
            warnings.append(
                "Localization source sample rate is below 20 kHz; TDOA precision "
                "may be reduced."
            )
        return normalized, warnings

    @staticmethod
    def _read_audio(path: Path) -> tuple[np.ndarray, int, list[str]]:
        """Read WAV/MP3/M4A audio while preserving the original sample rate."""

        warnings: list[str] = []
        suffix = path.suffix.lower()
        if suffix in {".mp3", ".m4a", ".aac"}:
            warnings.append(
                f"{suffix[1:].upper()} is a lossy compressed format; spectral features "
                "and TDOA timing may be less precise than with WAV."
            )

        # libsndfile (SoundFile) cannot decode AAC, so route M4A/AAC through the
        # ffmpeg/audioread path directly — that is the normal route here, not a
        # fallback after a failure.
        if suffix in {".m4a", ".aac"}:
            try:
                data, sample_rate = librosa.load(str(path), sr=None, mono=False, dtype=np.float32)
            except Exception as error:
                raise ValueError(
                    f"Could not read {path.name} as audio. For M4A/AAC, make sure "
                    "ffmpeg/audioread support is available."
                ) from error
            data_2d = data[:, np.newaxis] if data.ndim == 1 else data.T
            return np.asarray(data_2d, dtype=np.float32), int(sample_rate), warnings

        try:
            data, sample_rate = sf.read(path, always_2d=True)
            return np.asarray(data, dtype=np.float32), int(sample_rate), warnings
        except Exception as sf_error:
            try:
                data, sample_rate = librosa.load(
                    path=str(path),
                    sr=None,
                    mono=False,
                    dtype=np.float32,
                )
            except Exception as librosa_error:
                raise ValueError(
                    f"Could not read {path.name} as audio. "
                    "For compressed formats (MP3/M4A/AAC), make sure ffmpeg/audioread "
                    "support is available."
                ) from librosa_error

            if data.ndim == 1:
                data_2d = data[:, np.newaxis]
            else:
                data_2d = data.T
            warnings.append(
                f"{path.name}: decoded through Librosa fallback after SoundFile failed "
                f"({sf_error.__class__.__name__})."
            )
            return np.asarray(data_2d, dtype=np.float32), int(sample_rate), warnings
