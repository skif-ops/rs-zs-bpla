import math

import numpy as np

from spatial.gcc_phat import gcc_phat_delay_us
from spatial.geometry import (
    DEFAULT_GEOMETRY_3P1,
    direction_from_reference_tdoas_us,
    full_pair_tdoas_us,
    reference_tdoas_us_from_direction,
)


def _angle_error_deg(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def test_default_geometry_is_non_coplanar_and_compact():
    g = DEFAULT_GEOMETRY_3P1
    assert g.positions_m.shape == (4, 3)
    assert np.linalg.matrix_rank(g.positions_m[1:] - g.positions_m[0]) == 3
    assert 0.14 < g.max_baseline_m < 0.20


def test_direction_roundtrip_exact_tdoa():
    for azimuth, elevation in [(0.0, 15.0), (73.0, 32.0), (215.0, 55.0), (315.0, 8.0)]:
        t = reference_tdoas_us_from_direction(azimuth, elevation)
        s = direction_from_reference_tdoas_us(*t)
        assert s.valid
        assert _angle_error_deg(s.azimuth_deg, azimuth) < 1e-6
        assert abs(s.elevation_deg - elevation) < 1e-6
        assert s.residual_us < 1e-8
        assert s.confidence > 0.999


def test_integer_microsecond_quantization_is_still_usable():
    azimuth, elevation = 128.0, 28.0
    t = reference_tdoas_us_from_direction(azimuth, elevation)
    quantized = tuple(round(v) for v in t)
    s = direction_from_reference_tdoas_us(*quantized)
    assert s.valid
    assert _angle_error_deg(s.azimuth_deg, azimuth) < 1.0
    assert abs(s.elevation_deg - elevation) < 1.0
    assert s.residual_us < 2.0


def test_impossible_delay_is_rejected():
    s = direction_from_reference_tdoas_us(10000.0, 0.0, 0.0)
    assert not s.valid
    assert s.confidence == 0.0


def test_full_pair_delays_are_consistent():
    t12, t13, t14 = (10.0, -4.0, 25.0)
    p = full_pair_tdoas_us((t12, t13, t14))
    assert p["tdoa23_us"] == -14.0
    assert p["tdoa24_us"] == 15.0
    assert p["tdoa34_us"] == 29.0


def test_gcc_phat_delay_sign_and_accuracy():
    rng = np.random.default_rng(42)
    reference = rng.standard_normal(4096)
    delay_samples = 7
    other = np.concatenate((np.zeros(delay_samples), reference[:-delay_samples]))
    delay_us, quality = gcc_phat_delay_us(
        reference,
        other,
        sample_rate_hz=32000,
        max_tau_s=0.001,
        interp=16,
        fmin_hz=80.0,
        fmax_hz=5000.0,
    )
    expected_us = delay_samples / 32000.0 * 1e6
    assert abs(delay_us - expected_us) < 3.0
    assert quality > 5.0
