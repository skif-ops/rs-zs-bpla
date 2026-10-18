from app import app
from config import settings


def test_evt_pre_20_runtime_identity() -> None:
    assert settings.app_version == "1.3.0-evt-pre-20.rc2"
    assert app.version == settings.app_version
    assert "evt" + "-mb" not in app.version.lower()
