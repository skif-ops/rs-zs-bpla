"""What a station heard in one tracking window: class and fundamental frequency (decision 7, work item 4 of
docs/ZVOOK_COMPARISON_DECISIONS_2026-09-30.md, dioneya.alert/1).

A station track (station + the event id of its rising edge) has the rising-edge detection and, every few seconds,
keep-alive detections of the same window.  Their classification and fundamental frequency (feature 0 of the 43,
``fundamental_hz``) describe the target the station tracks.  Two station tracks whose known classes differ, or whose
fundamentals are further apart than the Doppler shift between two stations allows, hear different targets: their
rays are not intersected (station/track_fusion.py), and the output API reports the class of a track from them.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from station.schemas import DetectionMessage, TargetClass

KEEPALIVE_MARGIN_US = 2_000_000     # keep-alive detections of the window: within its bearings' time span (+- 2 s)
# Two stations may hear the same engine Doppler-shifted in opposite senses: (c + v) / (c - v) = 1.43 at v = 60 m/s
# (fast piston UAV).  An octave slip of the f0 estimate is not folded back: a missed fusion only leaves bearing lines,
# a ghost fusion would report a target where there is none.
F0_RATIO_MAX = 1.45
F0_MIN_HZ = 20.0

EXTERNAL_CLASS = {
    int(TargetClass.PISTON_UAV): "uav_piston",
    int(TargetClass.REACTIVE_UAV): "uav_jet",
    int(TargetClass.ELECTRIC_UAV): "uav_electric",
    int(TargetClass.AIRCRAFT): "aircraft",
    int(TargetClass.HELICOPTER): "helicopter",
}


@dataclass(frozen=True)
class Signature:
    class_id: int
    label: str
    unknown: bool
    confidence: float
    type_label: str | None
    f0_hz: float | None

    @property
    def code(self) -> str:
        if self.unknown:
            return "unknown"
        return EXTERNAL_CLASS.get(self.class_id, "other")

    def as_class(self) -> dict:
        """The ``class`` object of dioneya.alert/1."""
        return {"code": self.code, "label": self.label, "confidence": round(self.confidence, 3),
                "type": self.type_label, "f0_hz": None if self.f0_hz is None else round(self.f0_hz, 1)}


UNKNOWN = Signature(int(TargetClass.UNKNOWN), "UNKNOWN", True, 0.0, None, None)


def _f0(d: DetectionMessage) -> float | None:
    if d.features and d.features[0] >= F0_MIN_HZ:
        return float(d.features[0])
    return None


def from_detections(detections: list[DetectionMessage]) -> Signature:
    """The class of the most confident known classification (else the most confident one), the median fundamental."""
    if not detections:
        return UNKNOWN
    known = [d for d in detections if not d.classification.unknown]
    best = max(known or detections, key=lambda d: d.classification.confidence)
    typed = [d for d in detections if d.hierarchy.type_status in ("PROVISIONAL", "STABLE") and d.hierarchy.type_id]
    type_label = max(typed, key=lambda d: d.hierarchy.type_confidence).hierarchy.type_label if typed else None
    f0s = [f for f in (_f0(d) for d in detections) if f is not None]
    f0 = median(f0s) if f0s else None
    return Signature(best.classification.class_id, best.classification.label, best.classification.unknown,
                     best.classification.confidence, type_label, f0)


def station_track_signature(store, station_id: int, track_event_id: int) -> Signature:
    """Signature of a station track: its rising-edge detection and the keep-alive detections of the window."""
    detections = []
    rising = store.get_detection(station_id, track_event_id)
    if rising is not None:
        detections.append(rising)
    span = store.bearing_span(station_id, track_event_id)
    if span is not None:
        seen = {d.event_id for d in detections}
        for d in store.station_detections(station_id, span[0] - KEEPALIVE_MARGIN_US, span[1] + KEEPALIVE_MARGIN_US):
            if d.event_id not in seen:
                detections.append(d)
    return from_detections(detections)


def compatible(a: Signature, b: Signature) -> bool:
    """False only when the two stations evidently hear different targets."""
    if not a.unknown and not b.unknown and a.class_id != b.class_id:
        return False
    if a.f0_hz is not None and b.f0_hz is not None:
        if max(a.f0_hz, b.f0_hz) / min(a.f0_hz, b.f0_hz) > F0_RATIO_MAX:
            return False
    return True


def merge(signatures: list[Signature]) -> Signature:
    """The class of a fused track from its members: the most confident known one, the median fundamental."""
    if not signatures:
        return UNKNOWN
    known = [s for s in signatures if not s.unknown]
    best = max(known or signatures, key=lambda s: s.confidence)
    types = [s.type_label for s in signatures if s.type_label]
    f0s = [s.f0_hz for s in signatures if s.f0_hz is not None]
    return Signature(best.class_id, best.label, best.unknown, best.confidence, types[0] if types else None,
                     median(f0s) if f0s else None)
