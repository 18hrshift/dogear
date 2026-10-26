import copy
import sys

import pytest

from dogear.errors import ToolFailedError, ToolNotFoundError
from dogear.tools import find_tool, run_tool


def test_configured_path_is_used(config):
    custom = copy.deepcopy(config)
    custom["tools"]["ffmpeg"] = sys.executable
    assert find_tool("ffmpeg", custom) == sys.executable


def test_configured_path_that_does_not_exist_is_an_error(config):
    custom = copy.deepcopy(config)
    custom["tools"]["tesseract"] = "/nowhere/tesseract"
    with pytest.raises(ToolNotFoundError) as err:
        find_tool("tesseract", custom)
    assert "/nowhere/tesseract" in err.value.message
    assert "Install Tesseract" in err.value.hint


def test_missing_program_gives_install_hint(config, monkeypatch):
    monkeypatch.setattr("dogear.tools.shutil.which", lambda name: None)
    with pytest.raises(ToolNotFoundError) as err:
        find_tool("ebook_convert", config)
    assert "Calibre" in err.value.hint


def test_run_tool_failure_includes_output():
    with pytest.raises(ToolFailedError, match="boom"):
        run_tool([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"])


def test_run_tool_timeout():
    with pytest.raises(ToolFailedError, match="longer than"):
        run_tool([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)
