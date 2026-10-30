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


def test_a_standalone_builds_own_program_comes_before_path(config, standalone_build, monkeypatch):
    monkeypatch.setattr("dogear.tools.shutil.which", lambda name: f"/usr/bin/{name}")
    ffmpeg = standalone_build.add_program("ffmpeg")
    assert find_tool("ffmpeg", config) == str(ffmpeg)
    # A program the build doesn't carry is still looked for on PATH.
    assert find_tool("tesseract", config) == "/usr/bin/tesseract"


def test_the_configured_program_comes_before_the_bundled_one(config, standalone_build):
    standalone_build.add_program("ffmpeg")
    custom = copy.deepcopy(config)
    custom["tools"]["ffmpeg"] = sys.executable
    assert find_tool("ffmpeg", custom) == sys.executable


def test_a_normal_install_never_looks_in_a_bundled_folder(config, tmp_path, monkeypatch):
    monkeypatch.setattr("dogear.tools.shutil.which", lambda name: f"/usr/bin/{name}")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bundled" / "tools").mkdir(parents=True)
    (tmp_path / "bundled" / "tools" / "ffmpeg").write_text("not used", encoding="utf-8")
    assert find_tool("ffmpeg", config) == "/usr/bin/ffmpeg"


def test_programs_run_from_a_standalone_build_get_the_original_library_path(
    standalone_build, monkeypatch
):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/dogear/_internal")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    script = "import os; print(os.environ.get('LD_LIBRARY_PATH', 'unset'))"
    assert run_tool([sys.executable, "-c", script]).stdout.strip() == "unset"


def test_run_tool_failure_includes_output():
    with pytest.raises(ToolFailedError, match="boom"):
        run_tool([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"])


def test_run_tool_reads_output_as_utf8_and_survives_bad_bytes():
    script = "import sys; sys.stderr.buffer.write('caf\\u00e9 \\xff'.encode('utf-8') + b'\\xff')"
    result = run_tool([sys.executable, "-c", script])
    assert result.stderr == "café ÿ�"


def test_run_tool_timeout():
    with pytest.raises(ToolFailedError, match="longer than"):
        run_tool([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.2)
