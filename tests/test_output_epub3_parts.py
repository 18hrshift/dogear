"""The pieces of an EPUB talking book on their own: SMIL timing, the contents' nesting,
and language tags."""

from pathlib import Path

import pytest
from epub3_reader import NS

from dogear.output.chapter import ChapterAudio
from dogear.output.epub3_nav import TextDocument, navigation_document
from dogear.output.epub3_smil import clock, media_overlay
from dogear.output.language_tag import language_tag
from dogear.readalong.model import Clip, HeadingText, ParagraphText, SectionText, Sentence, Sync


def section(*syncs: Sync, items=()) -> SectionText:
    audio = ChapterAudio("One", Path("a.mp3"))
    return SectionText(1, "One", "body", "en", tuple(items), syncs, audio)


@pytest.mark.parametrize(
    ("ms", "value"),
    [
        (0, "0:00:00.000"),
        (1337, "0:00:01.337"),
        (3_723_004, "1:02:03.004"),
        (90_000_000, "25:00:00.000"),
    ],
)
def test_clock_values(ms, value):
    assert clock(ms) == value


def test_a_clip_under_a_millisecond_is_left_out():
    syncs = (
        Sync("p1", "a", Clip(0.0, 1.0)),
        Sync("p2", "b", Clip(1.0, 1.0004)),
        Sync("p3", "c", Clip(1.0004, 2.0)),
    )
    overlay = media_overlay(section(*syncs), "one.xhtml", "one.mp3", {"a", "b", "c"})
    pars = overlay.smil.xpath("//smil:par/@id", namespaces=NS)
    assert pars == ["p1", "p3"] and overlay.milliseconds == 2000
    audio = overlay.smil.xpath("//smil:audio", namespaces=NS)
    assert audio[0].get("clipEnd") == audio[1].get("clipBegin") == "0:00:01.000"


def test_an_overlay_pointing_at_missing_text_is_refused():
    with pytest.raises(ValueError, match="points at b, which isn't in the section's text"):
        media_overlay(section(Sync("p1", "b", Clip(0, 1))), "one.xhtml", "one.mp3", {"a"})


def test_an_empty_clip_is_refused():
    with pytest.raises(ValueError, match="empty clip"):
        media_overlay(section(Sync("p1", "a", Clip(2, 1))), "one.xhtml", "one.mp3", {"a"})


def test_an_overlay_with_nothing_to_play_is_refused():
    tiny = Sync("p1", "a", Clip(1.0, 1.0002))
    with pytest.raises(ValueError, match="no audio in step"):
        media_overlay(section(tiny), "one.xhtml", "one.mp3", {"a"})


def headings(*levels: int) -> TextDocument:
    items = [HeadingText(f"h{n}", level, f"H{n}", 0) for n, level in enumerate(levels)]
    items.append(ParagraphText((Sentence("s", "Text."),)))
    return TextDocument(section(items=items), "one.xhtml", "en")


@pytest.mark.parametrize("levels", [(2,), (1, 3)])
def test_contents_refuse_a_skipped_level(levels):
    with pytest.raises(ValueError, match="levels must not skip"):
        navigation_document([headings(*levels)], "en")


def test_contents_climb_back_up_any_number_of_levels():
    nav = navigation_document([headings(1, 2, 3, 4, 1)], "en")
    top = nav.xpath("//x:nav[@id='toc']/x:ol/x:li/x:a/text()", namespaces=NS)
    assert top == ["H0", "H4"]
    assert nav.xpath("count(//x:nav[@id='toc']//x:ol)", namespaces=NS) == 4


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("en", "en"),
        ("en-GB", "en-GB"),
        ("en_US", "en-US"),
        (" fr ", "fr"),
        ("zh-Hant-TW", "zh-Hant-TW"),
        ("haw", "haw"),
        ("English", None),
        ("xx", None),  # not a language
        ("und", None),  # "undetermined"
        ("en--GB", None),
        ("", None),
        (None, None),
    ],
)
def test_language_tags(tag, expected):
    assert language_tag(tag) == expected
