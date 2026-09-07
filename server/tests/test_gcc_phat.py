import numpy as np

from localization.gcc_phat import GccPhatEstimator


def test_gcc_phat_recovers_integer_delay():
    sample_rate = 48_000
    delay_samples = 24
    rng = np.random.default_rng(42)
    reference = rng.normal(0.0, 1.0, sample_rate // 4)
    signal = np.concatenate([np.zeros(delay_samples), reference[:-delay_samples]])

    result = GccPhatEstimator(interp=8).estimate(
        reference=reference,
        signal=signal,
        sample_rate=sample_rate,
        max_tau=0.01,
    )

    assert abs(abs(result.delay_seconds) - delay_samples / sample_rate) <= 1 / sample_rate
    assert result.confidence > 0.5

