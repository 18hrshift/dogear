import copy

import pytest
from audio_builder import image_bytes, loudness, probe, silence, spiky, tone
from conftest import require_tool

from dogear.config import default_config
from dogear.document import Cover, Metadata
from dogear.errors import ToolNotFoundError
from dogear.output import ChapterAudio, build_m4b
from dogear.output.m4b import ffmetadata

AUDIO = default_config()["audio"]
TARGET = AUDIO["loudness_target_lufs"]
CEILING = AUDIO["true_peak_ceiling_dbtp"]

# (title, seconds, maker); the makers give very different loudness on purpose.
CHAPTERS = [
    ("Opening", 1.5, lambda p: tone(p, 1.5, gain_db=-12)),  # about -33.7 LUFS
    ("Two; with = signs", 2.0, lambda p: spiky(p, 2.0)),  # needs the limiter
    ("A pause", 1.0, lambda p: silence(p, 1.0)),
    ("Último", 1.0, lambda p: tone(p, 1.0, hz=550, gain_db=6)),  # about -15.7 LUFS
]


@pytest.fixture(scope="module")
def book(tmp_path_factory):
    require_tool("ffprobe")
    tmp = tmp_path_factory.mktemp("m4b")
    chapters = [
        ChapterAudio(title, make(tmp / f"{n}.wav")) for n, (title, _, make) in enumerate(CHAPTERS)
    ]
    metadata = Metadata(
        title="Test Book",
        authors=["A. Writer", "B. Author"],
        language="fr-CA",
        cover=Cover(image_bytes("JPEG"), "image/jpeg"),
    )
    out = tmp / "new folder" / "book.m4b"
    build_m4b(chapters, metadata, out, default_config())
    return out, probe(out)


def test_one_chapter_marker_per_section(book):
    _, info = book
    assert [c["tags"]["title"] for c in info["chapters"]] == [t for t, _, _ in CHAPTERS]
    starts = [float(c["start_time"]) for c in info["chapters"]]
    assert starts == pytest.approx([0.0, 1.5, 3.5, 4.5], abs=0.01)
    assert float(info["chapters"][-1]["end_time"]) == pytest.approx(5.5, abs=0.01)


def test_book_tags(book):
    _, info = book
    tags = info["format"]["tags"]
    assert tags["title"] == "Test Book"
    assert tags["album"] == "Test Book"
    assert tags["artist"] == "A. Writer, B. Author"
    assert tags["album_artist"] == "A. Writer, B. Author"
    assert tags["genre"] == "Audiobook"
    assert tags["media_type"] == "2"


def test_aac_audio_with_language_and_attached_cover(book):
    _, info = book
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    video = [s for s in info["streams"] if s["codec_type"] == "video"]
    assert [s["codec_name"] for s in audio] == ["aac"]
    assert audio[0]["tags"]["language"] == "fra"
    assert audio[0]["sample_rate"] == "24000"
    assert [s["codec_name"] for s in video] == ["mjpeg"]
    assert video[0]["disposition"]["attached_pic"] == 1


def test_every_chapter_lands_at_the_target(book):
    out, info = book
    for chapter, (title, _, _) in zip(info["chapters"], CHAPTERS, strict=True):
        start, end = float(chapter["start_time"]), float(chapter["end_time"])
        # Stay clear of the joins, where a neighbor's audio could leak into the window.
        integrated, peak = loudness(out, start + 0.1, end - start - 0.2)
        if title == "A pause":
            assert peak < -60, "silence must not be boosted"
        else:
            assert integrated == pytest.approx(TARGET, abs=1.0), title
            assert peak <= CEILING + 0.5, title


def test_only_the_book_is_left_behind(book):
    out, _ = book
    assert [p.name for p in out.parent.iterdir()] == ["book.m4b"]


@pytest.mark.parametrize("fmt", ["PNG", None])
def test_png_cover_or_none(tmp_path, config, fmt):
    require_tool("ffprobe")
    cover = Cover(image_bytes(fmt), f"image/{fmt.lower()}") if fmt else None
    out = tmp_path / "book.m4b"
    chapters = [ChapterAudio("Only", tone(tmp_path / "1.wav", 0.6))]
    build_m4b(chapters, Metadata(title="T", cover=cover), out, config)
    video = [s["codec_name"] for s in probe(out)["streams"] if s["codec_type"] == "video"]
    assert video == (["png"] if fmt else [])


def test_loudness_target_comes_from_config(tmp_path, config):
    require_tool("ffprobe")
    chapters = [ChapterAudio("Only", tone(tmp_path / "1.wav", 1.0))]
    quieter = copy.deepcopy(config)
    quieter["audio"]["loudness_target_lufs"] = TARGET - 6
    build_m4b(chapters, Metadata(title="T"), tmp_path / "default.m4b", config)
    build_m4b(chapters, Metadata(title="T"), tmp_path / "quieter.m4b", quieter)
    default_level, _ = loudness(tmp_path / "default.m4b")
    quieter_level, _ = loudness(tmp_path / "quieter.m4b")
    assert default_level == pytest.approx(TARGET, abs=0.5)
    assert quieter_level == pytest.approx(TARGET - 6, abs=0.5)


def test_other_sample_rates_are_kept(tmp_path, config):
    require_tool("ffprobe")
    chapters = [
        ChapterAudio("One", tone(tmp_path / "1.wav", 1.0, rate=22050)),
        ChapterAudio("Two", spiky(tmp_path / "2.wav", 1.0, rate=22050)),
        ChapterAudio("Three", tone(tmp_path / "3.wav", 1.0, rate=22050)),
    ]
    out = tmp_path / "book.m4b"
    build_m4b(chapters, Metadata(title="T"), out, config)
    info = probe(out)
    assert info["streams"][0]["sample_rate"] == "22050"
    starts = [float(c["start_time"]) for c in info["chapters"]]
    assert starts == pytest.approx([0.0, 1.0, 2.0], abs=0.01)


def test_ffmetadata_escapes_and_accumulates():
    text = ffmetadata(Metadata(title="A=B", authors=["X", "Y"]), ["One", "Two#"], [1.5, 2.25])
    assert "title=A\\=B" in text
    assert "album=A\\=B" in text
    assert "artist=X, Y" in text
    assert "genre=Audiobook" in text
    assert "START=1500\nEND=3750\ntitle=Two\\#" in text


def test_ffmetadata_leaves_out_missing_authors():
    text = ffmetadata(Metadata(title="Anonymous"), ["One"], [1.0])
    assert "artist" not in text


def test_missing_ffmpeg_fails_loudly(tmp_path, config):
    custom = copy.deepcopy(config)
    custom["tools"]["ffmpeg"] = "definitely-not-ffmpeg"
    chapters = [ChapterAudio("One", tmp_path / "a.wav")]
    with pytest.raises(ToolNotFoundError, match="definitely-not-ffmpeg"):
        build_m4b(chapters, Metadata(title="T"), tmp_path / "b.m4b", custom)


def test_no_chapters_is_a_bug(tmp_path, config):
    with pytest.raises(ValueError, match="no chapters"):
        build_m4b([], Metadata(title="T"), tmp_path / "b.m4b", config)
