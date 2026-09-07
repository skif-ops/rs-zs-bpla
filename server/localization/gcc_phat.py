"""GCC-PHAT delay estimation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class GccPhatResult:
    """Estimated delay and confidence."""

    delay_seconds: float
    confidence: float
    peak_value: float


class GccPhatEstimator:
    """Estimate TDOA between two signals with GCC-PHAT."""

    def __init__(self, interp: int = 16) -> None:
        self.interp = max(1, int(interp))

    def estimate(
        self,
        reference: np.ndarray,
        signal: np.ndarray,
        sample_rate: int,
        max_tau: float | None = None,
    ) -> GccPhatResult:
        """Estimate delay of signal relative to reference."""

        ref = np.asarray(reference, dtype=np.float64)
        sig = np.asarray(signal, dtype=np.float64)
        n = min(len(ref), len(sig))
        if n < 8 or sample_rate <= 0:
            return GccPhatResult(0.0, 0.0, 0.0)

        ref = ref[:n]
        sig = sig[:n]
        if float(np.linalg.norm(ref)) < 1e-10 or float(np.linalg.norm(sig)) < 1e-10:
            return GccPhatResult(0.0, 0.0, 0.0)

        nfft = 1 << int(np.ceil(np.log2(n * 2 - 1)))
        ref_fft = np.fft.rfft(ref, n=nfft)
        sig_fft = np.fft.rfft(sig, n=nfft)
        cross_power = sig_fft * np.conj(ref_fft)
        cross_power /= np.abs(cross_power) + 1e-15
        cc = np.fft.irfft(cross_power, n=nfft * self.interp)

        max_shift = int(self.interp * nfft / 2)
        if max_tau is not None:
            max_shift = min(max_shift, int(self.interp * sample_rate * max_tau))
        cc = np.concatenate((cc[-max_shift:], cc[: max_shift + 1]))

        abs_cc = np.abs(cc)
        peak_index = int(np.argmax(abs_cc))
        shift = peak_index - max_shift
        delay = shift / float(self.interp * sample_rate)
        peak = float(abs_cc[peak_index])
        background = float(np.median(abs_cc) + 1e-12)
        confidence = float(np.clip(peak / (peak + 6.0 * background), 0.0, 1.0))
        return GccPhatResult(
            delay_seconds=float(delay),
            confidence=confidence,
            peak_value=peak,
        )

