"""Shared test setup.

Tests that need an external program skip when it's missing on a developer machine.
CI lists the programs it installs in DOGEAR_REQUIRE_TOOLS (comma-separated); for those,
a missing program fails the run instead, so a broken runner can't quietly skip tests.
"""

import os
import shutil

import pytest

from dogear.config import default_config


def require_tool(program: str) -> str:
    path = shutil.which(program)
    if path:
        return path
    required = {t.strip() for t in os.environ.get("DOGEAR_REQUIRE_TOOLS", "").split(",")}
    if program in required:
        pytest.fail(f"{program} is required (DOGEAR_REQUIRE_TOOLS) but was not found on PATH")
    pytest.skip(f"{program} not installed")


@pytest.fixture(autouse=True)
def _no_settings_file_from_the_environment(monkeypatch):
    """A developer's own DOGEAR_CONFIG must not change what the tests see."""
    monkeypatch.delenv("DOGEAR_CONFIG", raising=False)


@pytest.fixture(autouse=True)
def _per_user_folders_in_a_temporary_home(monkeypatch, tmp_path_factory):
    """Every test gets its own empty home folder, so nothing it does (a CLI command run
    with default settings, say) can reach the real downloaded voice, speech cache, or web
    books. A stand-in spaCy model once leaked into the real models folder this way and
    broke every real `dogear make` until it was found."""
    home = tmp_path_factory.mktemp("home")
    for name in ("HOME", "USERPROFILE"):  # Path.home() on POSIX and on Windows
        monkeypatch.setenv(name, str(home))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local" / "share"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(home / ".cache"))


@pytest.fixture
def config():
    return default_config()
