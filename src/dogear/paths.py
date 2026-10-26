"""Per-user folders for downloaded voice models and the speech cache.

Each can be set in config; empty means the usual place for the platform.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dogear.config import Config

APP = "dogear"


def models_dir(config: Config) -> Path:
    return _configured(config["models"]["dir"]) or _platform_dir("data") / "models"


def cache_dir(config: Config) -> Path:
    return _configured(config["render"]["cache_dir"]) or _platform_dir("cache")


def _configured(value: str) -> Path | None:
    return Path(value).expanduser() if value else None


def _platform_dir(kind: str) -> Path:
    home = Path.home()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local") / APP
        return base / "Cache" if kind == "cache" else base
    if sys.platform == "darwin":
        library = home / "Library"
        return library / ("Caches" if kind == "cache" else "Application Support") / APP
    if kind == "cache":
        return Path(os.environ.get("XDG_CACHE_HOME") or home / ".cache") / APP
    return Path(os.environ.get("XDG_DATA_HOME") or home / ".local" / "share") / APP
