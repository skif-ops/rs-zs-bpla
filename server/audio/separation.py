"""Separate a low-frequency drone/rotor source from background noise.

The single-file classifier answers "what is the loudest source?" by averaging
broadband features over the whole file. That mathematically erases a quiet
background drone hiding under a louder foreground (birds, wind, traffic): the
foreground wins every window and the average crowns it.

This module solves the complementary problem — *detection of a co-occurring
tonal source* — with three steps that are blind to the loud foreground:

1. Decimate to a low sample rate. The anti-alias filter removes the entire bird
   band above ~3 kHz outright, so the drone's low-frequency harmonic comb is no
   longer 15-25 dB down in a broadband mix.
2. Estimate the true fundamental by fitting a harmonic comb (GCD over the
   spectral peaks), not by peak-picking — otherwise a strong upper harmonic is
   mistaken for the fundamental.
3. Soft-mask the STFT around integer multiples of that fundamental to
   reconstruct a drone-only signal, with the remainder returned as the residual
   noise. The two sum back to the decimated mix, so the split is exact.

It then reports detection statistics (harmonic SNR, persistence over time,
frequency steadiness, integer-vs-half-order ratio) that separate a steady
rotor/engine from transient bird chirps and from mains hum.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import gcd

import numpy as np
from scipy import signal as scipy_signal

from config import settings
from models.schemas import DroneConstructionFeatures, DroneSeparationFindings


@dataclass(slots=True)
class DroneSeparation:
    """Isolated drone signal, residual noise and serializable findings."""

    findings: DroneSeparationFindings
    isolated: np.ndarray
    residual: np.ndarray
    sample_rate: int


class DroneSeparator:
    """Isolate a steady low-frequency harmonic comb (rotor/engine) from noise."""

    def __init__(
        self,
        target_rate: int | None = None,
        band_low_hz: float | None = None,
        band_high_hz: float | None = None,
    ) -> None:
        self.target_rate = int(target_rate or settings.separation_sample_rate_hz)
        self.band_low_hz = float(band_low_hz or settings.separation_band_low_hz)
        self.band_high_hz = float(band_high_hz or settings.separation_band_high_hz)

    def separate(self, signal: np.ndarray, sample_rate: int) -> DroneSeparation:
        """Split a mono mix into an isolated drone signal and residual noise."""

        y_lo, sr_lo = self._decimate(signal, sample_rate)
        if y_lo.size < sr_lo // 2:
            return self._empty(sr_lo)

        band = self._bandpass(y_lo, sr_lo)
        band = self._suppress_mains_harmonics(band, sr_lo)
        freqs, stft = self._stft(band, sr_lo)
        spec_db, spec_f = self._median_spectrum_db(freqs, stft)

        fundamental = self._fit_comb_fundamental(spec_f, spec_db)
        if fundamental <= 0.0:
            return self._empty(sr_lo, spectrum=(spec_f, spec_db))

        dominant_hz = self._dominant_harmonic(spec_f, spec_db, fundamental)
        isolated, residual = self._harmonic_mask(band, freqs, stft, sr_lo, fundamental)
        stats = self._window_statistics(band, sr_lo, fundamental, dominant_hz)
        hires = self._hires_spectrum(band, sr_lo)
        findings = self._build_findings(
            fundamental=fundamental,
            dominant_hz=dominant_hz,
            stats=stats,
            spectrum=(spec_f, spec_db),
            hires=hires,
            sr_lo=sr_lo,
            isolated=isolated,
            residual=residual,
        )
        return DroneSeparation(
            findings=findings,
            isolated=isolated.astype(np.float32),
            residual=residual.astype(np.float32),
            sample_rate=sr_lo,
        )

    def _decimate(self, signal: np.ndarray, sample_rate: int) -> tuple[np.ndarray, int]:
        """Resample to the low analysis rate, removing the bird band entirely."""

        y = np.asarray(signal, dtype=np.float64)
        if y.size:
            y = y - float(np.mean(y))
        target = min(self.target_rate, sample_rate)
        if target >= sample_rate:
            return y, int(sample_rate)
        divisor = gcd(int(sample_rate), int(target))
        up = int(target) // divisor
        down = int(sample_rate) // divisor
        resampled = scipy_signal.resample_poly(y, up, down)
        return np.asarray(resampled, dtype=np.float64), int(target)

    def _bandpass(self, y: np.ndarray, sr: int) -> np.ndarray:
        """Keep only the drone harmonic region."""

        nyquist = sr / 2.0
        high = min(self.band_high_hz, nyquist - 1.0)
        low = max(self.band_low_hz, 1.0)
        if high <= low:
            return y
        sos = scipy_signal.butter(6, [low, high], btype="band", fs=sr, output="sos")
        return scipy_signal.sosfiltfilt(sos, y)

    @staticmethod
    def _suppress_mains_harmonics(y: np.ndarray, sr: int) -> np.ndarray:
        """Remove narrow, grid-locked 50/60 Hz lines before comb fitting.

        A strong 100 or 200 Hz mains harmonic can make the missing-fundamental
        search descend to 25, 16.7 or 12.5 Hz and bypass the existing 50/60 Hz
        veto. Narrow fixed-band notches remove that alias while retaining the
        wider and Doppler-shifted propulsion tracks around it.
        """

        cleaned = np.asarray(y, dtype=np.float64)
        if cleaned.size < 32 or sr <= 0:
            return cleaned
        upper = min(
            settings.mains_notch_max_frequency_hz,
            settings.separation_band_high_hz,
            sr / 2.0 - 2.0,
        )
        bandwidth = max(float(settings.mains_notch_bandwidth_hz), 0.1)
        frequencies: list[float] = []
        for base in settings.mains_base_frequencies_hz:
            harmonic = float(base)
            while harmonic <= upper + 1e-9:
                if not any(abs(harmonic - existing) < bandwidth * 0.5 for existing in frequencies):
                    frequencies.append(harmonic)
                harmonic += float(base)
        for frequency in sorted(frequencies):
            quality = max(float(frequency / bandwidth), 2.0)
            b, a = scipy_signal.iirnotch(frequency, quality, fs=sr)
            cleaned = scipy_signal.filtfilt(b, a, cleaned)
        return np.asarray(cleaned, dtype=np.float64)

    @staticmethod
    def _stft_layout(sr: int, n_samples: int) -> tuple[int, int]:
        """STFT (nperseg, noverlap) resolving ~20 Hz, clamped to the signal.

        Deriving the segment size from the actual length keeps a short signal
        from tripping scipy's ``noverlap < nperseg`` constraint, and guarantees
        the STFT and the inverse in ``_harmonic_mask`` use identical parameters.
        """

        n_fft = 2048 if sr <= 8_000 else 4096
        nperseg = max(min(n_fft, n_samples), 16)
        hop = max(nperseg // 4, 1)
        return nperseg, nperseg - hop

    def _stft(self, y: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
        """Return (frequencies, complex STFT) using a COLA-compliant window."""

        nperseg, noverlap = self._stft_layout(sr, len(y))
        freqs, _, stft = scipy_signal.stft(
            y,
            fs=sr,
            window="hann",
            nperseg=nperseg,
            noverlap=noverlap,
            boundary="zeros",
        )
        return freqs, stft

    @staticmethod
    def _median_spectrum_db(freqs: np.ndarray, stft: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Temporal-median magnitude spectrum (isolates persistent tones)."""

        mag = np.abs(stft)
        median = np.median(mag, axis=1)
        peak = float(np.max(median)) if median.size else 0.0
        ref = peak if peak > 0 else 1.0
        db = 20.0 * np.log10(median / ref + 1e-9)
        return db, freqs

    def _fit_comb_fundamental(self, freqs: np.ndarray, spec_db: np.ndarray) -> float:
        """Estimate the blade-pass fundamental robustly, including on multirotors.

        The loudest tonal line is the blade-pass anchor. We descend to a lower
        sub-harmonic D/k only when that lower fundamental's own first harmonics
        are really present in the spectrum (a genuine missing-fundamental comb,
        e.g. a loud 5th harmonic). A multirotor's dense cluster of close rotor
        tones has no real low harmonics, so it correctly keeps the blade-pass
        itself instead of locking onto a phantom low frequency.
        """

        bin_hz = float(freqs[1] - freqs[0]) if freqs.size > 1 else 1.0
        if bin_hz <= 0:
            return 0.0
        power = np.power(10.0, spec_db / 10.0)
        fmax = min(self.band_high_hz, float(freqs[-1]))
        f0_min = max(settings.comb_f0_min_hz, bin_hz)

        band = (freqs >= f0_min) & (freqs <= fmax)
        if not np.any(band):
            return 0.0
        band_idx = np.where(band)[0]
        dominant = float(freqs[band_idx[int(np.argmax(power[band_idx]))]])
        if dominant <= 0:
            return 0.0
        floor = float(np.median(spec_db))

        def low_harmonics_present(f0: float) -> int:
            """How many of the first four harmonics of f0 are real peaks."""

            tol = max(1.5 * bin_hz, f0 * 0.04)
            hits = 0
            for k in range(1, 5):
                target = f0 * k
                if target > fmax:
                    break
                near = np.abs(freqs - target) <= tol
                if np.any(near) and float(np.max(spec_db[near])) >= floor + 8.0:
                    hits += 1
            return hits

        def comb_power(f0: float) -> float:
            tol = max(1.5 * bin_hz, f0 * 0.05)
            total = 0.0
            for k in range(1, settings.comb_max_harmonics + 1):
                target = f0 * k
                if target > fmax:
                    break
                near = np.abs(freqs - target) <= tol
                if np.any(near):
                    total += float(np.max(power[near]))
            return total

        # Candidate fundamentals: the blade-pass itself (k=1), plus any lower
        # sub-harmonic D/k (k<=6, so the loud line is at most a 6th harmonic)
        # whose own first harmonics are really present. The one whose full integer
        # comb captures the most energy is the true fundamental — so a multirotor
        # cluster keeps the blade-pass, while a missing-fundamental comb correctly
        # descends to its real low fundamental.
        candidates = [dominant]
        for k in range(2, 7):
            candidate = dominant / k
            if candidate < f0_min:
                break
            if low_harmonics_present(candidate) >= 3:
                candidates.append(candidate)
        best = max(candidates, key=comb_power)

        grid = np.arange(best * 0.95, best * 1.05, bin_hz / 4.0)
        grid = grid[grid >= f0_min]
        if grid.size == 0:
            return float(best)
        scores = np.array([comb_power(f0) for f0 in grid])
        return float(grid[int(np.argmax(scores))])

    def _harmonic_mask(
        self,
        band: np.ndarray,
        freqs: np.ndarray,
        stft: np.ndarray,
        sr: int,
        fundamental: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Soft-mask the STFT around integer harmonics; residual = band - drone."""

        bin_hz = float(freqs[1] - freqs[0]) if freqs.size > 1 else 1.0
        # Capture the full leakage skirt of each tooth so the residual is left
        # comb-free, but stay well inside the inter-harmonic spacing.
        sigma_hz = min(max(2.2 * bin_hz, fundamental * 0.08), fundamental * 0.3)
        mask = np.zeros_like(freqs, dtype=np.float64)
        k = 1
        while fundamental * k <= min(self.band_high_hz, float(freqs[-1])):
            mask = np.maximum(mask, np.exp(-0.5 * ((freqs - fundamental * k) / sigma_hz) ** 2))
            k += 1
        masked = stft * mask[:, None]

        nperseg, noverlap = self._stft_layout(sr, len(band))
        _, isolated = scipy_signal.istft(
            masked,
            fs=sr,
            window="hann",
            nperseg=nperseg,
            noverlap=noverlap,
            boundary=True,
        )
        isolated = self._fit_length(isolated, len(band))
        residual = band - isolated
        return isolated, residual

    def _window_statistics(
        self,
        band: np.ndarray,
        sr: int,
        fundamental: float,
        dominant_hz: float,
    ) -> dict[str, float]:
        """Per-second harmonic SNR, persistence, steadiness and order ratio.

        Steadiness tracks the single globally-dominant harmonic line across
        windows (a true engine tone barely moves); following "whichever harmonic
        is loudest this window" would hop between teeth and look unsteady.
        """

        win = max(int(round(settings.comb_window_seconds * sr)), 256)
        hop = max(win // 2, 1)
        window = scipy_signal.windows.hann(win, sym=False)
        present_db = settings.comb_present_snr_db
        track_tol = max(fundamental * 0.25, 4.0)

        snrs: list[float] = []
        dominant: list[float] = []
        int_orders: list[float] = []
        half_orders: list[float] = []
        present = 0
        total = 0
        for start in range(0, max(len(band) - win + 1, 1), hop):
            seg = band[start:start + win]
            if seg.size < win:
                break
            spec = np.abs(np.fft.rfft(seg * window))
            f = np.fft.rfftfreq(win, d=1.0 / sr)
            power = np.square(spec)
            snr_db, integer_p, half_p = self._window_harmonic_snr(f, power, fundamental)
            total += 1
            snrs.append(snr_db)
            int_orders.append(integer_p)
            half_orders.append(half_p)
            if snr_db >= present_db:
                present += 1
            if dominant_hz > 0:
                near = np.abs(f - dominant_hz) <= track_tol
                if np.any(near):
                    dominant.append(float(f[near][int(np.argmax(power[near]))]))

        median_snr = float(np.median(snrs)) if snrs else 0.0
        persistence = float(present / total) if total else 0.0
        steadiness_cv = (
            float(np.std(dominant) / np.mean(dominant))
            if len(dominant) >= 2 and np.mean(dominant) > 0
            else 1.0
        )
        integer_sum = float(np.sum(int_orders))
        half_sum = float(np.sum(half_orders))
        order_ratio = integer_sum / (integer_sum + half_sum) if (integer_sum + half_sum) > 0 else 0.0
        return {
            "median_snr_db": median_snr,
            "persistence": persistence,
            "steadiness_cv": steadiness_cv,
            "integer_order_ratio": order_ratio,
        }

    @staticmethod
    def _window_harmonic_snr(
        freqs: np.ndarray,
        power: np.ndarray,
        fundamental: float,
    ) -> tuple[float, float, float]:
        """Harmonic-to-noise ratio in dB plus integer/half-order power sums."""

        bin_hz = float(freqs[1] - freqs[0]) if freqs.size > 1 else 1.0
        tol = max(1.5 * bin_hz, fundamental * 0.06)
        fmax = min(settings.separation_band_high_hz, float(freqs[-1]))

        harmonic_mask = np.zeros_like(freqs, dtype=bool)
        peak_powers: list[float] = []
        integer_power = 0.0
        for k in range(1, settings.comb_max_harmonics + 1):
            target = fundamental * k
            if target > fmax:
                break
            near = np.abs(freqs - target) <= tol
            if not np.any(near):
                continue
            harmonic_mask |= near
            local_peak = float(np.max(power[near]))
            peak_powers.append(local_peak)
            integer_power += local_peak

        half_power = 0.0
        for k in range(0, settings.comb_max_harmonics):
            target = fundamental * (k + 0.5)
            if target > fmax:
                break
            near = np.abs(freqs - target) <= tol
            if np.any(near):
                half_power += float(np.max(power[near]))

        band_mask = (freqs >= fundamental * 0.5) & (freqs <= fmax)
        noise_mask = band_mask & ~harmonic_mask
        noise_floor = float(np.median(power[noise_mask])) if np.any(noise_mask) else 0.0
        harmonic_level = float(np.mean(peak_powers)) if peak_powers else 0.0
        if noise_floor <= 1e-20 or harmonic_level <= 0.0:
            return 0.0, integer_power, half_power
        snr_db = 10.0 * np.log10(harmonic_level / noise_floor)
        return float(snr_db), integer_power, half_power

    def _build_findings(
        self,
        fundamental: float,
        dominant_hz: float,
        stats: dict[str, float],
        spectrum: tuple[np.ndarray, np.ndarray],
        hires: tuple[np.ndarray, np.ndarray],
        sr_lo: int,
        isolated: np.ndarray,
        residual: np.ndarray,
    ) -> DroneSeparationFindings:
        """Apply detection gates and assemble the serializable findings."""

        spec_f, spec_db = spectrum
        harmonic_count = self._count_harmonics(spec_f, spec_db, fundamental)
        median_snr = stats["median_snr_db"]
        persistence = stats["persistence"]
        steadiness_cv = stats["steadiness_cv"]
        order_ratio = stats["integer_order_ratio"]

        gain_db = self._separation_gain_db(isolated, residual)
        # A loud, clearly-tonal source is allowed a wider frequency drift before
        # it is rejected as unsteady, so a fast-moving (Doppler) drone still fires.
        cv_max = settings.comb_steadiness_cv_max
        if median_snr >= 20.0:
            cv_max = min(cv_max * 2.0, 0.25)
        is_mains = self._looks_like_mains(fundamental, steadiness_cv, order_ratio)
        # A high blade-pass leaves fewer harmonics inside the band, so when the
        # tone is persistent and loud (clear drone evidence) we accept fewer of
        # them rather than miss a real maneuvering drone.
        strong_evidence = persistence >= 0.6 and median_snr >= 12.0
        min_harmonics = 2 if strong_evidence else settings.comb_min_harmonics
        present = (
            persistence >= settings.comb_persistence_threshold
            and median_snr >= settings.comb_present_snr_db
            and steadiness_cv <= cv_max
            and harmonic_count >= min_harmonics
            and not is_mains
        )

        confidence = self._confidence(
            present, persistence, median_snr, steadiness_cv, harmonic_count, gain_db
        )
        likely = self._likely_source(present, order_ratio, is_mains)
        explanation = self._explain(present, fundamental, dominant_hz, persistence, median_snr, likely)
        construction = (
            self._construction_features(
                spec_f, spec_db, hires, fundamental, dominant_hz, steadiness_cv, harmonic_count
            )
            if fundamental > 0 and not is_mains
            else None
        )

        return DroneSeparationFindings(
            drone_present=present,
            confidence=round(confidence, 3),
            fundamental_hz=round(float(fundamental), 2),
            dominant_harmonic_hz=round(float(dominant_hz), 2),
            harmonic_count=int(harmonic_count),
            harmonic_snr_db=round(float(median_snr), 1),
            persistence=round(float(persistence), 3),
            steadiness_cv=round(float(steadiness_cv), 4),
            integer_order_ratio=round(float(order_ratio), 3),
            separation_gain_db=round(float(gain_db), 1),
            likely_source=likely,
            construction=construction,
            sample_rate=int(sr_lo),
            explanation=explanation,
            spectrum_freq_hz=[round(float(v), 2) for v in spec_f],
            spectrum_db=[round(float(v), 1) for v in spec_db],
        )

    @staticmethod
    def _hires_spectrum(band: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
        """High-resolution Welch spectrum for resolving rotor/blade fine structure."""

        nperseg = int(min(len(band), 16_384))
        if nperseg < 256:
            return np.zeros(0), np.zeros(0)
        freqs, power = scipy_signal.welch(
            band, fs=sr, nperseg=nperseg, noverlap=nperseg // 2, scaling="spectrum"
        )
        return freqs, power

    def _construction_features(
        self,
        freqs: np.ndarray,
        spec_db: np.ndarray,
        hires: tuple[np.ndarray, np.ndarray],
        fundamental: float,
        dominant_hz: float,
        steadiness_cv: float,
        harmonic_count: int,
    ) -> DroneConstructionFeatures:
        """Infer first-order platform descriptors from the isolated comb."""

        power = np.power(10.0, spec_db / 10.0)
        hf, hp = hires
        use_hires = hf.size > 8
        blade_count = self._estimate_blade_count(
            hf if use_hires else freqs,
            hp if use_hires else power,
            fundamental,
        )
        shaft_hz = fundamental / blade_count if blade_count >= 1 else fundamental
        rotor_rpm = shaft_hz * 60.0
        rotor_count = self._estimate_rotor_count(
            hf if use_hires else freqs,
            hp if use_hires else power,
            fundamental,
            dominant_hz,
        )
        half_ratio, tonality = self._order_structure(freqs, power, fundamental)
        propulsion, p_conf = self._propulsion(half_ratio, steadiness_cv, tonality)
        summary = self._construction_summary(
            blade_count, rotor_count, rotor_rpm, propulsion, fundamental
        )
        return DroneConstructionFeatures(
            blade_pass_hz=round(float(fundamental), 2),
            rotor_rpm=round(float(rotor_rpm), 0),
            blade_count_estimate=int(blade_count),
            rotor_count_estimate=int(rotor_count),
            propulsion=propulsion,
            propulsion_confidence=round(float(p_conf), 3),
            half_order_ratio=round(float(half_ratio), 3),
            tonality=round(float(tonality), 3),
            summary=summary,
        )

    @staticmethod
    def _estimate_blade_count(freqs: np.ndarray, power: np.ndarray, fundamental: float) -> int:
        """Detect a once-per-revolution sub-line to infer the blade count.

        If the comb fundamental is the blade-pass rate, an imbalance tone sits at
        the shaft rate F0/N. Finding a clean sub-line at F0/N reveals N blades;
        absent one, the fundamental is treated as the rotation rate (count 1).
        """

        if freqs.size < 2:
            return 1
        bin_hz = float(freqs[1] - freqs[0])
        spec_db = 10.0 * np.log10(power + 1e-20)
        floor = float(np.median(spec_db))
        best_n = 1
        best_db = floor + 8.0
        for n in (2, 3, 4):
            sub = fundamental / n
            if sub < max(settings.comb_f0_min_hz, bin_hz):
                continue
            tol = max(1.5 * bin_hz, sub * 0.06)
            near = np.abs(freqs - sub) <= tol
            if np.any(near):
                level = float(np.max(spec_db[near]))
                if level > best_db:
                    best_db = level
                    best_n = n
        return best_n

    @staticmethod
    def _estimate_rotor_count(
        freqs: np.ndarray,
        power: np.ndarray,
        fundamental: float,
        dominant_hz: float,
    ) -> int:
        """Approximate rotor count from the blade-pass cluster.

        On a multirotor each motor runs at a slightly different RPM, so the
        blade-pass tones form a cluster of close peaks around the dominant line;
        we count the resolvable peaks there. A single-rotor source shows one
        peak. This is a coarse hint, not a hard count.
        """

        if dominant_hz <= 0 or freqs.size < 2:
            return 1
        bin_hz = float(freqs[1] - freqs[0])
        floor_global = float(np.median(10.0 * np.log10(power + 1e-20)))
        lo = dominant_hz * 0.82
        hi = dominant_hz * 1.18
        window = (freqs >= lo) & (freqs <= hi)
        if np.count_nonzero(window) < 6:
            return 1
        seg_db = 10.0 * np.log10(power[window] + 1e-20)
        distance = max(1, int(round((dominant_hz * 0.015) / bin_hz)))
        peaks, _ = scipy_signal.find_peaks(seg_db, prominence=4.0, distance=distance)
        strong = [p for p in peaks if seg_db[p] >= floor_global + 6.0]
        return int(np.clip(len(strong), 1, 8))

    @staticmethod
    def _order_structure(
        freqs: np.ndarray,
        power: np.ndarray,
        fundamental: float,
    ) -> tuple[float, float]:
        """Return (half-order fraction, tonality) from the median spectrum."""

        bin_hz = float(freqs[1] - freqs[0]) if freqs.size > 1 else 1.0
        tol = max(1.5 * bin_hz, fundamental * 0.06)
        fmax = min(settings.separation_band_high_hz, float(freqs[-1]))
        harmonic_mask = np.zeros_like(freqs, dtype=bool)
        integer_power = 0.0
        peak_powers: list[float] = []
        for k in range(1, settings.comb_max_harmonics + 1):
            target = fundamental * k
            if target > fmax:
                break
            near = np.abs(freqs - target) <= tol
            if np.any(near):
                harmonic_mask |= near
                local = float(np.max(power[near]))
                integer_power += local
                peak_powers.append(local)
        half_power = 0.0
        for k in range(0, settings.comb_max_harmonics):
            target = fundamental * (k + 0.5)
            if target > fmax or target < fundamental * 0.5:
                continue
            near = np.abs(freqs - target) <= tol
            if np.any(near):
                half_power += float(np.max(power[near]))
        half_ratio = half_power / (integer_power + half_power) if (integer_power + half_power) > 0 else 0.0

        band = (freqs >= fundamental * 0.5) & (freqs <= fmax)
        floor = float(np.median(power[band & ~harmonic_mask])) if np.any(band & ~harmonic_mask) else 0.0
        harmonic_level = float(np.mean(peak_powers)) if peak_powers else 0.0
        tonality = floor / harmonic_level if harmonic_level > 0 else 1.0
        return float(half_ratio), float(np.clip(tonality, 0.0, 1.0))

    @staticmethod
    def _propulsion(half_ratio: float, steadiness_cv: float, tonality: float) -> tuple[str, float]:
        """Classify propulsion as electric vs combustion from order structure.

        A combustion engine fires every other revolution (strong half-orders) AND
        has cycle-to-cycle roughness, so it is never ultra-steady. A high half-order
        ratio on an ultra-steady high-Q tone is therefore an F0-estimation artifact
        (common on multirotors with several close rotor tones), not a real engine —
        so an ultra-steady source is classified electric regardless of half-orders.
        """

        very_steady = steadiness_cv < 0.015
        if very_steady:
            return "electric", 0.85

        combustion = 0.0
        if half_ratio > 0.25:
            combustion += 0.5
        if steadiness_cv > 0.05:
            combustion += 0.25
        if tonality > 0.2:
            combustion += 0.25
        if combustion >= 0.5:
            return "combustion", min(combustion, 1.0)
        if half_ratio < 0.2 and steadiness_cv < 0.03 and tonality < 0.15:
            electric = 0.6 + 0.4 * (1.0 - min(half_ratio / 0.2, 1.0))
            return "electric", min(electric, 1.0)
        return "unknown", 0.4

    @staticmethod
    def _construction_summary(
        blade_count: int,
        rotor_count: int,
        rotor_rpm: float,
        propulsion: str,
        fundamental: float,
    ) -> str:
        """Human-readable construction hint (clearly an estimate)."""

        prop_ru = {"electric": "электропривод", "combustion": "ДВС", "unknown": "тип привода неясен"}
        parts = [
            f"blade-pass {fundamental:.1f} Гц",
            f"~{rotor_rpm:.0f} об/мин",
            prop_ru.get(propulsion, propulsion),
        ]
        if blade_count >= 2:
            parts.append(f"~{blade_count} лопасти")
        if rotor_count >= 2:
            parts.append(f"~{rotor_count} ротора (мультиротор)")
        return "Оценка (предварительно): " + ", ".join(parts) + "."

    @staticmethod
    def _count_harmonics(freqs: np.ndarray, spec_db: np.ndarray, fundamental: float) -> int:
        """Count integer harmonics standing clearly above the local floor."""

        if fundamental <= 0:
            return 0
        floor = float(np.median(spec_db))
        bin_hz = float(freqs[1] - freqs[0]) if freqs.size > 1 else 1.0
        tol = max(1.5 * bin_hz, fundamental * 0.06)
        count = 0
        for k in range(1, settings.comb_max_harmonics + 1):
            target = fundamental * k
            if target > min(settings.separation_band_high_hz, float(freqs[-1])):
                break
            near = np.abs(freqs - target) <= tol
            if np.any(near) and float(np.max(spec_db[near])) >= floor + 6.0:
                count += 1
        return count

    @staticmethod
    def _dominant_harmonic(freqs: np.ndarray, spec_db: np.ndarray, fundamental: float) -> float:
        """Frequency of the strongest harmonic line."""

        if fundamental <= 0:
            return 0.0
        bin_hz = float(freqs[1] - freqs[0]) if freqs.size > 1 else 1.0
        tol = max(1.5 * bin_hz, fundamental * 0.06)
        best_hz = fundamental
        best_db = -np.inf
        for k in range(1, settings.comb_max_harmonics + 1):
            target = fundamental * k
            if target > min(settings.separation_band_high_hz, float(freqs[-1])):
                break
            near = np.abs(freqs - target) <= tol
            if np.any(near):
                local = float(np.max(spec_db[near]))
                if local > best_db:
                    best_db = local
                    best_hz = float(freqs[near][int(np.argmax(spec_db[near]))])
        return best_hz

    @staticmethod
    def _looks_like_mains(fundamental: float, steadiness_cv: float, order_ratio: float) -> bool:
        """Flag a stable 50/60 Hz line (mains or grid-locked genset) as hum."""

        for mains in (50.0, 60.0):
            if abs(fundamental - mains) <= 2.0 and steadiness_cv <= 0.02:
                return True
            # A near-mains fundamental with a pure integer-order comb is almost
            # certainly electrical, even if it drifts a little (small genset).
            if abs(fundamental - mains) <= 2.0 and order_ratio >= 0.95:
                return True
        return False

    @staticmethod
    def _separation_gain_db(isolated: np.ndarray, residual: np.ndarray) -> float:
        """Energy ratio of the isolated drone signal to the residual noise."""

        drone_power = float(np.mean(np.square(isolated))) if isolated.size else 0.0
        noise_power = float(np.mean(np.square(residual))) if residual.size else 0.0
        if drone_power <= 1e-20 or noise_power <= 1e-20:
            return 0.0
        return 10.0 * np.log10(drone_power / noise_power)

    @staticmethod
    def _confidence(
        present: bool,
        persistence: float,
        median_snr: float,
        steadiness_cv: float,
        harmonic_count: int,
        gain_db: float,
    ) -> float:
        """Blend detection evidence into a 0..1 confidence."""

        score = (
            0.40 * min(persistence / 0.6, 1.0)
            + 0.30 * min(max(median_snr, 0.0) / 15.0, 1.0)
            + 0.20 * (1.0 - min(steadiness_cv / 0.1, 1.0))
            + 0.10 * min(harmonic_count / 8.0, 1.0)
        )
        # Penalize when the isolated signal barely stands above the residual,
        # i.e. the "drone" we pulled out is mostly noise.
        if gain_db < 3.0:
            score *= 0.7
        score = float(np.clip(score, 0.0, 1.0))
        return score if present else min(score, 0.45)

    @staticmethod
    def _likely_source(present: bool, order_ratio: float, is_mains: bool) -> str:
        """Coarse identity hint from the harmonic-order structure."""

        if is_mains:
            return "возможно сетевая наводка 50/60 Гц"
        if not present:
            return "нет устойчивого источника"
        if order_ratio < 0.7:
            return "поршневой двигатель (трактор/ДВС)"
        return "роторный/винтовой источник (БПЛА или генератор)"

    @staticmethod
    def _explain(
        present: bool,
        fundamental: float,
        dominant_hz: float,
        persistence: float,
        median_snr: float,
        likely: str,
    ) -> str:
        """Human-readable summary of the separation result."""

        if not present:
            return (
                "Устойчивый гармонический источник под шумом не выделен "
                f"(персистентность {persistence:.0%}, SNR {median_snr:.1f} дБ)."
            )
        return (
            f"Выделен устойчивый источник: F0 ≈ {fundamental:.1f} Гц "
            f"(самая громкая линия {dominant_hz:.1f} Гц), присутствует в "
            f"{persistence:.0%} окон, гармонический SNR {median_snr:.1f} дБ. "
            f"Вероятно — {likely}."
        )

    @staticmethod
    def _fit_length(signal: np.ndarray, length: int) -> np.ndarray:
        """Trim or zero-pad an ISTFT result to a target length."""

        if len(signal) == length:
            return signal
        if len(signal) > length:
            return signal[:length]
        return np.pad(signal, (0, length - len(signal)))

    def _empty(
        self,
        sr_lo: int,
        spectrum: tuple[np.ndarray, np.ndarray] | None = None,
    ) -> DroneSeparation:
        """Return a no-detection result (signal too short or no comb found)."""

        findings = DroneSeparationFindings(sample_rate=int(sr_lo))
        if spectrum is not None:
            spec_f, spec_db = spectrum
            findings.spectrum_freq_hz = [round(float(v), 2) for v in spec_f]
            findings.spectrum_db = [round(float(v), 1) for v in spec_db]
            findings.explanation = "Гармоническая гребёнка не обнаружена."
        return DroneSeparation(
            findings=findings,
            isolated=np.zeros(0, dtype=np.float32),
            residual=np.zeros(0, dtype=np.float32),
            sample_rate=int(sr_lo),
        )
