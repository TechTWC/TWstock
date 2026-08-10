from __future__ import annotations

import json
from pathlib import Path

from .models import MonitorConfig


def load_config(path: Path) -> MonitorConfig:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"monitor config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"monitor config is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("monitor config root must be an object")
    return MonitorConfig.from_mapping(payload)
