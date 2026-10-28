import copy
import dataclasses
import logging
import math
import wave

import pytest
from audio_builder import silence, spiky, tone
from conftest import require_tool

from dogear.config import default_config
from dogear.errors import ConfigError, ToolFailedError
from dogear.output.chapter import ChapterAudio
from dogear.output.loudness import (
    GainPlan,
    Loudness,
    LoudnessSettings,
    filter_chain,
    measure_loudness,
    normalize_chapters,
    normalize_filter,
    parse_ebur128_summary,
    plan_gain,
)

# The tail of what ffmpeg 6.1 logs for `ebur128=peak=true`.
SUMMARY = """
[Parsed_ebur128_0 @ 0x5d] Summary:

  Integrated loudness:
    I:         -21.7 LUFS
    Threshold: -31.7 LUFS

  Loudness range:
    LRA:         0.0 LU
    Threshold:   0.0 LUFS
    LRA low:     0.0 LUFS
    LRA high:    0.0 LUFS

  True peak:
    Peak:      -18.1 dBFS
"""


def settings(**changes) -> LoudnessSettings:
    base = LoudnessSettings(
        target_lufs=-18.0, ceiling_dbtp=-3.0, max_limiting_db=6.0, silence_threshold_lufs=-50.0
    )
    return dataclasses.replace(base, **changes)


def test_summary_is_parsed():
    assert parse_ebur128_summary("frame lines\n" + SUMMARY, "a.wav") == Loudness(-21.7, -18.1)


def test_summary_of_silence_reads_minus_infinity():
    text = SUMMARY.replace("-21.7 LUFS", "-70.0 LUFS").replace("-18.1 dBFS", "-inf dBFS")
    reading = parse_ebur128_summary(text, "a.wav")
    assert reading.integrated_lufs == -70.0
    assert reading.true_peak_dbtp == -math.inf


@pytest.mark.parametrize("text", ["", "no summary here", SUMMARY.replace("-18.1", "nan")])
def test_missing_or_odd_summary_fails_loudly(text):
    with pytest.raises(ToolFailedError, match="loudness of a.wav"):
        parse_ebur128_summary(text, "a.wav")


def test_plain_gain_reaches_target_both_ways():
    assert plan_gain(Loudness(-24.0, -10.0), settings()) == GainPlan(6.0, limit=False)
    assert plan_gain(Loudness(-10.0, -1.0), settings()) == GainPlan(-8.0, limit=False)


def test_peaks_over_ceiling_are_limited_when_within_budget():
    # +6 dB puts a -5 dBTP peak at +1, 4 dB over the ceiling: the limiter can take that.
    plan = plan_gain(Loudness(-24.0, -5.0), settings())
    assert plan == GainPlan(6.0, limit=True, shortfall_db=0.0)


def test_gain_is_lowered_when_peaks_need_more_limiting_than_allowed():
    # Wants +12 dB, but peaks may end at most 6 dB over -3, so the gain stops at +8.
    plan = plan_gain(Loudness(-30.0, -5.0), settings())
    assert plan.gain_db == pytest.approx(8.0)
    assert plan.shortfall_db == pytest.approx(4.0)
    assert plan.limit


def test_no_limiting_allowed_means_pure_gain_up_to_the_ceiling():
    plan = plan_gain(Loudness(-24.0, -5.0), settings(max_limiting_db=0.0))
    assert plan.gain_db == pytest.approx(2.0)
    assert plan.shortfall_db == pytest.approx(4.0)
    assert not plan.limit


@pytest.mark.parametrize("reading", [Loudness(-70.0, -math.inf), Loudness(-55.0, -40.0)])
def test_silence_and_near_silence_are_left_alone(reading):
    plan = plan_gain(reading, settings())
    assert plan == GainPlan(0.0, limit=False, silent=True)


def test_filter_chain_is_plain_volume_without_limiting():
    assert filter_chain(GainPlan(6.0, limit=False), settings(), 24000) == "volume=6.00dB"


def test_filter_chain_limits_at_four_times_the_rate_and_returns_to_it():
    chain = filter_chain(GainPlan(-2.5, limit=True), settings(), 22050).split(",")
    assert chain[0] == "volume=-2.50dB"
    assert chain[1] == "aresample=88200"
    assert chain[2].startswith("alimiter=limit=0.70795:")  # -3 dB
    assert "level=false" in chain[2] and "latency=true" in chain[2]
    assert chain[3] == "aresample=22050"


@pytest.mark.parametrize(
    ("key", "value", "reading"),
    [
        ("loudness_target_lufs", -23, Loudness(-30.0, -20.0)),  # an int is fine for a float
        ("true_peak_ceiling_dbtp", -6.0, Loudness(-24.0, -8.0)),
        ("max_limiting_db", 0.0, Loudness(-24.0, -5.0)),
        ("silence_threshold_lufs", -25.0, Loudness(-30.0, -20.0)),
    ],
)
def test_each_setting_is_read_from_config(key, value, reading):
    config = default_config()
    before = plan_gain(reading, LoudnessSettings.from_config(config))
    config["audio"][key] = value
    assert plan_gain(reading, LoudnessSettings.from_config(config)) != before


def test_ceiling_from_config_sets_the_limiter():
    config = default_config()
    config["audio"]["true_peak_ceiling_dbtp"] = -6.0
    chain = filter_chain(GainPlan(0.0, limit=True), LoudnessSettings.from_config(config), 24000)
    assert "alimiter=limit=0.50119:" in chain


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("true_peak_ceiling_dbtp", 1.0, "outside -24 to 0"),
        ("true_peak_ceiling_dbtp", -30.0, "outside -24 to 0"),
        ("loudness_target_lufs", -2.0, "must be lower than"),
        ("silence_threshold_lufs", -10.0, "must be lower"),
        ("max_limiting_db", -1.0, "can't be negative"),
    ],
)
def test_bad_settings_are_config_errors(key, value, message):
    config = copy.deepcopy(default_config())
    config["audio"][key] = value
    with pytest.raises(ConfigError, match=message) as err:
        LoudnessSettings.from_config(config)
    assert err.value.hint


def test_measure_reads_a_real_file(tmp_path, config):
    reading = measure_loudness(tone(tmp_path / "t.wav", 1.0), config)
    assert reading.integrated_lufs == pytest.approx(-21.7, abs=0.2)
    assert reading.true_peak_dbtp == pytest.approx(-18.1, abs=0.2)


def test_silent_chapter_is_logged_and_left_alone(tmp_path, config, caplog):
    require_tool("ffprobe")
    quiet = silence(tmp_path / "s.wav", 1.0)
    with caplog.at_level(logging.WARNING, logger="dogear.output.loudness"):
        chain = normalize_filter(
            quiet, "Chapter 2 of 5", LoudnessSettings.from_config(config), config
        )
    assert chain == "volume=0.00dB"
    assert "Chapter 2 of 5 is silent" in caplog.text


def frame_count(path) -> int:
    with wave.open(str(path), "rb") as w:
        return w.getnframes()


def test_normalizing_keeps_length_so_marks_stay_true(tmp_path, config):
    # Spiky audio goes through the limiter, which must not shift or stretch the audio.
    loud = spiky(tmp_path / "a.wav", 2.0)
    marks = (0, 12000, frame_count(loud))
    [chapter] = normalize_chapters([ChapterAudio("One", loud, marks, 24000)], tmp_path, config)
    assert (chapter.marks, chapter.sample_rate) == (marks, 24000)
    assert frame_count(chapter.path) == frame_count(loud)


def test_marks_follow_a_chapter_resampled_to_the_first_ones_rate(tmp_path, config):
    first = tone(tmp_path / "a.wav", 1.0, rate=24000)
    second = tone(tmp_path / "b.wav", 1.0, rate=48000)
    chapters = [
        ChapterAudio("One", first, (0, 24000), 24000),
        ChapterAudio("Two", second, (0, 9600, 48000), 48000),
    ]
    _, two = normalize_chapters(chapters, tmp_path, config)
    assert (two.marks, two.sample_rate) == ((0, 4800, 24000), 24000)
