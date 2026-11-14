"""station/analysis_access.py: a file analysis belongs to the account that ran it; its artifacts (/artifact, /download)
are seen by that account, by unlimited accounts and by accounts whose tenants cover the maker's; nothing else under
output (backups, hidden files) is served; /dataset/image serves images only."""
import json
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from config import settings
from station import analysis_access as aa, operator_auth as oa

PASSWORD = "correct horse battery"
ORIGIN = {"origin": "https://testserver"}


def account(name, tenants=(), stations=()):
    return {"name": name, "tenants": list(tenants), "stations": list(stations)}


def test_who_sees_an_analysis():
    anna, nick, bob = account("anna", ["north"]), account("nick", ["north"]), account("bob", ["south"])
    both, st17, boss = account("both", ["north", "south"]), account("st17", [], [17]), account("boss")
    by_anna = {"name": "anna", "tenants": ["north"], "stations": []}
    assert all(aa.may_read(o, by_anna) for o in (anna, nick, both, boss))     # itself, the same tenant, a wider one, unlimited
    assert not aa.may_read(bob, by_anna) and not aa.may_read(st17, by_anna)   # another tenant, stations only
    by_boss = {"name": "boss", "tenants": [], "stations": []}
    assert aa.may_read(boss, by_boss) and aa.may_read(account("root"), by_boss)
    assert not aa.may_read(anna, by_boss) and not aa.may_read(both, by_boss)  # an unlimited maker's analysis is its own
    by_st17 = {"name": "st17", "tenants": [], "stations": [17]}
    assert aa.may_read(st17, by_st17) and aa.may_read(boss, by_st17) and not aa.may_read(anna, by_st17)
    assert aa.may_read(boss, None) and not aa.may_read(anna, None)             # no owner recorded: unlimited only
    assert aa.may_read(None, None) and aa.may_read(None, by_anna)              # the bench checks nobody


@pytest.fixture
def web(tmp_path: Path, monkeypatch):
    """Accounts in a temporary store, uploads/output/dataset under tmp_path."""
    monkeypatch.delenv(oa.INSECURE_BENCH_ENV, raising=False)
    monkeypatch.delenv(oa.TOTP_ENV, raising=False)
    monkeypatch.setenv(oa.ACCOUNTS_ENV, str(tmp_path / "operators.json"))
    monkeypatch.setenv(oa.SESSION_KEY_ENV, str(tmp_path / "session.key"))
    monkeypatch.setenv(oa.STATE_ENV, str(tmp_path / "state.sqlite3"))
    monkeypatch.setattr(oa, "throttle", oa.LoginThrottle())
    base = settings.base_dir
    object.__setattr__(settings, "base_dir", tmp_path / "server")
    for d in ("uploads", "output", "dataset"):
        (tmp_path / "server" / d).mkdir(parents=True)
    from app import app

    accounts = oa.current_store()
    for name, tenants, stations in (("anna", ["north"], []), ("nick", ["north"], []), ("bob", ["south"], []),
                                    ("st17", [], [17]), ("boss", [], [])):
        accounts.add_user(name, "operator", PASSWORD)
        accounts.set_scope(name, tenants, stations)
    try:
        yield app
    finally:
        object.__setattr__(settings, "base_dir", base)


def logged_in(app, name) -> TestClient:
    c = TestClient(app, base_url="https://testserver", follow_redirects=False)
    r = c.post("/login", data={"username": name, "password": PASSWORD}, headers=ORIGIN)
    assert r.status_code == 303, r.text
    return c


def wav_bytes(seconds=2.0, rate=22050) -> bytes:
    t = np.arange(int(rate * seconds)) / rate
    x = 0.3 * np.sin(2 * np.pi * 120 * t) + 0.1 * np.sin(2 * np.pi * 240 * t) + 0.02 * np.random.default_rng(1).standard_normal(t.size)
    path = Path(__file__).with_name("_tmp_tone.wav")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes((x * 32767).astype("<i2").tobytes())
    data = path.read_bytes()
    path.unlink()
    return data


def analyze(c: TestClient, data: bytes) -> dict:
    r = c.post("/api/analyze-single", files={"wav_file": ("tone.wav", data, "audio/wav")}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    return r.json()


def statuses(app, path: str, names, route="/artifact") -> dict:
    return {n: logged_in(app, n).get(route, params={"path": path}).status_code for n in names}


def test_artifacts_follow_the_account(web):
    app = web
    data = wav_bytes()
    everyone = ("anna", "nick", "bob", "st17", "boss")
    report = analyze(logged_in(app, "anna"), data)
    plot = report["plots"]["spectrogram"]
    analysis_dir = Path(plot).parent
    assert json.loads((analysis_dir / aa.OWNER_FILE).read_text())["name"] == "anna"
    assert statuses(app, plot, everyone) == {"anna": 200, "nick": 200, "bob": 404, "st17": 404, "boss": 200}
    assert statuses(app, report["report_json"], ("anna", "bob"), "/download") == {"anna": 200, "bob": 404}
    assert "attachment" in logged_in(app, "anna").get("/download", params={"path": report["report_json"]}).headers["content-disposition"]
    # the owner file, the uploaded recording, a path outside output and a backup archive are not artifacts for anyone
    (settings.output_dir / "backups").mkdir()
    archive = settings.output_dir / "backups" / "backup_20261003_110000.tar.gz"
    archive.write_bytes(b"not for the web")
    upload = next(settings.upload_dir.rglob("*.wav"))
    for path in (str(analysis_dir / aa.OWNER_FILE), str(upload), str(archive), str(settings.output_dir),
                 str(analysis_dir), "/etc/hostname", str(analysis_dir / "../../../etc/hostname")):
        assert statuses(app, path, ("anna", "boss")) == {"anna": 404, "boss": 404}, path
    # an unlimited maker's analysis is its own; a station-limited maker's too
    by_boss = analyze(logged_in(app, "boss"), data)["plots"]["spectrogram"]
    assert statuses(app, by_boss, everyone) == {"anna": 404, "nick": 404, "bob": 404, "st17": 404, "boss": 200}
    by_st17 = analyze(logged_in(app, "st17"), data)["plots"]["spectrogram"]
    assert statuses(app, by_st17, ("anna", "st17", "boss")) == {"anna": 404, "st17": 200, "boss": 200}
    # an analysis from before the owner file (or from the bench): unlimited accounts only
    (analysis_dir / aa.OWNER_FILE).unlink()
    assert statuses(app, plot, ("anna", "boss")) == {"anna": 404, "boss": 200}


def test_dataset_image_serves_images_only(web):
    app = web
    uploads = settings.dataset_dir / "raw" / "x" / "_uploads"
    uploads.mkdir(parents=True)
    (uploads / "pic.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(16))
    (uploads.parent / "rec.wav").write_bytes(b"RIFF" + bytes(32))
    c = logged_in(app, "anna")
    assert c.get("/dataset/image", params={"path": str(uploads / "pic.png")}).status_code == 200
    assert c.get("/dataset/image", params={"path": str(uploads.parent / "rec.wav")}).status_code == 404
    assert c.get("/dataset/image", params={"path": str(uploads / "missing.png")}).status_code == 404
    assert c.get("/dataset/image", params={"path": str(settings.output_dir / "x.png")}).status_code == 404
