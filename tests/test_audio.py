import copy
import json
import subprocess
from pathlib import Path

import pytest
from conftest import require_tool

from dogear.audio import ChapterAudio, build_m4b, concat_to_mp3, ffmetadata, probe_duration
from dogear.document import Metadata
from dogear.errors import ToolNotFoundError


def tone(path: Path, seconds: float, hz: int = 440) -> Path:
    ffmpeg = require_tool("ffmpeg")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={hz}:duration={seconds}",
        ]
        + ["-ar", "24000", "-ac", "1", str(path)],
        check=True,
    )
    return path


def test_concat_to_mp3_joins_in_order(tmp_path, config):
    require_tool("ffprobe")
    parts = [tone(tmp_path / f"part {i}'s.wav", 0.5, 440 + i * 100) for i in range(3)]
    out = tmp_path / "out" / "chapter.mp3"
    concat_to_mp3(parts, out, config)
    assert probe_duration(out, config) == pytest.approx(1.5, abs=0.1)


def test_build_m4b_writes_chapters_and_tags(tmp_path, config):
    ffprobe = require_tool("ffprobe")
    chapters = [
        ChapterAudio("One", tone(tmp_path / "1.wav", 1.0)),
        ChapterAudio("Two; with = signs", tone(tmp_path / "2.wav", 2.0)),
    ]
    out = tmp_path / "book.m4b"
    build_m4b(chapters, Metadata(title="Test Book", authors=["A. Writer"]), out, config)

    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_chapters", "-show_format", "-of", "json", str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    info = json.loads(probe.stdout)
    titles = [c["tags"]["title"] for c in info["chapters"]]
    assert titles == ["One", "Two; with = signs"]
    assert float(info["chapters"][1]["start_time"]) == pytest.approx(1.0, abs=0.05)
    assert info["format"]["tags"]["title"] == "Test Book"
    assert info["format"]["tags"]["artist"] == "A. Writer"


def test_ffmetadata_escapes_and_accumulates():
    text = ffmetadata(Metadata(title="A=B", authors=["X", "Y"]), ["One", "Two#"], [1.5, 2.25])
    assert "title=A\\=B" in text
    assert "artist=X, Y" in text
    assert "START=1500\nEND=3750\ntitle=Two\\#" in text


def test_missing_ffmpeg_fails_loudly(tmp_path, config):
    custom = copy.deepcopy(config)
    custom["tools"]["ffmpeg"] = "definitely-not-ffmpeg"
    with pytest.raises(ToolNotFoundError, match="definitely-not-ffmpeg"):
        concat_to_mp3([tmp_path / "a.wav"], tmp_path / "b.mp3", custom)
