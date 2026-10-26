"""Load settings: packaged defaults, overridden by an optional user TOML file.

`defaults.toml` is the only place a default value lives. Code reads settings from the
dict this module returns instead of keeping its own copies.
"""

from __future__ import annotations

import copy
import tomllib
from importlib import resources
from pathlib import Path
from typing import Any

from dogear.errors import ConfigError

# Tables whose keys are user-chosen (word lists), so any string key is allowed.
FREEFORM_TABLES = {
    ("speech", "abbreviations"),
    ("speech", "abbreviations_before_name"),
    ("speech", "abbreviations_before_number"),
}

Config = dict[str, Any]


def default_config() -> Config:
    text = resources.files("dogear").joinpath("defaults.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)


def load_config(path: Path | None = None) -> Config:
    """Defaults, with `path` (if given) merged on top after validation."""
    config = default_config()
    if path is None:
        return config
    try:
        user = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(
            f"Config file {path} is not valid TOML: {e}",
            hint="Check the line it names. Strings need quotes; tables look like [pdf].",
        ) from None
    return _merge(config, user, ())


def _merge(base: Config, override: Config, where: tuple[str, ...]) -> Config:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        here = (*where, key)
        name = ".".join(here)
        if key not in base:
            known = ", ".join(sorted(base)) or "(none)"
            raise ConfigError(f"Unknown setting '{name}'.", hint=f"Known keys here: {known}.")
        default = base[key]
        if isinstance(default, dict):
            if not isinstance(value, dict):
                raise ConfigError(f"Setting '{name}' must be a table like [{name}].")
            if here in FREEFORM_TABLES:
                _check_string_table(name, value)
                merged[key] = {**default, **value}
            else:
                merged[key] = _merge(default, value, here)
        else:
            _check_type(name, default, value)
            merged[key] = value
    return merged


def _check_string_table(name: str, table: dict[str, Any]) -> None:
    for k, v in table.items():
        if not isinstance(v, str):
            raise ConfigError(f"'{name}.{k}' must be text in quotes, got {v!r}.")


def _check_type(name: str, default: Any, value: Any) -> None:
    expected = type(default)
    if expected is float:
        ok = isinstance(value, int | float) and not isinstance(value, bool)
    elif expected is int:
        ok = isinstance(value, int) and not isinstance(value, bool)
    else:
        ok = isinstance(value, expected)
    if not ok:
        raise ConfigError(
            f"Setting '{name}' must be {expected.__name__}, got {type(value).__name__} ({value!r})."
        )
    if expected is list and default and not all(isinstance(v, type(default[0])) for v in value):
        raise ConfigError(f"Every item in '{name}' must be {type(default[0]).__name__}.")
