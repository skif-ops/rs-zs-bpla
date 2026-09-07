"""File handling utilities for uploads and generated artifacts."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile

from config import settings
from models.schemas import UploadedFileInfo

SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac"}
SUPPORTED_AUDIO_EXTENSIONS_TEXT = "WAV, MP3, M4A or AAC"


def ensure_runtime_directories() -> None:
    """Create upload/output/static directories if they are missing."""

    for path in (
        settings.upload_dir,
        settings.output_dir,
        settings.dataset_dir,
        settings.dataset_dir / "raw",
        settings.ml_model_path.parent,
        settings.static_dir,
        settings.template_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def new_analysis_id() -> str:
    """Return a UUID for one analysis session."""

    return str(uuid.uuid4())


def safe_filename(filename: str) -> str:
    """Return a conservative filename safe for local storage."""

    cleaned = Path(filename).name.strip().replace(" ", "_")
    allowed = "-_.()abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    safe = "".join(ch for ch in cleaned if ch in allowed)
    return safe or f"upload_{uuid.uuid4().hex}"


def analysis_upload_dir(analysis_id: str) -> Path:
    """Return the upload folder for one analysis."""

    path = settings.upload_dir / analysis_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def analysis_output_dir(analysis_id: str) -> Path:
    """Return the output folder for one analysis."""

    path = settings.output_dir / analysis_id
    path.mkdir(parents=True, exist_ok=True)
    return path


async def save_upload(upload: UploadFile, target_dir: Path) -> UploadedFileInfo:
    """Save an UploadFile to disk and return metadata."""

    target_dir.mkdir(parents=True, exist_ok=True)
    filename = safe_filename(upload.filename or f"upload_{uuid.uuid4().hex}")
    target_path = target_dir / filename
    with target_path.open("wb") as output:
        shutil.copyfileobj(upload.file, output)
    size = target_path.stat().st_size
    await upload.close()
    return UploadedFileInfo(
        original_name=upload.filename or filename,
        stored_path=str(target_path),
        size_bytes=size,
    )


def is_supported_audio_filename(filename: str | None) -> bool:
    """Return True if a filename has a supported audio extension."""

    if not filename:
        return False
    return Path(filename).suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS


def assert_audio_path(path: Path) -> None:
    """Raise ValueError if a file does not look like supported audio."""

    if path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        raise ValueError(f"{path.name} is not a supported audio file ({SUPPORTED_AUDIO_EXTENSIONS_TEXT}).")
    if not path.exists() or not path.is_file():
        raise ValueError(f"{path.name} was not found.")


def assert_wav_path(path: Path) -> None:
    """Backward-compatible alias for older WAV-only call sites."""

    assert_audio_path(path)


def resolve_artifact(path: str) -> Path:
    """Resolve a generated artifact path and keep it inside output_dir."""

    artifact = Path(path).resolve()
    output_root = settings.output_dir.resolve()
    if output_root not in artifact.parents and artifact != output_root:
        raise ValueError("Artifact path is outside the output directory.")
    if not artifact.exists():
        raise FileNotFoundError(path)
    return artifact


def resolve_dataset_file(path: str) -> Path:
    """Resolve a dataset file path and keep it inside dataset_dir (path-safe)."""

    target = Path(path).resolve()
    dataset_root = settings.dataset_dir.resolve()
    if dataset_root not in target.parents and target != dataset_root:
        raise ValueError("Path is outside the dataset directory.")
    if not target.exists():
        raise FileNotFoundError(path)
    return target
