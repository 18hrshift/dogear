"""Talking-book text: items with ids, and syncs tying each spoken utterance to its audio."""

import re
from pathlib import Path

import pytest

from dogear.document import (
    Book,
    Footnote,
    Heading,
    Image,
    ListBlock,
    Metadata,
    PageMarker,
    Paragraph,
    SceneBreak,
    Section,
    Table,
)
from dogear.narration import narrate_book, narrate_title
from dogear.output.chapter import ChapterAudio
from dogear.readalong import build_readalong
from dogear.readalong.model import (
    BreakText,
    Clip,
    HeadingText,
    ImageText,
    ListText,
    NoteText,
    PageText,
    ParagraphText,
    TableText,
)
from dogear.readalong.outline import heading_levels, page_kind

XML_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*")


def book(*sections: Section, title="A Book", authors=()) -> Book:
    return Book(Metadata(title, authors=list(authors)), list(sections), Path("b.epub"), "epub")


def timed(narration) -> ChapterAudio:
    """Audio where utterance i starts at i seconds: one second per utterance."""
    count = len(narration.utterances)
    return ChapterAudio(narration.section.title, Path("a.wav"), tuple(range(count + 1)), 1)


def readalong(config, the_book, title_track=False):
    narrations = narrate_book(the_book, config)
    if title_track:
        narrations.insert(0, narrate_title(the_book, config))
    return build_readalong(narrations, [timed(n) for n in narrations], "en")


def ids(section) -> set[str]:
    """Every element id the section's text has."""
    found = set()
    for item in section.items:
        match item:
            case HeadingText(id=id_) | PageText(id=id_):
                found.add(id_)
            case ParagraphText(sentences=s) | NoteText(sentences=s):
                found.update(x.id for x in s)
            case ListText(items=items):
                found.update(x.id for item_ in items for x in item_)
            case ImageText(description=d, caption=c):
                found.update(x.id for x in d + c)
            case TableText(caption=c, rows=rows):
                found.update(x.id for x in c)
                found.update(r.id for r in rows if r.id)
    return found


CHAPTER = Section(
    "One",
    blocks=[
        Heading(1, "One"),
        PageMarker("7"),
        Paragraph("It rained. It poured."),
        ListBlock(("Milk.", "Eggs."), ordered=True),
        SceneBreak(),
        Table(rows=(("Name", "Age"), ("Ann", "30")), header_rows=1, caption="Ages"),
        Image(alt="A map.", caption="The town."),
    ],
)


def test_items_follow_the_narration(config):
    [section] = readalong(config, book(CHAPTER))
    kinds = [type(item) for item in section.items]
    assert kinds == [
        HeadingText,
        PageText,
        ParagraphText,
        ListText,
        BreakText,
        TableText,
        ImageText,
    ]
    paragraph, items = section.items[2], section.items[3]
    assert [s.text for s in paragraph.sentences] == ["It rained.", "It poured."]
    # A list shows its own numbers, so the text has none.
    assert [[s.text for s in item] for item in items.items] == [["Milk."], ["Eggs."]]
    assert items.ordered


def test_every_spoken_utterance_has_one_sync_in_order(config):
    [narration] = narrate_book(book(CHAPTER), config)
    [section] = readalong(config, book(CHAPTER))
    spoken = [i for i, u in enumerate(narration.utterances) if u.spoken]
    assert len(section.syncs) == len(spoken)
    assert [s.clip.begin for s in section.syncs] == [float(i) for i in spoken]


def test_clips_run_back_to_back_from_the_first_words_to_the_end(config):
    [section] = readalong(config, book(CHAPTER))
    clips = [s.clip for s in section.syncs]
    assert all(a.end == b.begin for a, b in zip(clips, clips[1:], strict=False))
    # The opening pause comes before the first words, so no clip includes it.
    assert clips[0].begin == 1.0
    assert clips[-1].end == float(section.audio.marks[-1])
    assert section.duration == clips[-1].end - 1.0


def test_sync_targets_exist_and_ids_are_unique_xml_ids(config):
    sections = readalong(config, book(CHAPTER, CHAPTER), title_track=True)
    seen: set[str] = set()
    for section in sections:
        section_ids = ids(section) | {s.id for s in section.syncs}
        assert not section_ids & seen
        seen |= section_ids
        assert all(XML_ID.fullmatch(i) for i in section_ids)
        targets = {s.target for s in section.syncs}
        assert targets <= ids(section)


def test_table_rows_are_synced_whole_and_headers_are_not(config):
    [section] = readalong(config, book(CHAPTER))
    table = section.items[5]
    assert [s.text for s in table.caption] == ["Table: Ages."]
    assert [r.id for r in table.header_rows] == [None]
    [row] = table.rows
    assert row.cells == ("Ann", "30") and row.id
    assert row.id in {s.target for s in section.syncs}


def test_a_skipped_table_shows_its_rows_without_syncing_them(config):
    config["narration"]["tables"] = "skip"
    [section] = readalong(config, book(CHAPTER))
    table = section.items[5]
    assert [s.text for s in table.caption] == ["Table: Ages.", "Table not read."]
    assert [r.id for r in table.rows] == [None]


def test_a_silent_page_points_at_what_is_said_next(config):
    [section] = readalong(config, book(CHAPTER))
    page = section.items[1]
    assert (page.label, page.kind) == ("7", "normal")
    first_sentence = section.items[2].sentences[0].id
    assert section.syncs[page.sync].target == first_sentence


def test_an_announced_page_is_synced_to_its_own_marker(config):
    config["narration"]["announce_pages"] = True
    [section] = readalong(config, book(CHAPTER))
    page = section.items[1]
    assert section.syncs[page.sync].target == page.id


def test_a_page_with_nothing_after_it_has_no_sync(config):
    ending = Section("End", blocks=[Heading(1, "End"), Paragraph("Bye."), PageMarker("9")])
    [section] = readalong(config, book(ending))
    assert section.pages()[0].sync is None


def test_notes_keep_their_label_and_language(config):
    note = Footnote("n1", "Ecrit en 1886.", label="1", lang="fr")
    chapter = Section("One", blocks=[Heading(1, "One"), Paragraph("Text.", note_refs=("n1",))])
    notes = Section("Notes", kind="back", blocks=[note])
    [section] = readalong(config, book(chapter, notes))
    [item] = [i for i in section.items if isinstance(i, NoteText)]
    assert (item.label, item.lang) == ("1", "fr")
    assert item.sentences[0].text.startswith("Note: ")


def test_heading_levels_are_settled_across_the_book(config):
    chapters = [
        Section("One", blocks=[Heading(2, "One"), Heading(4, "Deep"), Paragraph("x.")]),
        Section("Two", blocks=[Heading(2, "Two"), Paragraph("y.")]),
    ]
    sections = readalong(config, book(*chapters, title="T"), title_track=True)
    levels = [[h.level for h in s.headings()] for s in sections]
    # The title track is level 1; chapters at level 2 in the book become level 1 beside
    # it, and the level 4 heading under a chapter becomes 2.
    assert levels == [[1], [1, 2], [1]]


def test_section_language_and_kind_carry_over(config):
    appendix = Section("Notes", kind="back", lang="en-GB", blocks=[Paragraph("x.")])
    [section] = readalong(config, book(appendix))
    assert (section.kind, section.lang, section.title, section.number) == (
        "back",
        "en-GB",
        "Notes",
        1,
    )


def test_audio_without_timings_is_refused(config):
    narrations = narrate_book(book(CHAPTER), config)
    with pytest.raises(ValueError, match="no timings"):
        build_readalong(narrations, [ChapterAudio("One", Path("a.wav"))], "en")


def test_narrations_and_audio_must_pair_up(config):
    narrations = narrate_book(book(CHAPTER), config)
    with pytest.raises(ValueError, match="1 narrations but 0"):
        build_readalong(narrations, [], "en")


def test_clips_are_in_seconds_at_the_audio_sample_rate(config):
    [narration] = narrate_book(book(CHAPTER), config)
    marks = tuple(i * 24000 for i in range(len(narration.utterances) + 1))
    audio = ChapterAudio("One", Path("a.wav"), marks, 24000)
    [section] = build_readalong([narration], [audio], "en")
    assert section.syncs[0].clip == Clip(1.0, 2.0)


@pytest.mark.parametrize(
    "levels, expected",
    [
        ([1, 2, 3], [1, 2, 3]),
        ([2, 2, 3], [1, 1, 2]),  # no level 1 anywhere: everything moves up
        ([1, 3, 3, 1], [1, 2, 2, 1]),  # a level never used is closed up
        ([3, 1, 2], [1, 1, 2]),  # the first heading is always level 1
        ([1, 2, 5, 6], [1, 2, 3, 4]),
        ([], []),
    ],
)
def test_heading_levels(levels, expected):
    assert heading_levels(levels) == expected


def test_heading_levels_pull_up_jumps_the_book_also_uses_shallower():
    # 1 and 3 are both used with 2 in between elsewhere, so 3 keeps its rank but can't
    # follow 1 directly.
    assert heading_levels([1, 2, 1, 3]) == [1, 2, 1, 2]


@pytest.mark.parametrize(
    "label, kind",
    [("42", "normal"), ("xii", "front"), ("XIV", "front"), ("A-3", "special"), ("4a", "special")],
)
def test_page_kinds(label, kind):
    assert page_kind(label) == kind


def test_an_utterance_that_came_out_silent_gets_no_sync(config):
    chapter = Section("One", blocks=[Heading(1, "One"), Paragraph("Hush. Then words.")])
    [narration] = narrate_book(book(chapter), config)
    hush = next(i for i, u in enumerate(narration.utterances) if u.text == "Hush.")
    # One second per utterance, except none for "Hush.": no audio and no pause after it.
    marks = [i if i <= hush else i - 1 for i in range(len(narration.utterances) + 1)]
    audio = ChapterAudio("One", Path("a.wav"), tuple(marks), 1)
    [section] = build_readalong([narration], [audio], "en")
    hush_id = section.items[1].sentences[0].id
    assert hush_id not in {s.target for s in section.syncs}
    assert all(s.clip.end > s.clip.begin for s in section.syncs)


def test_a_silent_heading_points_at_what_follows(config):
    chapter = Section("One", blocks=[Heading(1, "One"), Paragraph("Words.")])
    [narration] = narrate_book(book(chapter), config)
    heading = next(i for i, u in enumerate(narration.utterances) if u.text == "One")
    marks = [0 if i <= heading + 1 else i for i in range(len(narration.utterances) + 1)]
    audio = ChapterAudio("One", Path("a.wav"), tuple(marks), 1)
    [section] = build_readalong([narration], [audio], "en")
    [title] = section.headings()
    assert section.syncs[title.sync].target == section.items[1].sentences[0].id


def test_a_section_with_no_audio_at_all_is_refused(config):
    [narration] = narrate_book(book(CHAPTER), config)
    audio = ChapterAudio("One", Path("a.wav"), (0,) * (len(narration.utterances) + 1), 1)
    with pytest.raises(ValueError, match="came out silent"):
        build_readalong([narration], [audio], "en")


def test_announced_pages_are_marked_so_players_can_skip_them(config):
    config["narration"]["announce_pages"] = True
    [section] = readalong(config, book(CHAPTER))
    page = section.items[1]
    assert [s.target for s in section.syncs if s.page] == [page.id]
