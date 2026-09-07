"""Per-class metadata registry for the labeled sound dataset.

Stores, per class label: its category (drone/background), whether it counts as a
drone, an optional reference image, a description and the last-used recording
metadata. Kept separate from ``SoundDatasetManager`` (a slotted dataclass) and
from the frozen ``Settings`` so that drone classes added through the UI are
recognized as drones without editing code.
"""

from __future__ import annotations

import json
from pathlib import Path

from config import settings
from models.schemas import LabelMeta, LabelRegistry, RecordingMetadata
from utils.serialization import write_json


def registry_path() -> Path:
    """Location of the registry document."""

    return settings.dataset_dir / "label_meta.json"


def load_registry(path: Path | None = None) -> LabelRegistry:
    """Load the registry, returning an empty one if missing or unreadable."""

    path = path or registry_path()
    if not path.exists():
        return LabelRegistry()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return LabelRegistry(**data)
    except Exception:
        return LabelRegistry()


def save_registry(registry: LabelRegistry, path: Path | None = None) -> Path:
    """Persist the registry as UTF-8 JSON (Cyrillic-safe)."""

    return write_json(path or registry_path(), registry)


def upsert_label(
    label: str,
    *,
    category: str | None = None,
    is_drone: bool | None = None,
    image_path: str | None = None,
    description: str | None = None,
    status: str | None = None,
    last_metadata: RecordingMetadata | None = None,
    path: Path | None = None,
) -> LabelMeta:
    """Create or update one class entry, persisting the registry."""

    registry = load_registry(path)
    meta = registry.labels.get(label) or LabelMeta(label=label)
    if category is not None:
        if category not in ("drone", "background"):
            raise ValueError(f"Invalid category: {category!r}")
        meta.category = category  # type: ignore[assignment]
    if is_drone is not None:
        meta.is_drone = bool(is_drone)
    elif category is not None:
        meta.is_drone = category == "drone"
    if image_path is not None:
        meta.image_path = image_path
    if description is not None:
        meta.description = description
    if status is not None:
        if status not in ("active", "training_provisional", "training_provisional_weak", "research", "pending"):
            raise ValueError(f"Invalid label status: {status!r}")
        meta.status = status  # type: ignore[assignment]
    if last_metadata is not None:
        meta.last_metadata = last_metadata
    registry.labels[label] = meta
    save_registry(registry, path)
    return meta


def remove_label(label: str, path: Path | None = None) -> bool:
    """Remove a class entry; return True if it existed."""

    registry = load_registry(path)
    if label in registry.labels:
        del registry.labels[label]
        save_registry(registry, path)
        return True
    return False


def drone_labels(path: Path | None = None) -> set[str]:
    """Labels flagged as drones in the registry."""

    registry = load_registry(path)
    return {
        label for label, meta in registry.labels.items()
        if meta.is_drone and meta.status in {"active", "training_provisional", "training_provisional_weak"}
    }


def effective_drone_labels() -> frozenset[str]:
    """Config drone labels unioned with registry drone labels.

    Used by the analyzer so a drone class added through the training UI is
    treated as a drone immediately, without editing the frozen config.
    """

    # drone_labels() -> load_registry() already returns empty on any error.
    return frozenset(settings.ml_drone_labels) | drone_labels()
