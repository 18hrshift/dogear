import copy

import pytest
from audio_builder import image_bytes, loudness, probe, silence, spiky, tone
from conftest import require_tool

from dogear.config import default_config
from dogear.document import Cover, Metadata
from dogear.errors import OutputFolderError, ToolNotFoundError
from dogear.output import ChapterAudio, build_mp3_folder
from dogear.output.folder_record import RECORD_NAME

AUDIO = default_config()["audio"]
TARGET = AUDIO["loudness_target_lufs"]
CEILING = AUDIO["true_peak_ceiling_dbtp"]

TRACKS = [
    "01 - Chapter One The Start.mp3",
    "02 - Spikes.mp3",
    "03 - A pause.mp3",
]
PLAYLIST = "Book A Test.m3u"


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    require_tool("ffprobe")
    tmp = tmp_path_factory.mktemp("mp3")
    chapters = [
        ChapterAudio('Chapter One: "The Start"?', tone(tmp / "1.wav", 2.0, gain_db=-10)),
        ChapterAudio("Spikes", spiky(tmp / "2.wav", 2.0)),
        ChapterAudio("A pause", silence(tmp / "3.wav", 1.0)),
    ]
    metadata = Metadata(
        title="Book: A Test",
        authors=["A. Writer"],
        language="en-US",
        cover=Cover(image_bytes("PNG"), "image/png"),
    )
    target = tmp / "out" / "Book"
    paths = build_mp3_folder(chapters, metadata, target, default_config())
    return target, paths


def test_returns_tracks_in_order_with_safe_names(folder):
    target, paths = folder
    assert paths == [target / name for name in TRACKS]
    assert sorted(p.name for p in target.iterdir()) == sorted([*TRACKS, PLAYLIST, RECORD_NAME])


def test_playlist_lists_tracks_with_lengths_and_titles(folder):
    target, _ = folder
    data = (target / PLAYLIST).read_bytes()
    assert data.decode("utf-8").split("\r\n") == [
        "#EXTM3U",
        '#EXTINF:2,Chapter One: "The Start"?',
        TRACKS[0],
        "#EXTINF:2,Spikes",
        TRACKS[1],
        "#EXTINF:1,A pause",
        TRACKS[2],
        "",
    ]


def test_id3_tags_and_cover(folder):
    _, paths = folder
    for number, path in enumerate(paths, start=1):
        info = probe(path)
        tags = info["format"]["tags"]
        assert tags["album"] == "Book: A Test"
        assert tags["artist"] == "A. Writer"
        assert tags["album_artist"] == "A. Writer"
        assert tags["track"] == f"{number}/3"
        assert tags["genre"] == "Audiobook"
        assert tags["language"] == "eng"
        streams = {s["codec_type"]: s for s in info["streams"]}
        assert streams["audio"]["codec_name"] == "mp3"
        assert streams["video"]["codec_name"] == "png"
        assert streams["video"]["disposition"]["attached_pic"] == 1
    assert probe(paths[0])["format"]["tags"]["title"] == 'Chapter One: "The Start"?'


def test_id3_version_is_2_3(folder):
    _, paths = folder
    header = paths[0].read_bytes()[:4]
    assert header == b"ID3\x03"


def test_each_track_is_normalized(folder):
    _, paths = folder
    quiet_tone, spikes, pause = (loudness(p) for p in paths)
    assert quiet_tone[0] == pytest.approx(TARGET, abs=0.5)
    assert quiet_tone[1] <= CEILING
    # The limiter keeps the bursts under the ceiling (plus a little MP3 overshoot).
    assert spikes[0] == pytest.approx(TARGET, abs=1.0)
    assert spikes[1] <= CEILING + 0.5
    assert pause[1] < -60, "silence must not be boosted"


def two_chapters(tmp_path, second="Two"):
    clip = tone(tmp_path / "clip.wav", 0.6)
    return [ChapterAudio("One", clip), ChapterAudio(second, clip)]


def test_rerun_replaces_its_own_files_and_keeps_the_users(tmp_path, config):
    require_tool("ffprobe")
    target = tmp_path / "Book"
    target.mkdir()
    (target / "notes.txt").write_text("mine")
    book = Metadata(title="Book")
    build_mp3_folder(two_chapters(tmp_path), book, target, config)
    build_mp3_folder(two_chapters(tmp_path, second="Second"), book, target, config)
    assert sorted(p.name for p in target.iterdir()) == [
        RECORD_NAME,
        "01 - One.mp3",
        "02 - Second.mp3",
        "Book.m3u",
        "notes.txt",
    ]
    assert (target / "notes.txt").read_text() == "mine"


def test_another_books_folder_is_refused(tmp_path, config):
    require_tool("ffprobe")
    target = tmp_path / "Book"
    build_mp3_folder(two_chapters(tmp_path), Metadata(title="First"), target, config)
    with pytest.raises(OutputFolderError, match='another book, "First"'):
        build_mp3_folder(two_chapters(tmp_path), Metadata(title="Second"), target, config)
    assert (target / "First.m3u").exists()
    assert not (target / "Second.m3u").exists()


def test_a_users_file_is_never_overwritten(tmp_path, config):
    require_tool("ffprobe")
    target = tmp_path / "Book"
    target.mkdir()
    (target / "01 - One.mp3").write_bytes(b"mine")
    with pytest.raises(OutputFolderError, match="didn't make"):
        build_mp3_folder(two_chapters(tmp_path), Metadata(title="Book"), target, config)
    assert (target / "01 - One.mp3").read_bytes() == b"mine"


def test_folder_path_that_is_a_file_is_refused(tmp_path, config):
    require_tool("ffmpeg")
    target = tmp_path / "Book"
    target.write_text("a file")
    with pytest.raises(OutputFolderError, match="is a file"):
        build_mp3_folder(two_chapters(tmp_path), Metadata(title="Book"), target, config)


def test_mp3_quality_comes_from_config(tmp_path, config):
    require_tool("ffprobe")
    small = copy.deepcopy(config)
    small["audio"]["mp3_quality"] = 9
    chapters = [ChapterAudio("One", tone(tmp_path / "1.wav", 3.0))]
    best = build_mp3_folder(chapters, Metadata(title="A"), tmp_path / "best", config)[0]
    worst = build_mp3_folder(chapters, Metadata(title="A"), tmp_path / "small", small)[0]
    assert worst.stat().st_size < best.stat().st_size


def test_missing_ffmpeg_fails_loudly(tmp_path, config):
    custom = copy.deepcopy(config)
    custom["tools"]["ffmpeg"] = "definitely-not-ffmpeg"
    chapters = [ChapterAudio("One", tmp_path / "a.wav")]
    with pytest.raises(ToolNotFoundError, match="definitely-not-ffmpeg"):
        build_mp3_folder(chapters, Metadata(title="T"), tmp_path / "out", custom)
    assert not (tmp_path / "out").exists()
