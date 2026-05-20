from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict


ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG_PATH = ROOT / "config.local.json"


def load_local_config() -> Dict[str, str]:
    if not LOCAL_CONFIG_PATH.exists():
        return {}
    data = json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if value is not None}


def get_config_value(name: str, default: str = "") -> str:
    local_config = load_local_config()
    return local_config.get(name) or os.environ.get(name, default)
