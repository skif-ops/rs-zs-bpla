"""Station classifier model as a signed package (MQTT_TLS_ICD_v0_1 addendum I, firmware/include/zs_model.h).

A retrained nearest-centroid model reaches the stations without a firmware release: the package is signed offline
with the firmware release key (``python -m pki.cli model-sign``, manifest target 3) and delivered with the same
CMD_UPDATE_FIRMWARE command and fwreq/fw chunks as an image (addendum F).  The station writes it into the free slot
of its model store and loads it after the OK ACK, without a reset.

Package "DIOM" format 1, little-endian:
  0 magic u32 | 4 format u16 = 1 | 6 feature_count u16 = 43 | 8 class_count u16 | 10 reserved u16 = 0
  12 version u32 >= 1 | 16 feature_set u32 | 20 reserved 12 bytes = 0
  32 mean f32[43] | std f32[43] | class_id u8[n] padded with zeros to 4 | radius f32[n] | centroid f32[n][43]
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import struct

import numpy as np

from station import firmware_codec as fw

MAGIC = 0x4D4F4944                     # "DIOM" little-endian
FORMAT = 1
FEATURE_SET = 1                        # the 43 features of zs_dsp (server/tools/golden/feature_order.txt)
FEATURE_COUNT = 43
HEADER_BYTES = 32
MAX_CLASSES = 96
TARGET_MODEL = fw.TARGET_MODEL
KNOWN_CLASSES = frozenset({1, 2, 3, *range(10, 19)})
CAPACITY_BYTES = 60 * 1024             # package area of one NOR model slot (15 blocks of 4 KiB)


def package_bytes(class_count: int) -> int:
    return HEADER_BYTES + 2 * 4 * FEATURE_COUNT + ((class_count + 3) & ~3) + 4 * class_count + 4 * FEATURE_COUNT * class_count


MIN_BYTES = package_bytes(1)
MAX_BYTES = package_bytes(MAX_CLASSES)


@dataclass(frozen=True)
class ModelPackage:
    version: int
    feature_set: int
    mean: np.ndarray                   # float32[43]
    std: np.ndarray                    # float32[43]
    class_id: np.ndarray               # uint8[n]
    radius: np.ndarray                 # float32[n]
    centroids: np.ndarray              # float32[n][43]

    @property
    def class_count(self) -> int:
        return len(self.class_id)

    def as_model(self) -> dict:
        """The dict of server/tools/export_station_model.py (float64), for its predict()."""
        return {"mean": self.mean.astype(np.float64), "std": self.std.astype(np.float64),
                "centroids": self.centroids.astype(np.float64), "class_id": self.class_id.astype(np.int64),
                "radius": self.radius.astype(np.float64), "label": []}

    def describe(self) -> str:
        """Heartbeat model text (key 9) of a station running this package."""
        return f"m{self.version}"


def _floats(values, count: int, name: str, *, positive: bool = False, non_negative: bool = False) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64).reshape(-1)
    if arr.size != count:
        raise ValueError(f"{name} must carry {count} values")
    out = arr.astype("<f4")
    for v in out:
        if not math.isfinite(float(v)) or (positive and not v > 0) or (non_negative and v < 0):
            raise ValueError(f"{name} holds an invalid value")
    return out


def encode_model(model: dict, version: int, feature_set: int = FEATURE_SET) -> bytes:
    """Package of a model dict {mean, std, centroids, class_id, radius} (export_station_model.fit / parse_header)."""
    fw._uint32(version, "version", 1)
    fw._uint32(feature_set, "feature_set", 1)
    class_id = [int(v) for v in np.asarray(model["class_id"]).reshape(-1)]
    n = len(class_id)
    if not 1 <= n <= MAX_CLASSES:
        raise ValueError(f"class count must be 1..{MAX_CLASSES}")
    if any(c not in KNOWN_CLASSES for c in class_id):
        raise ValueError("unknown class id in the model")
    mean = _floats(model["mean"], FEATURE_COUNT, "mean")
    std = _floats(model["std"], FEATURE_COUNT, "std", non_negative=True)
    radius = _floats(model["radius"], n, "radius", positive=True)
    centroids = _floats(model["centroids"], n * FEATURE_COUNT, "centroids")
    out = bytearray(struct.pack("<IHHHHII12x", MAGIC, FORMAT, FEATURE_COUNT, n, 0, version, feature_set))
    out += mean.tobytes() + std.tobytes()
    out += bytes(class_id) + bytes(((n + 3) & ~3) - n)
    out += radius.tobytes() + centroids.tobytes()
    assert len(out) == package_bytes(n)
    return bytes(out)


def parse_model(raw: bytes) -> ModelPackage:
    """The station's zs_model_load: every check that makes it refuse a package (FAILED 3 after the download)."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) < HEADER_BYTES:
        raise ValueError("model package is too short")
    raw = bytes(raw)
    magic, fmt, features, n, reserved, version, feature_set = struct.unpack_from("<IHHHHII", raw, 0)
    if magic != MAGIC or fmt != FORMAT or features != FEATURE_COUNT or reserved != 0 or version == 0 or any(raw[20:32]):
        raise ValueError("not a model package of format 1")
    if feature_set != FEATURE_SET:
        raise ValueError(f"model is for feature set {feature_set}, stations run {FEATURE_SET}")
    if not 1 <= n <= MAX_CLASSES or len(raw) != package_bytes(n):
        raise ValueError("model package size does not match its class count")
    off = HEADER_BYTES
    mean = np.frombuffer(raw, "<f4", FEATURE_COUNT, off); off += 4 * FEATURE_COUNT
    std = np.frombuffer(raw, "<f4", FEATURE_COUNT, off); off += 4 * FEATURE_COUNT
    padded = (n + 3) & ~3
    ids = np.frombuffer(raw, np.uint8, padded, off); off += padded
    radius = np.frombuffer(raw, "<f4", n, off); off += 4 * n
    centroids = np.frombuffer(raw, "<f4", n * FEATURE_COUNT, off).reshape(n, FEATURE_COUNT)
    if not (np.isfinite(mean).all() and np.isfinite(std).all() and np.isfinite(radius).all() and np.isfinite(centroids).all()):
        raise ValueError("model package holds a non-finite number")
    if (std < 0).any() or not (radius > 0).all():
        raise ValueError("model package holds a negative std or a non-positive radius")
    if any(int(c) not in KNOWN_CLASSES for c in ids[:n]) or any(ids[n:]):
        raise ValueError("model package holds an unknown class id")
    return ModelPackage(version, feature_set, mean.copy(), std.copy(), ids[:n].copy(), radius.copy(), centroids.copy())


def manifest_for_model(raw: bytes) -> fw.Manifest:
    package = parse_model(raw)
    if len(raw) > CAPACITY_BYTES:
        raise ValueError("model package exceeds the station slot")
    return fw.Manifest(target=TARGET_MODEL, version=package.version, size=len(raw), sha256=hashlib.sha256(raw).digest())


class ModelRepository(fw.ReleaseRepository):
    """Signed model packages, laid out like firmware releases (``<version>.bin`` is the package)."""

    manifest_for = staticmethod(manifest_for_model)

    def get(self, version: int) -> fw.Release | None:
        release = super().get(version)
        if release is not None and release.manifest.target != TARGET_MODEL:
            raise ValueError(f"model release {version} is not a model manifest")
        return release
