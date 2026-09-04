from __future__ import annotations

import math

import numpy as np

from spatial.core import (
    default_geometry_3plus1,
    direction_to_pair_tdoa,
    estimate_direction_from_tdoa,
    gcc_phat_pair_tdoa,
)


def _angle_error_deg(a: float, b: float) -> float:
    d = (a - b + 180.0) % 360.0 - 180.0
    return abs(d)


def test_default_geometry_is_non_coplanar_and_centered() -> None:
    g = default_geometry_3plus1(0.12, 0.15)
    assert g.shape == (4, 3)
    assert np.linalg.matrix_rank(g[1:] - g[0]) == 3
    assert abs(float(np.mean(g[:3, 0]))) < 1e-12
    assert abs(float(np.mean(g[:3, 1]))) < 1e-12
    assert np.allclose(g[:3, 2], 0.0)
    assert math.isclose(float(g[3, 2]), 0.15, abs_tol=1e-12)


def test_ideal_tdoa_recovers_3d_direction() -> None:
    g = default_geometry_3plus1(0.12, 0.15)
    for azimuth, elevation in [(0.0, 10.0), (37.0, 25.0), (145.0, 55.0), (278.0, 18.0)]:
        tdoa = direction_to_pair_tdoa(g, azimuth, elevation, 343.0)
        est = estimate_direction_from_tdoa(g, tdoa, 343.0)
        assert est.valid, est.reason
        assert est.azimuth_deg is not None
        assert est.elevation_deg is not None
        assert _angle_error_deg(est.azimuth_deg, azimuth) < 1e-6
        assert abs(est.elevation_deg - elevation) < 1e-6
        assert est.residual_us < 1e-6
        assert abs(est.direction_norm - 1.0) < 1e-9


def test_small_tdoa_noise_remains_usable() -> None:
    rng = np.random.default_rng(7)
    g = default_geometry_3plus1(0.12, 0.15)
    truth_az = 215.0
    truth_el = 22.0
    tdoa = direction_to_pair_tdoa(g, truth_az, truth_el, 343.0)
    noisy = {pair: tau + float(rng.normal(0.0, 4e-6)) for pair, tau in tdoa.items()}
    est = estimate_direction_from_tdoa(g, noisy, 343.0, max_residual_us=40.0)
    assert est.valid, est.reason
    assert est.azimuth_deg is not None
    assert est.elevation_deg is not None
    assert _angle_error_deg(est.azimuth_deg, truth_az) < 5.0
    assert abs(est.elevation_deg - truth_el) < 5.0
    assert est.confidence > 0.2


def test_planar_geometry_is_rejected_for_full_3d() -> None:
    g = default_geometry_3plus1(0.12, 0.15)
    g[3, 2] = 0.0
    tdoa = direction_to_pair_tdoa(g, 80.0, 30.0, 343.0)
    est = estimate_direction_from_tdoa(g, tdoa, 343.0)
    assert not est.valid
    assert est.reason == "rank_deficient_geometry"


def test_physically_inconsistent_tdoa_is_rejected() -> None:
    g = default_geometry_3plus1(0.12, 0.15)
    tdoa = direction_to_pair_tdoa(g, 30.0, 20.0, 343.0)
    # Scale all delays far beyond the plane-wave unit-vector solution.
    impossible = {pair: tau * 2.0 for pair, tau in tdoa.items()}
    est = estimate_direction_from_tdoa(g, impossible, 343.0)
    assert not est.valid
    assert est.reason == "physically_inconsistent_tdoa"


def test_gcc_phat_pair_tdoa_sign_and_subsample_resolution() -> None:
    fs = 32000
    rng = np.random.default_rng(11)
    source = rng.normal(0.0, 1.0, 4096)
    # Channel j arrives 6 samples later than channel i.
    delay_samples = 6
    channel_i = source.copy()
    channel_j = np.concatenate((np.zeros(delay_samples), source[:-delay_samples]))
    tau = gcc_phat_pair_tdoa(
        channel_i,
        channel_j,
        fs,
        max_tau_s=0.001,
        band_hz=(80.0, 5000.0),
        interp=8,
    )
    assert abs(tau - delay_samples / fs) <= 1.0 / (fs * 8)
