"""Environment-driven settings for RingGuard.

All configuration that could vary between runs (paths, seeds, scale)
lives here. Keep this file secret-free: API keys / tokens must come
from the environment and are NEVER committed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    """Immutable, environment-driven settings."""

    project_root: Path = field(
        default_factory=lambda: Path(_env("RINGGUARD_ROOT", str(Path(__file__).resolve().parents[1])))
    )
    data_dir: Path = field(
        default_factory=lambda: Path(_env("RINGGUARD_DATA_DIR", str(Path.cwd() / "data")))
    )
    db_path: Path = field(
        default_factory=lambda: Path(_env("RINGGUARD_DB_PATH", str(Path.cwd() / "data" / "ringguard.db")))
    )
    seed: int = field(default_factory=lambda: int(_env("RINGGUARD_SEED", "42")))

    # API
    api_title: str = "RingGuard AI Risk Manager"
    api_version: str = "0.1.0"
    api_description: str = (
        "AI Risk Manager for coordinated payment abuse. "
        "Prototype using SIMULATED (synthetic) data only. Not a production service."
    )

    # Runtime behaviour
    log_level: str = field(default_factory=lambda: _env("RINGGUARD_LOG_LEVEL", "INFO"))

    def ensure_directories(self) -> None:
        """Create runtime data directories if they do not exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()