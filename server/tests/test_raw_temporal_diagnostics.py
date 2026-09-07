from __future__ import annotations
import numpy as np
from ml.raw_temporal_diagnostics import RAW_DIAGNOSTIC_COLUMNS, raw_temporal_diagnostics


def test_raw_diagnostics_are_gain_invariant():
    sr=32000
    t=np.arange(sr*4,dtype=float)/sr
    x=(0.5+0.2*np.sin(2*np.pi*2*t))*np.sin(2*np.pi*120*t) + 0.1*np.sin(2*np.pi*4800*t)
    a=raw_temporal_diagnostics(x,sr)
    b=raw_temporal_diagnostics(x*0.17,sr)
    for name in RAW_DIAGNOSTIC_COLUMNS:
        assert np.isfinite(a[name]) and np.isfinite(b[name])
        assert abs(a[name]-b[name]) <= max(1e-5, abs(a[name])*1e-4)


def test_raw_diagnostics_resolve_one_to_three_hz_envelope():
    sr=32000
    t=np.arange(sr*5,dtype=float)/sr
    x=(1.0+0.7*np.sin(2*np.pi*2*t))*np.sin(2*np.pi*120*t)
    d=raw_temporal_diagnostics(x,sr)
    assert d["raw_envmod_1_3_ratio"] > d["raw_envmod_3_8_ratio"]
