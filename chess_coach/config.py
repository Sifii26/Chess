"""Persistent user settings and well-known paths."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "Chess Coach"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("CHESS_COACH_HOME", Path.home() / ".chess_coach"))
CONFIG_FILE = CONFIG_DIR / "settings.json"
TEMPLATE_DIR = CONFIG_DIR / "piece_templates"
ENGINE_DIR = PROJECT_ROOT / "engines"


@dataclass
class Settings:
    stockfish_path: str = ""
    depth: int = 18
    multipv: int = 3
    threads: int = max(1, (os.cpu_count() or 2) // 2)
    hash_mb: int = 128
    mate_search_depth: int = 30
    auto_analyze: bool = True
    mate_mode: bool = False
    fair_play_acknowledged: bool = False
    capture_delay_s: int = 3
    extra: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        try:
            return cls(**known)
        except TypeError:
            return cls()

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_FILE.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            pass  # settings are a convenience; never crash over them
