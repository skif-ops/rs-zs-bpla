"""Input validation helpers."""

from __future__ import annotations

import json
from pathlib import Path

from models.schemas import MicrophoneArrayConfig


def load_microphone_config(path: Path) -> MicrophoneArrayConfig:
    """Load and validate a mics.json file."""

    text = path.read_text(encoding="utf-8")
    text = text.replace("“", '"').replace("”", '"')
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid mics.json: {exc}") from exc
    return MicrophoneArrayConfig.model_validate(payload)
