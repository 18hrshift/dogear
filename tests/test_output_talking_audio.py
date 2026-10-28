"""Talking-book audio: constant-bitrate mono MP3 at 44.1 kHz, the format every player plays."""

from audio_builder import probe, tone

from dogear.output.chapter import ChapterAudio
from dogear.output.talking_audio import encode_talking_audio
from dogear.readalong.model import Clip, SectionText, Sync


def section(wav) -> SectionText:
    sync = Sync("s001-par1", "s001-u1", Clip(0.0, 1.0))
    audio = ChapterAudio("One", wav, (0, 24000), 24000)
    return SectionText(1, "One", "body", "en", (), (sync,), audio)


def test_each_section_becomes_a_plain_cbr_mp3(tmp_path, config):
    original = section(tone(tmp_path / "a.wav", 2.0))
    [encoded] = encode_talking_audio([original], tmp_path, config)
    assert encoded.audio.path.suffix == ".mp3"
    # Everything but the file is kept, timings included.
    assert encoded.syncs == original.syncs and encoded.audio.marks == original.audio.marks
    info = probe(encoded.audio.path)
    [stream] = info["streams"]
    assert (stream["codec_name"], stream["sample_rate"], stream["channels"]) == ("mp3", "44100", 1)
    assert int(stream["bit_rate"]) == 64000
    assert "tags" not in info["format"]


def test_the_bitrate_comes_from_config(tmp_path, config):
    config["audio"]["talking_book_bitrate"] = "48k"
    [encoded] = encode_talking_audio([section(tone(tmp_path / "a.wav", 1.0))], tmp_path, config)
    assert int(probe(encoded.audio.path)["streams"][0]["bit_rate"]) == 48000
