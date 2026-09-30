"""Bearing-stream fusion (ICD addendum H, decision 2 of docs/ZVOOK_COMPARISON_DECISIONS_2026-09-30.md): the live
bearings of two or more stations become the points of one target track.

For every emission time on a 1 s grid each station's bearing is taken at the moment the sound of that emission
reached it (emission time + range / speed of sound; the range comes from the previous iteration), interpolated
between its 0.5 s bearings.  The horizontal position is the weighted least-squares intersection of the rays, each
weighted by its lateral error (range x bearing sigma), so the error follows the geometry: it grows along the baseline
between two stations (the blind zone of triangulation) and such points are refused.  The height comes from the
elevations.  A constant-velocity Kalman filter smooths the points and gives speed and course.

Pure functions only: no storage, no association (station/track_fusion.py does both).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from fusion.geodesy import EnuFrame
from fusion.kalman import ConstantVelocityKalman3D

SPEED_OF_SOUND_MPS = 343.0
BIN_S = 1.0                  # one point a second (the dioneya.alert/1 track update rate)
MAX_SAMPLE_GAP_S = 1.2       # interpolate between bearings at most this far apart
MAX_NEAREST_S = 0.8          # otherwise take the nearest bearing only this close
MIN_SIGMA_DEG = 0.5
MAX_RANGE_M = 5000.0         # beyond the acoustic range of the array for the classes we track
MIN_CROSSING_DEG = 10.0      # rays closer to parallel than this do not intersect usefully
MAX_ERROR_M = 1000.0
ITERATIONS = 4


@dataclass
class StationBearings:
    """One station's bearings of one target (all its station tracks merged), times in seconds."""
    station_id: int
    lat: float
    lon: float
    alt_m: float
    time_s: np.ndarray
    azimuth_deg: np.ndarray
    elevation_deg: np.ndarray
    sigma_deg: np.ndarray

    @classmethod
    def from_rows(cls, station_id: int, position: tuple[float, float, float], rows: list[dict]) -> "StationBearings":
        rows = sorted(rows, key=lambda r: r["time_us"])
        return cls(station_id, position[0], position[1], position[2],
                   np.array([r["time_us"] * 1e-6 for r in rows], dtype=float),
                   np.array([r["azimuth_deg"] for r in rows], dtype=float),
                   np.array([r["elevation_deg"] for r in rows], dtype=float),
                   np.array([max(r["sigma_deg"], MIN_SIGMA_DEG) for r in rows], dtype=float))

    def sample(self, t: float) -> tuple[float, float, float] | None:
        """(azimuth, elevation, sigma) at arrival time t, or None when no bearing covers it."""
        ts = self.time_s
        if ts.size == 0:
            return None
        i = int(np.searchsorted(ts, t))
        if 0 < i < ts.size and ts[i] - ts[i - 1] <= MAX_SAMPLE_GAP_S:
            a, b = i - 1, i
            w = (t - ts[a]) / max(ts[b] - ts[a], 1e-9)
            daz = (self.azimuth_deg[b] - self.azimuth_deg[a] + 180.0) % 360.0 - 180.0
            az = (self.azimuth_deg[a] + w * daz) % 360.0
            el = self.elevation_deg[a] + w * (self.elevation_deg[b] - self.elevation_deg[a])
            return az, el, max(self.sigma_deg[a], self.sigma_deg[b])
        j = min(range(max(i - 1, 0), min(i + 1, ts.size)), key=lambda k: abs(ts[k] - t))
        if abs(ts[j] - t) > MAX_NEAREST_S:
            return None
        return float(self.azimuth_deg[j]), float(self.elevation_deg[j]), float(self.sigma_deg[j])


@dataclass(frozen=True)
class Fix:
    """One raw intersection in the local frame."""
    time_s: float
    xyz: np.ndarray
    horizontal_error_m: float
    vertical_error_m: float
    crossing_deg: float
    stations: tuple[int, ...]


@dataclass(frozen=True)
class TrackPoint:
    time_us: int
    lat: float
    lon: float
    alt_msl_m: float
    horizontal_error_m: float
    vertical_error_m: float
    vx_east_mps: float
    vy_north_mps: float
    vz_up_mps: float
    speed_mps: float
    course_deg: float
    crossing_deg: float
    stations: tuple[int, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {"time_us": self.time_us, "lat": self.lat, "lon": self.lon, "alt_msl_m": self.alt_msl_m,
                "horizontal_error_m": self.horizontal_error_m, "vertical_error_m": self.vertical_error_m,
                "vx_east_mps": self.vx_east_mps, "vy_north_mps": self.vy_north_mps, "vz_up_mps": self.vz_up_mps,
                "speed_mps": self.speed_mps, "course_deg": self.course_deg, "crossing_deg": self.crossing_deg,
                "stations": list(self.stations)}


def _direction(az_deg: float) -> np.ndarray:
    a = math.radians(az_deg)
    return np.array([math.sin(a), math.cos(a)])        # east, north


def intersect(origins: np.ndarray, azimuth_deg: list[float], elevation_deg: list[float], sigma_deg: list[float],
              ranges_m: list[float] | None) -> tuple[np.ndarray, np.ndarray, float] | None:
    """Weighted intersection of horizontal rays from ``origins`` (ENU, n x 3).  ``ranges_m`` from the previous
    iteration weight each ray by its lateral error (None: equal ranges).  Returns (xyz, 2x2 covariance, vertical
    sigma) or None for parallel rays."""
    n = len(azimuth_deg)
    a = np.zeros((n, 2))
    b = np.zeros(n)
    w = np.zeros(n)
    for i in range(n):
        d = _direction(azimuth_deg[i])
        normal = np.array([-d[1], d[0]])
        lateral = math.radians(sigma_deg[i]) * (ranges_m[i] if ranges_m else 1000.0)
        w[i] = 1.0 / max(lateral, 1.0) ** 2
        a[i] = normal
        b[i] = normal @ origins[i, :2]
    info = (a.T * w) @ a
    det = info[0, 0] * info[1, 1] - info[0, 1] * info[1, 0]
    if det <= 1e-12 * max(info[0, 0] * info[1, 1], 1e-300):
        return None
    cov = np.array([[info[1, 1], -info[0, 1]], [-info[1, 0], info[0, 0]]]) / det
    xy = cov @ ((a.T * w) @ b)
    zs, zw = [], []
    for i in range(n):
        rho = float(np.linalg.norm(xy - origins[i, :2]))
        el = math.radians(elevation_deg[i])
        if abs(elevation_deg[i]) >= 80.0:
            continue
        zs.append(origins[i, 2] + rho * math.tan(el))
        zw.append(1.0 / max(rho * math.radians(sigma_deg[i]) / math.cos(el) ** 2, 5.0) ** 2)
    if zs:
        z = float(np.average(zs, weights=zw))
        z_sigma = math.sqrt(1.0 / sum(zw))
    else:
        z = float(np.mean(origins[:, 2]))
        z_sigma = MAX_ERROR_M
    return np.array([xy[0], xy[1], z]), cov, z_sigma


def _crossing_deg(azimuth_deg: list[float]) -> float:
    best = 0.0
    for i in range(len(azimuth_deg)):
        for j in range(i + 1, len(azimuth_deg)):
            cos = abs(float(_direction(azimuth_deg[i]) @ _direction(azimuth_deg[j])))
            best = max(best, math.degrees(math.acos(min(cos, 1.0))))
    return best


def fix_at(t: float, stations: list[StationBearings], origins: np.ndarray, *, c: float = SPEED_OF_SOUND_MPS,
           ranges_hint: list[float] | None = None) -> Fix | None:
    """The target at emission time ``t``: every station's bearing at t + range/c, iterated on the range."""
    ranges = list(ranges_hint) if ranges_hint else None
    result = None
    used: list[int] = []
    for _ in range(ITERATIONS):
        az, el, sg, idx = [], [], [], []
        for k, sb in enumerate(stations):
            s = sb.sample(t + (ranges[k] / c if ranges else 0.0))
            if s is not None:
                az.append(s[0]); el.append(s[1]); sg.append(s[2]); idx.append(k)
        if len(idx) < 2:
            return None
        solved = intersect(origins[idx], az, el, sg, [ranges[k] for k in idx] if ranges else None)
        if solved is None:
            return None
        xyz, cov, z_sigma = solved
        new_ranges = [float(np.linalg.norm(xyz[:2] - origins[k, :2])) for k in range(len(stations))]
        converged = ranges is not None and max(abs(x - y) for x, y in zip(new_ranges, ranges)) < 2.0
        result, used = (xyz, cov, z_sigma, az), idx
        ranges = new_ranges
        if converged:
            break
    xyz, cov, z_sigma, az = result
    for k, a in zip(used, az):                       # the target must lie ahead of every ray, within range
        ahead = float((xyz[:2] - origins[k, :2]) @ _direction(a))
        if ahead <= 0.0 or ranges[k] > MAX_RANGE_M:
            return None
    crossing = _crossing_deg(az)
    h_err = math.sqrt(max(float(np.trace(cov)), 0.0))
    if crossing < MIN_CROSSING_DEG or h_err > MAX_ERROR_M:
        return None
    return Fix(t, xyz, h_err, max(z_sigma, 10.0), crossing, tuple(stations[k].station_id for k in used))


def fuse(stations: list[StationBearings], *, bin_s: float = BIN_S, c: float = SPEED_OF_SOUND_MPS,
         smooth: bool = True) -> list[TrackPoint]:
    """Track points on a ``bin_s`` grid of emission times where at least two stations see the target."""
    stations = [s for s in stations if s.time_s.size]
    if len({s.station_id for s in stations}) < 2:
        return []
    frame = EnuFrame(float(np.mean([s.lat for s in stations])), float(np.mean([s.lon for s in stations])),
                     float(np.mean([s.alt_m for s in stations])))
    origins = np.array([frame.to_enu(s.lat, s.lon, s.alt_m) for s in stations])
    t_first = min(float(s.time_s[0]) for s in stations)
    t_last = max(float(s.time_s[-1]) for s in stations)
    fixes: list[Fix] = []
    hint = None
    t = math.floor((t_first - MAX_RANGE_M / c) / bin_s) * bin_s
    while t <= t_last:
        f = fix_at(t, stations, origins, c=c, ranges_hint=hint)
        if f is None and hint is not None:
            f = fix_at(t, stations, origins, c=c)
        if f is not None:
            fixes.append(f)
            hint = [float(np.linalg.norm(f.xyz[:2] - o[:2])) for o in origins]
        t += bin_s
    points = []
    kalman = ConstantVelocityKalman3D(process_accel_sigma=6.0)
    for f in fixes:
        if smooth:
            state = kalman.update(f.xyz, f.time_s, f.horizontal_error_m)
            xyz, vel = state[:3], state[3:]
            h_err = min(f.horizontal_error_m, math.sqrt(max(float(kalman.p[0, 0] + kalman.p[1, 1]), 0.0)))
        else:
            xyz, vel, h_err = f.xyz, np.zeros(3), f.horizontal_error_m
        lat, lon, alt = frame.to_geodetic(*xyz)
        speed = float(math.hypot(vel[0], vel[1]))
        course = (math.degrees(math.atan2(vel[0], vel[1])) + 360.0) % 360.0 if speed > 0.5 else 0.0
        points.append(TrackPoint(int(round(f.time_s * 1e6)), lat, lon, alt, round(h_err, 1), round(f.vertical_error_m, 1),
                                 float(vel[0]), float(vel[1]), float(vel[2]), speed, course, round(f.crossing_deg, 1),
                                 f.stations))
    return points
