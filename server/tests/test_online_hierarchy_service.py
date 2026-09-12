from models.schemas import FamilyClassificationResult, OnlineTypeReplay, OnlineTypeSnapshot
from station.online_type_service import OnlineTypeSessionService
from station.schemas import FeatureUpdateMessage


class _FamilyClassifier:
    def __init__(self):
        self.window_counts: list[int] = []

    def predict_rows(self, rows, *, air_target_confirmed=False):
        count = len(rows)
        self.window_counts.append(count)
        return FamilyClassificationResult(
            best_family="PROP_PISTON" if count >= 4 else "UNKNOWN",
            confidence=0.8 if count >= 4 else 0.0,
            margin=0.4 if count >= 4 else 0.0,
            status="provisional_family" if count >= 4 else "warming_up",
            conditional_on_air_target=air_target_confirmed,
            evidence_windows=count,
            model_version="family-test",
        )


class _TypeClassifier:
    @staticmethod
    def load():
        return {"version": "type-test"}

    @staticmethod
    def replay(frame, **_kwargs):
        return OnlineTypeReplay(
            source_file="live",
            snapshots=[OnlineTypeSnapshot(time_seconds=4.0, phase="early_type")],
        )


def _message(seq_no: int) -> FeatureUpdateMessage:
    return FeatureUpdateMessage(
        station_id=7,
        seq_no=seq_no,
        boot_id=11,
        event_id=70,
        event_time_us=1_000_000 + (seq_no - 1) * 1_000_000,
        features=[0.0] * 43,
        air_target_confirmed=True,
    )


def test_live_hierarchy_requires_four_unique_windows_and_preserves_family():
    family = _FamilyClassifier()
    service = OnlineTypeSessionService(classifier=_TypeClassifier(), family_classifier=family)
    for seq_no in range(1, 4):
        status = service.ingest(_message(seq_no))
        assert status.status == "warming_up"
        assert status.hierarchical_label == "UNKNOWN"

    status = service.ingest(_message(4))
    assert status.evidence_windows == 4
    assert status.family_label == "PROP_PISTON"
    assert status.best_label == "UNKNOWN"
    assert status.hierarchical_label == "UNKNOWN_PROP_PISTON_UAV"
    assert status.family_conditional_on_air_target is True

    duplicate = service.ingest(_message(4))
    assert duplicate.evidence_windows == 4


def test_live_hierarchy_caps_consensus_at_latest_eight_windows():
    family = _FamilyClassifier()
    service = OnlineTypeSessionService(classifier=_TypeClassifier(), family_classifier=family)
    for seq_no in range(1, 11):
        status = service.ingest(_message(seq_no))
    assert status.evidence_windows == 8
    assert family.window_counts[-1] == 8
