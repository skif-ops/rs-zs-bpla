"""Which build the server runs: the release version (config.settings.app_version) and the commit it was packaged from.

``server/BUILD`` holds the placeholder ``$Format:%H %cs$``; ``git archive`` replaces it with the commit hash and date of
the archived tree (``.gitattributes``: ``export-subst``), so the package installed on a server carries its own identity
without anyone editing a version by hand.  A working copy still has the placeholder and asks git instead; where neither
is available (no file, no git) only the release version is known.  ``ZS_BUILD`` ("<commit> <YYYY-MM-DD>") overrides
both, for a bench.  The result is shown in the footer of every page and in ``/api/v1/health``.
"""
from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
BUILD_FILE = BASE / "BUILD"
BUILD_ENV = "ZS_BUILD"
SHORT = 8                                   # the length the deploy scripts use in VERSION.txt
PLACEHOLDER = "$Format"
_LINE = re.compile(r"^([0-9a-fA-F]{7,40})(?:\s+(\d{4}-\d{2}-\d{2}))?(?:\s|$)")


@dataclass(frozen=True)
class Build:
    version: str
    commit: str | None = None               # SHORT hex characters of the commit, None when unknown
    date: str | None = None                 # the commit's date, YYYY-MM-DD

    @property
    def date_ru(self) -> str | None:
        return ".".join(reversed(self.date.split("-"))) if self.date else None

    @property
    def label(self) -> str:
        """``1.2.0-evt-pre-20.1, сборка 696d9c80 от 03.10.2026``; without the build when it is unknown."""
        if not self.commit:
            return self.version
        return f"{self.version}, сборка {self.commit}" + (f" от {self.date_ru}" if self.date else "")

    def as_dict(self) -> dict[str, str | None]:
        return {"version": self.version, "commit": self.commit, "date": self.date}


def parse(text: str) -> tuple[str | None, str | None]:
    """The commit (shortened) and date of a ``<hash> [<YYYY-MM-DD>]`` line; (None, None) for anything else, the
    placeholder included."""
    m = _LINE.match((text or "").strip())
    if not m:
        return None, None
    return m.group(1).lower()[:SHORT], m.group(2)


def _from_git(directory: Path) -> str:
    try:
        out = subprocess.run(["git", "-C", str(directory), "log", "-1", "--format=%H %cs"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def read_build(version: str, path: Path = BUILD_FILE, env: Mapping[str, str] | None = None) -> Build:
    env = os.environ if env is None else env
    text = (env.get(BUILD_ENV) or "").strip()
    if not text:
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            text = ""
        if not text or text.startswith(PLACEHOLDER):      # a working copy, not an archive
            text = _from_git(path.parent)
    commit, date = parse(text)
    return Build(version, commit, date)


@lru_cache(maxsize=None)
def current(version: str) -> Build:
    """The server's build, read once (the pages and /api/v1/health share it)."""
    return read_build(version)
