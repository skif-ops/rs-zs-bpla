"""Audio feature extraction for drone acoustic analysis."""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np
from scipy import signal as scipy_signal

from config import settings
from models.schemas import AudioFeatureSet


@dataclass(slots=True)
class FeatureExtractionResult:
    """Feature model plus arrays needed by visualization."""

    features: AudioFeatureSet
    waveform_time: np.ndarray
    waveform: np.ndarray
    fft_frequency: np.ndarray
    fft_magnitude: np.ndarray
    stft_time: np.ndarray
    stft_frequency: np.ndarray
    stft_db: np.ndarray
    mel_db: np.ndarray
    mel_frequency: np.ndarray


class FeatureExtractor:
    """Extract spectral, harmonic and time-domain features from drone audio."""

    def __init__(self, n_mfcc: int = 13) -> None:
        self.n_mfcc = n_mfcc

    def extract(self, signal: np.ndarray, sample_rate: int) -> FeatureExtractionResult:
        """Extract all supported features from a normalized mono signal."""

        y = np.asarray(signal, dtype=np.float32)
        if y.size == 0:
            raise ValueError("Cannot extract features from an empty signal.")

        waveform_time = np.arange(len(y), dtype=np.float64) / float(sample_rate)
        fft_frequency, fft_magnitude = self._fft(y, sample_rate)
        stft_db, stft_frequency, stft_time = self._stft(y, sample_rate)
        mel_db, mel_frequency = self._mel(y, sample_rate)
        f0_track, f0_times = self._estimate_f0_track(y, sample_rate)
        fundamental = self._fundamental_from_track_or_spectrum(
            f0_track,
            fft_frequency,
            fft_magnitude,
        )
        harmonics = self._detect_harmonics(
            fundamental,
            fft_frequency,
            fft_magnitude,
        )
        harmonic_count = len(harmonics)
        harmonic_step = self._mean_harmonic_step(harmonics, fundamental)
        fundamental_variation = self._relative_std(f0_track)
        harmonic_variation = self._harmonic_variation(harmonics, fundamental)
        harmonic_stability = self._harmonic_stability(
            f0_track=f0_track,
            harmonics=harmonics,
            fundamental=fundamental,
        )

        average_energy = float(np.mean(np.square(y)))
        rms = float(np.sqrt(average_energy))
        zero_crossing_rate = self._librosa_scalar(
            lambda: librosa.feature.zero_crossing_rate(y=y).mean()
        )
        spectral_centroid = self._librosa_scalar(
            lambda: librosa.feature.spectral_centroid(y=y, sr=sample_rate).mean()
        )
        spectral_flatness = self._librosa_scalar(
            lambda: librosa.feature.spectral_flatness(y=y).mean()
        )
        spectral_bandwidth = self._librosa_scalar(
            lambda: librosa.feature.spectral_bandwidth(y=y, sr=sample_rate).mean()
        )
        mfcc_mean, mfcc_std = self._mfcc(y, sample_rate)
        noise_floor = self._noise_floor(fft_frequency, fft_magnitude)
        high_band_energy = self._band_energy_ratio(
            fft_frequency,
            fft_magnitude,
            settings.high_noise_band_low_hz,
            settings.high_noise_band_high_hz,
        )
        high_band_label = self._energy_label(high_band_energy)
        frequency_modulation_index = float(np.clip(fundamental_variation * 4.0, 0.0, 1.0))
        spectral_roughness = self._spectral_roughness(fft_frequency, fft_magnitude)
        doppler_stability = float(np.clip(1.0 - fundamental_variation * 5.0, 0.0, 1.0))

        features = AudioFeatureSet(
            fundamental_hz=float(fundamental),
            harmonic_count=harmonic_count,
            harmonic_step_hz=float(harmonic_step),
            harmonic_stability=float(harmonic_stability),
            average_energy=average_energy,
            rms=rms,
            zero_crossing_rate=float(zero_crossing_rate),
            spectral_centroid_hz=float(spectral_centroid),
            spectral_flatness=float(spectral_flatness),
            spectral_bandwidth_hz=float(spectral_bandwidth),
            mfcc_mean=[float(value) for value in mfcc_mean],
            mfcc_std=[float(value) for value in mfcc_std],
            noise_floor=float(noise_floor),
            high_band_energy_6_10khz=float(high_band_energy),
            high_band_energy_label=high_band_label,
            fundamental_variation=float(fundamental_variation),
            harmonic_variation=float(harmonic_variation),
            frequency_modulation_index=frequency_modulation_index,
            spectral_roughness=float(spectral_roughness),
            doppler_stability=doppler_stability,
            f0_track_hz=[float(value) for value in f0_track],
            time_axis_seconds=[float(value) for value in f0_times],
            detected_harmonics_hz=[float(value) for value in harmonics],
        )

        return FeatureExtractionResult(
            features=features,
            waveform_time=waveform_time,
            waveform=y,
            fft_frequency=fft_frequency,
            fft_magnitude=fft_magnitude,
            stft_time=stft_time,
            stft_frequency=stft_frequency,
            stft_db=stft_db,
            mel_db=mel_db,
            mel_frequency=mel_frequency,
        )

    @staticmethod
    def _fft(y: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
        """Return normalized FFT magnitude for display and peak search."""

        max_samples = min(len(y), 262_144)
        if max_samples < 16:
            padded = np.pad(y, (0, 16 - max_samples))
            max_samples = len(padded)
            segment = padded
        else:
            start = max((len(y) - max_samples) // 2, 0)
            segment = y[start : start + max_samples]

        window = scipy_signal.windows.hann(len(segment), sym=False)
        spectrum = np.fft.rfft(segment * window)
        magnitude = np.abs(spectrum)
        max_mag = float(np.max(magnitude))
        if max_mag > 0:
            magnitude = magnitude / max_mag
        frequency = np.fft.rfftfreq(len(segment), d=1.0 / sample_rate)
        return frequency.astype(np.float64), magnitude.astype(np.float64)

    @staticmethod
    def _stft(y: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Compute a log-amplitude STFT."""

        n_fft = min(4096, max(512, 2 ** int(np.floor(np.log2(max(len(y), 512))))))
        hop_length = max(n_fft // 4, 128)
        stft = librosa.stft(y=y, n_fft=n_fft, hop_length=hop_length, window="hann")
        stft_db = librosa.amplitude_to_db(np.abs(stft), ref=np.max)
        frequency = librosa.fft_frequencies(sr=sample_rate, n_fft=n_fft)
        time = librosa.frames_to_time(
            np.arange(stft_db.shape[1]),
            sr=sample_rate,
            hop_length=hop_length,
            n_fft=n_fft,
        )
        return stft_db, frequency, time

    @staticmethod
    def _mel(y: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
        """Compute a Mel spectrogram in dB."""

        n_fft = min(4096, max(512, 2 ** int(np.floor(np.log2(max(len(y), 512))))))
        hop_length = max(n_fft // 4, 128)
        n_mels = 96
        mel = librosa.feature.melspectrogram(
            y=y,
            sr=sample_rate,
            n_fft=n_fft,
            hop_length=hop_length,
            n_mels=n_mels,
            power=2.0,
        )
        mel_db = librosa.power_to_db(mel, ref=np.max)
        mel_frequency = librosa.mel_frequencies(
            n_mels=n_mels,
            fmin=0,
            fmax=sample_rate / 2.0,
        )
        return mel_db, mel_frequency

    @staticmethod
    def _estimate_f0_track(y: np.ndarray, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
        """Estimate fundamental-frequency track with librosa.yin."""

        nyquist = sample_rate / 2.0
        fmin = settings.drone_low_frequency_hz
        fmax = min(settings.drone_high_frequency_hz, nyquist - 1.0)
        if len(y) < 1024 or fmax <= fmin:
            return np.array([], dtype=np.float64), np.array([], dtype=np.float64)

        frame_length = min(4096, max(1024, 2 ** int(np.floor(np.log2(len(y))))))
        hop_length = max(frame_length // 4, 256)
        try:
            f0 = librosa.yin(
                y=y,
                fmin=fmin,
                fmax=fmax,
                sr=sample_rate,
                frame_length=frame_length,
                hop_length=hop_length,
            )
            times = librosa.frames_to_time(
                np.arange(len(f0)),
                sr=sample_rate,
                hop_length=hop_length,
                n_fft=frame_length,
            )
        except Exception:
            return np.array([], dtype=np.float64), np.array([], dtype=np.float64)

        mask = np.isfinite(f0) & (f0 >= fmin) & (f0 <= fmax)
        return f0[mask].astype(np.float64), times[mask].astype(np.float64)

    @staticmethod
    def _fundamental_from_track_or_spectrum(
        f0_track: np.ndarray,
        frequency: np.ndarray,
        magnitude: np.ndarray,
    ) -> float:
        """Use F0 track first, then spectral peak fallback."""

        valid = f0_track[np.isfinite(f0_track)]
        if valid.size:
            return float(np.median(valid))

        mask = (
            (frequency >= settings.drone_low_frequency_hz)
            & (frequency <= settings.drone_high_frequency_hz)
        )
        if not np.any(mask):
            return 0.0
        band_freq = frequency[mask]
        band_mag = magnitude[mask]
        if band_mag.size == 0 or float(np.max(band_mag)) <= 0:
            return 0.0
        return float(band_freq[int(np.argmax(band_mag))])

    @staticmethod
    def _detect_harmonics(
        fundamental: float,
        frequency: np.ndarray,
        magnitude: np.ndarray,
    ) -> list[float]:
        """Detect harmonics close to integer multiples of F0."""

        if fundamental <= 0:
            return []

        max_frequency = min(settings.fft_max_frequency_hz, float(np.max(frequency)))
        search_mask = (frequency >= fundamental * 0.7) & (frequency <= max_frequency)
        if not np.any(search_mask):
            return []

        band_mag = magnitude[search_mask]
        prominence = max(0.015, float(np.median(band_mag) * 4.0))
        peaks, _ = scipy_signal.find_peaks(
            band_mag,
            prominence=prominence,
            distance=max(1, int(fundamental / max(frequency[1] - frequency[0], 1e-6) * 0.45)),
        )
        peak_freq = frequency[search_mask][peaks]
        peak_mag = band_mag[peaks]
        if peak_freq.size == 0:
            return [fundamental]

        harmonics: list[float] = []
        max_index = int(max_frequency // fundamental)
        for harmonic_index in range(1, max_index + 1):
            target = harmonic_index * fundamental
            tolerance = max(5.0, fundamental * 0.08)
            candidates = np.where(np.abs(peak_freq - target) <= tolerance)[0]
            if candidates.size == 0:
                continue
            best_local = candidates[int(np.argmax(peak_mag[candidates]))]
            harmonics.append(float(peak_freq[best_local]))
        return harmonics

    @staticmethod
    def _mean_harmonic_step(harmonics: list[float], fundamental: float) -> float:
        """Return the typical spacing between detected harmonics.

        Uses the median of consecutive spacings, not the mean, so a few missing
        harmonics (large gaps) cannot inflate the reported step into a number
        that no longer reflects the real comb spacing.
        """

        if len(harmonics) >= 2:
            return float(np.median(np.diff(sorted(harmonics))))
        return float(fundamental)

    @staticmethod
    def _relative_std(values: np.ndarray) -> float:
        """Return coefficient of variation with robust guards."""

        valid = values[np.isfinite(values)]
        if valid.size < 2:
            return 0.0
        mean = float(np.mean(valid))
        if abs(mean) < 1e-9:
            return 0.0
        return float(np.clip(np.std(valid) / abs(mean), 0.0, 1.0))

    @staticmethod
    def _harmonic_variation(harmonics: list[float], fundamental: float) -> float:
        """Measure harmonic spacing irregularity."""

        if fundamental <= 0 or len(harmonics) < 3:
            return 1.0 if fundamental <= 0 else 0.0
        sorted_harmonics = np.array(sorted(harmonics), dtype=np.float64)
        steps = np.diff(sorted_harmonics)
        return float(np.clip(np.std(steps) / fundamental, 0.0, 1.0))

    @staticmethod
    def _harmonic_stability(
        f0_track: np.ndarray,
        harmonics: list[float],
        fundamental: float,
    ) -> float:
        """Combine F0 steadiness and harmonic regularity into 0..1 stability."""

        if fundamental <= 0:
            return 0.0
        f0_stability = 1.0 - FeatureExtractor._relative_std(f0_track)
        harmonic_variation = FeatureExtractor._harmonic_variation(harmonics, fundamental)
        spacing_stability = 1.0 - harmonic_variation
        harmonic_presence = np.clip(len(harmonics) / 24.0, 0.15, 1.0)
        return float(np.clip(0.45 * f0_stability + 0.35 * spacing_stability + 0.20 * harmonic_presence, 0.0, 1.0))

    @staticmethod
    def _librosa_scalar(fn: callable) -> float:
        """Run a librosa feature function and return a finite scalar."""

        try:
            value = float(fn())
        except Exception:
            return 0.0
        if not np.isfinite(value):
            return 0.0
        return value

    def _mfcc(self, y: np.ndarray, sample_rate: int) -> tuple[list[float], list[float]]:
        """Return MFCC means and standard deviations."""

        try:
            mfcc = librosa.feature.mfcc(y=y, sr=sample_rate, n_mfcc=self.n_mfcc)
        except Exception:
            zeros = [0.0] * self.n_mfcc
            return zeros, zeros
        return (
            [float(value) for value in np.mean(mfcc, axis=1)],
            [float(value) for value in np.std(mfcc, axis=1)],
        )

    @staticmethod
    def _noise_floor(frequency: np.ndarray, magnitude: np.ndarray) -> float:
        """Estimate a high-frequency noise floor."""

        mask = frequency >= min(3_000.0, float(np.max(frequency)) * 0.5)
        if not np.any(mask):
            return 0.0
        return float(np.median(magnitude[mask]))

    @staticmethod
    def _band_energy_ratio(
        frequency: np.ndarray,
        magnitude: np.ndarray,
        low_hz: float,
        high_hz: float,
    ) -> float:
        """Return energy ratio in a frequency band."""

        power = np.square(magnitude)
        total_mask = frequency > 20.0
        total = float(np.sum(power[total_mask]))
        if total <= 1e-12:
            return 0.0
        band_mask = (frequency >= low_hz) & (frequency <= high_hz)
        return float(np.clip(np.sum(power[band_mask]) / total, 0.0, 1.0))

    @staticmethod
    def _energy_label(value: float) -> str:
        """Convert high-band energy ratio into a label."""

        if value >= 0.12:
            return "high"
        if value >= 0.04:
            return "medium"
        return "low"

    @staticmethod
    def _spectral_roughness(frequency: np.ndarray, magnitude: np.ndarray) -> float:
        """Estimate spectral roughness from normalized local magnitude changes."""

        mask = (frequency >= 50.0) & (frequency <= min(10_000.0, float(np.max(frequency))))
        if np.count_nonzero(mask) < 3:
            return 0.0
        mag = magnitude[mask]
        if float(np.max(mag)) <= 0:
            return 0.0
        mag = mag / float(np.max(mag))
        roughness = float(np.mean(np.abs(np.diff(mag))))
        return float(np.clip(roughness * 35.0, 0.0, 1.0))

