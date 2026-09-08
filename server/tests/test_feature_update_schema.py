import pytest
from pydantic import ValidationError

from station.schemas import FeatureUpdateMessage, OnlineTypeStatusMessage


def test_feature_update_requires_exactly_43_features():
    valid = FeatureUpdateMessage(
        station_id=1,
        seq_no=2,
        boot_id=3,
        event_id=4,
        event_time_us=5,
        features=[0.0] * 43,
        detector_profile="piston",
    )
    assert len(valid.features) == 43

    with pytest.raises(ValidationError):
        FeatureUpdateMessage(
            station_id=1,
            seq_no=2,
            event_id=4,
            event_time_us=5,
            features=[0.0] * 42,
        )


def test_online_type_status_has_fail_safe_defaults():
    status = OnlineTypeStatusMessage(station_id=1, event_id=4)
    assert status.best_label == "UNKNOWN"
    assert status.status == "unknown"
    assert status.type_lock_allowed is False
    assert status.confidence == 0.0

