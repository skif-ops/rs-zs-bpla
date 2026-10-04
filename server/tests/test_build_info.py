"""The build shown in the footer of every page and in /api/v1/health (utils/build_info.py): the commit git archive wrote
into server/BUILD, git in a working copy, ZS_BUILD on a bench, and only the release version when nothing is known."""
from pathlib import Path

from config import settings
from tests.test_operator_auth import auth, client  # noqa: F401
from utils import build_info


def test_parse_takes_the_commit_and_date_and_refuses_the_placeholder():
    assert build_info.parse("696d9c801b68409655a2de598a942682b2a26513 2026-10-03") == ("696d9c80", "2026-10-03")
    assert build_info.parse("ABCDEF1234\n") == ("abcdef12", None)
    assert build_info.parse("$Format:%H %cs$") == (None, None)
    assert build_info.parse("") == (None, None)
    assert build_info.parse("not a commit") == (None, None)


def test_build_label_and_sources(tmp_path: Path):
    archived = tmp_path / "BUILD"
    archived.write_text("696d9c801b68409655a2de598a942682b2a26513 2026-10-03\n", encoding="utf-8")
    b = build_info.read_build("1.2.0-x", archived, env={})
    assert (b.commit, b.date, b.date_ru) == ("696d9c80", "2026-10-03", "03.10.2026")
    assert b.label == "1.2.0-x, сборка 696d9c80 от 03.10.2026"
    assert b.as_dict() == {"version": "1.2.0-x", "commit": "696d9c80", "date": "2026-10-03"}
    # the environment wins over the file
    b = build_info.read_build("1.2.0-x", archived, env={build_info.BUILD_ENV: "0123456789ab"})
    assert (b.commit, b.date) == ("01234567", None) and b.label == "1.2.0-x, сборка 01234567"
    # a placeholder outside a git repository, or no file at all: only the version
    (tmp_path / "git-free").mkdir()
    placeholder = tmp_path / "git-free" / "BUILD"
    placeholder.write_text("$Format:%H %cs$\n", encoding="utf-8")
    assert build_info.read_build("1.2.0-x", placeholder, env={}).label == "1.2.0-x"
    assert build_info.read_build("1.2.0-x", tmp_path / "git-free" / "missing", env={}).label == "1.2.0-x"


def test_the_server_reports_its_build_in_health_and_on_every_page(auth):
    store, app = auth
    c = client(app)
    health = c.get("/api/v1/health").json()
    assert health["version"] == settings.app_version
    assert set(health["build"]) == {"version", "commit", "date"} and health["build"]["version"] == settings.app_version
    label = build_info.current(settings.app_version).label
    assert label.startswith(settings.app_version)
    page = c.get("/login").text                                  # public: the footer is on the pages before login too
    assert f"Мухоед {label}" in page and 'class="app-footer"' in page
