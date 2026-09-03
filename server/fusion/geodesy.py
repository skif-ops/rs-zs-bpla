"""Small WGS84 <-> local ENU helpers without external GIS dependencies."""
from __future__ import annotations
import math
import numpy as np

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_E2 = WGS84_F * (2.0 - WGS84_F)

def geodetic_to_ecef(lat_deg: float, lon_deg: float, alt_m: float) -> np.ndarray:
    lat = math.radians(lat_deg); lon = math.radians(lon_deg)
    s = math.sin(lat); c = math.cos(lat)
    n = WGS84_A / math.sqrt(1.0 - WGS84_E2 * s * s)
    return np.array([(n+alt_m)*c*math.cos(lon), (n+alt_m)*c*math.sin(lon), (n*(1-WGS84_E2)+alt_m)*s], dtype=float)

def ecef_to_geodetic(x: float, y: float, z: float) -> tuple[float,float,float]:
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1.0 - WGS84_E2))
    for _ in range(8):
        s = math.sin(lat)
        n = WGS84_A / math.sqrt(1.0 - WGS84_E2*s*s)
        alt = p / max(math.cos(lat), 1e-12) - n
        lat = math.atan2(z, p * (1.0 - WGS84_E2*n/(n+alt)))
    s = math.sin(lat); n = WGS84_A / math.sqrt(1.0 - WGS84_E2*s*s)
    alt = p / max(math.cos(lat),1e-12) - n
    return math.degrees(lat), math.degrees(lon), float(alt)

class EnuFrame:
    def __init__(self, lat0: float, lon0: float, alt0: float):
        self.lat0=lat0; self.lon0=lon0; self.alt0=alt0
        self.ecef0=geodetic_to_ecef(lat0,lon0,alt0)
        lat=math.radians(lat0); lon=math.radians(lon0)
        self.r = np.array([
            [-math.sin(lon), math.cos(lon), 0.0],
            [-math.sin(lat)*math.cos(lon), -math.sin(lat)*math.sin(lon), math.cos(lat)],
            [ math.cos(lat)*math.cos(lon),  math.cos(lat)*math.sin(lon), math.sin(lat)],
        ])
    def to_enu(self, lat: float, lon: float, alt: float) -> np.ndarray:
        return self.r @ (geodetic_to_ecef(lat,lon,alt)-self.ecef0)
    def to_geodetic(self, e: float, n: float, u: float) -> tuple[float,float,float]:
        ecef=self.ecef0 + self.r.T @ np.array([e,n,u],dtype=float)
        return ecef_to_geodetic(*ecef)
