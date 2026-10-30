"""Shared test setup.

Tests that need an external program skip when it's missing on a developer machine.
CI lists the programs it installs in DOGEAR_REQUIRE_TOOLS (comma-separated); for those,
a missing program fails the run instead, so a broken runner can't quietly skip tests.
"""

import os
import shutil

import pytest
from standalone_build import FakeBuild

from dogear.config import default_config


def require_tool(program: str) -> str:
    path = shutil.which(program)
    if path:
        return path
    required = {t.strip() for t in os.environ.get("DOGEAR_REQUIRE_TOOLS", "").split(",")}
    if program in required:
        pytest.fail(f"{program} is required (DOGEAR_REQUIRE_TOOLS) but was not found on PATH")
    pytest.skip(f"{program} not installed")


@pytest.fixture
def config():
    return default_config()


@pytest.fixture
def standalone_build(tmp_path, monkeypatch) -> FakeBuild:
    """Dogear running as a standalone build, with an empty bundled folder to fill."""
    return FakeBuild(tmp_path / "standalone", monkeypatch)
