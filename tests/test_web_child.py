"""How the server runs `dogear` as a child process."""

import io
import subprocess
import sys
from pathlib import Path

from dogear.web import child
from dogear.web.child import (
    MAX_LINE_CHARS,
    UTF8_OUTPUT_ENV,
    child_command,
    dogear_command,
    popen_options,
    read_lines,
    run_captured,
)


def test_normal_python_runs_the_dogear_module(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert dogear_command() == [sys.executable, "-m", "dogear"]


def test_a_frozen_build_runs_itself(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/opt/Dogear/dogear")
    assert dogear_command() == ["/opt/Dogear/dogear"]
    assert child_command(["outline", "b.epub", "--json"], None) == [
        "/opt/Dogear/dogear",
        "outline",
        "b.epub",
        "--json",
    ]


def test_the_servers_config_file_is_passed_on(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    command = child_command(["make", "b.epub"], Path("/home/me/dogear.toml"))
    assert command[-2:] == ["--config", str(Path("/home/me/dogear.toml"))]


def test_children_write_utf8_and_open_no_window_on_windows(monkeypatch):
    options = popen_options()
    assert options["env"][UTF8_OUTPUT_ENV] == "1"
    assert options["env"]["PYTHONIOENCODING"] == "utf-8"
    assert "creationflags" not in options or sys.platform == "win32"
    monkeypatch.setattr(child.os, "name", "nt")
    monkeypatch.setattr(subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    assert popen_options()["creationflags"] == 0x08000000


def test_the_real_dogear_writes_utf8_when_asked(tmp_path):
    """The child's side: `dogear` honours the variable even where the console isn't UTF-8."""
    script = "from dogear.cli import main; import sys; sys.exit(main(['outline', 'é.xyz']))"
    env = {**popen_options()["env"], "PYTHONIOENCODING": "ascii"}
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, env=env, cwd=tmp_path
    )
    assert "Error: No such file: é.xyz".encode() in result.stderr


def test_lines_are_decoded_and_cut_to_a_bound():
    long = b"x" * (MAX_LINE_CHARS * 5)
    stream = io.BytesIO(b"first \xc3\xa9\r\n" + long + b"\nlast\n\xff\n")
    lines = list(read_lines(stream))
    assert lines[0] == "first é"
    assert lines[1] == "x" * MAX_LINE_CHARS
    assert lines[2:] == ["last", "�"]


def test_captured_output_is_bounded():
    command = [sys.executable, "-c", "print('y' * 100000)"]
    result = run_captured(command, timeout=30, max_stdout=1000)
    assert result.returncode == 0
    assert result.too_long
    assert result.stdout == b"y" * 1000


def test_a_child_that_takes_too_long_is_stopped():
    command = [sys.executable, "-c", "import time; time.sleep(30)"]
    result = run_captured(command, timeout=0.5, max_stdout=1000)
    assert result.timed_out
    assert result.returncode != 0
