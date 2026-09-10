from app import app
from config import settings


def test_evt_pre_20_runtime_identity() -> None:
    assert settings.app_version == "1.2.0-evt-pre-20.1"
    assert app.version == settings.app_version
    assert "evt" + "-mb" not in app.version.lower()
