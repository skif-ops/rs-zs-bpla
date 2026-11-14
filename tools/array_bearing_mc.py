"""Monte Carlo (tools/array_bearing_mc.py): bearing accuracy of the Dioneya 3+1 array with the firmware GCC-PHAT + closed-form solver.

Plane wave from a piston UAV (harmonic series, f0 ~ 110 Hz, blade-pass comb, level falling with frequency),
independent sensor noise per microphone at a given band SNR, optional wind noise (uncorrelated, 1/f^2 below
~300 Hz).  The array is scaled: 1x = locked geometry (triangle 120 mm, MIC4 +150 mm), 2x, 4x (ZVOOK-like
aperture ~0.5 m).  One estimate = one 1024-sample frame (32 ms) or the median of N frame TDOAs.
"""
import ctypes, math, os, subprocess, sys, tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def _build_library() -> str:
    """Compile the firmware's zs_spatial + zs_fft into a shared library (the exact on-board solver)."""
    out = Path(tempfile.gettempdir()) / "zs_spatial_mc.so"
    fw = ROOT / "firmware"
    subprocess.check_call(["cc", "-O2", "-shared", "-fPIC", f"-I{fw / 'include'}", str(fw / "src" / "zs_spatial.c"),
                           str(fw / "src" / "zs_fft.c"), "-o", str(out), "-lm"])
    return str(out)


lib = ctypes.CDLL(os.environ.get("ZS_SPATIAL_LIB") or _build_library())
F = ctypes.c_float


class Geo(ctypes.Structure):
    _fields_ = [("pos", (F * 3) * 4), ("gid", ctypes.c_uint8)]


class Sol(ctypes.Structure):
    _fields_ = [("az", F), ("el", F), ("res", F), ("conf", F), ("norm", F), ("valid", ctypes.c_bool)]


class Cpx(ctypes.Structure):
    _fields_ = [("re", F), ("im", F)]


class WS(ctypes.Structure):
    _fields_ = [("sig", Cpx * 1024), ("ref", Cpx * 1024)]


lib.zs_spatial_geometry_3p1_default.argtypes = [ctypes.POINTER(Geo)]
lib.zs_spatial_gcc_phat_delay_us.restype = ctypes.c_bool
lib.zs_spatial_gcc_phat_delay_us.argtypes = [ctypes.POINTER(ctypes.c_int16), ctypes.POINTER(ctypes.c_int16), ctypes.c_size_t,
                                             ctypes.c_uint32, F, F, F, ctypes.POINTER(WS), ctypes.POINTER(F), ctypes.POINTER(F)]
lib.zs_spatial_direction_from_reference_tdoas.restype = ctypes.c_bool
lib.zs_spatial_direction_from_reference_tdoas.argtypes = [ctypes.POINTER(Geo), ctypes.POINTER(F * 3), F, ctypes.POINTER(Sol)]
lib.zs_spatial_max_baseline_m.restype = F
lib.zs_spatial_max_baseline_m.argtypes = [ctypes.POINTER(Geo)]

FS = 32000
N = 1024
C = 331.3 + 0.606 * 15.0
ws = WS()


def geometry(scale):
    g = Geo()
    lib.zs_spatial_geometry_3p1_default(ctypes.byref(g))
    for i in range(4):
        for k in range(3):
            g.pos[i][k] *= scale
    return g


def positions(g):
    return np.array([[g.pos[i][k] for k in range(3)] for i in range(4)])


def unit(az, el):
    a, e = math.radians(az), math.radians(el)
    return np.array([math.cos(e) * math.sin(a), math.cos(e) * math.cos(a), math.sin(e)])


def source(nsamp, rng, f0=110.0):
    """complex spectrum of a piston UAV: harmonics k*f0 up to 2.5 kHz, -4 dB/harmonic-octave, jittered f0."""
    t = np.arange(nsamp) / FS
    f0 = f0 * (1 + 0.01 * rng.standard_normal())
    s = np.zeros(nsamp)
    for k in range(1, int(2500 / f0)):
        s += (k ** -0.7) * np.cos(2 * np.pi * k * f0 * t + rng.uniform(0, 2 * np.pi))
    return s


def delay(x, tau):
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / FS)
    return np.fft.irfft(X * np.exp(-2j * np.pi * f * tau), len(x))


def wind(nsamp, rng):
    w = rng.standard_normal(nsamp)
    W = np.fft.rfft(w)
    f = np.fft.rfftfreq(nsamp, 1 / FS)
    W *= 1.0 / (1 + (f / 60.0) ** 2)          # strong below ~60 Hz, -40 dB/dec above
    return np.fft.irfft(W, nsamp)


def frame(g, az, el, snr_db, wind_db, rng, pad=4096):
    P = positions(g)
    u = unit(az, el)
    s = source(pad, rng)
    sig_pow = np.var(s)
    out = []
    for i in range(4):
        tau = -(P[i] @ u) / C                  # arrival earlier for mics toward the source
        x = delay(s, tau)
        x += rng.standard_normal(pad) * math.sqrt(sig_pow / 10 ** (snr_db / 10))
        if wind_db is not None:
            wv = wind(pad, rng)
            x += wv * math.sqrt(sig_pow / 10 ** (-wind_db / 10) / np.var(wv))
        out.append(x[pad // 2 - N // 2: pad // 2 + N // 2])
    m = max(np.abs(np.array(out)).max(), 1e-9)
    return [np.round(o / m * 20000).astype(np.int16) for o in out]


def tdoas(g, chans, fmin, fmax):
    maxd = lib.zs_spatial_max_baseline_m(ctypes.byref(g)) / C * 1e6 + 5
    ref = chans[0].ctypes.data_as(ctypes.POINTER(ctypes.c_int16))
    t = []
    for i in range(1, 4):
        d, q = F(), F()
        ok = lib.zs_spatial_gcc_phat_delay_us(ref, chans[i].ctypes.data_as(ctypes.POINTER(ctypes.c_int16)), N, FS, maxd,
                                              fmin, fmax, ctypes.byref(ws), ctypes.byref(d), ctypes.byref(q))
        t.append(d.value if ok else float("nan"))
    return t


def solve(g, t):
    arr = (F * 3)(*t)
    s = Sol()
    lib.zs_spatial_direction_from_reference_tdoas(ctypes.byref(g), ctypes.byref(arr), 15.0, ctypes.byref(s))
    return s


def angdiff(a, b):
    return (a - b + 180) % 360 - 180


def run(scale, snr_db, nframes=1, wind_db=None, fmin=80.0, fmax=3000.0, trials=150, seed=1):
    rng = np.random.default_rng(seed)
    g = geometry(scale)
    eaz, eel, fails = [], [], 0
    for _ in range(trials):
        az, el = rng.uniform(0, 360), rng.uniform(5, 45)
        ts = np.array([tdoas(g, frame(g, az, el, snr_db, wind_db, rng), fmin, fmax) for _ in range(nframes)])
        t = np.nanmedian(ts, axis=0)
        s = solve(g, list(t))
        if not s.valid:
            fails += 1
            continue
        eaz.append(abs(angdiff(s.az, az)))
        eel.append(abs(s.el - el))
    if not eaz:
        return float("nan"), float("nan"), float("nan"), fails / trials
    eaz = np.array(eaz)
    return np.median(eaz), np.percentile(eaz, 90), np.median(eel), fails / trials


if __name__ == "__main__":
    print("scale baseline_m snr_dB frames wind | az_med az_p90 el_med invalid")
    for scale in (1, 2, 4):
        g = geometry(scale)
        for snr in (0, -6, -12):
            for nf in (1, 16):
                r = run(scale, snr, nf, trials=80 if nf == 16 else 150)
                print(f"{scale}x {lib.zs_spatial_max_baseline_m(ctypes.byref(g)):.3f} {snr:4d} {nf:3d}  -   | "
                      f"{r[0]:6.1f} {r[1]:6.1f} {r[2]:6.1f} {r[3]:.2f}", flush=True)
    for scale in (1, 4):
        for wdb in (0, 10):
            r = run(scale, 0, 16, wind_db=wdb, trials=80)
            print(f"{scale}x wind+{wdb}dB snr0 16fr | {r[0]:6.1f} {r[1]:6.1f} {r[2]:6.1f} {r[3]:.2f}", flush=True)
            r = run(scale, 0, 16, wind_db=wdb, fmin=250.0, trials=80)
            print(f"{scale}x wind+{wdb}dB snr0 16fr fmin250 | {r[0]:6.1f} {r[1]:6.1f} {r[2]:6.1f} {r[3]:.2f}", flush=True)
