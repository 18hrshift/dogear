"""Spoken structure: which words and pauses each kind of block becomes, per [narration]."""

import logging
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
from dogear.narration import Utterance, narrate_book


def book(*sections: Section, lang: str | None = None) -> Book:
    return Book(Metadata("A Book", language=lang), list(sections), Path("book.epub"), "epub")


def narrate(config, *blocks, title="The Storm", **section) -> list[Utterance]:
    """The utterances of a one-section book."""
    [narration] = narrate_book(book(Section(title, blocks=list(blocks), **section)), config)
    return narration.utterances


def spoken(utterances: list[Utterance]) -> list[str]:
    return [u.spoken for u in utterances if u.spoken]


def heard(utterances: list[Utterance]) -> list[tuple[str, int]]:
    """What is said and the silence after it, skipping the opening pause."""
    return [(u.spoken, u.pause_ms) for u in utterances[1:]]


@pytest.fixture
def pause(config):
    return config["narration"]["pauses"]


@pytest.fixture
def narration(config):
    return config["narration"]


# The shape of a section.


def test_a_section_from_start_to_end(config, pause):
    utterances = narrate(
        config,
        Heading(1, "Chapter 1"),
        Paragraph("It was dark. It rained."),
        Paragraph("Then it stopped."),
    )
    assert utterances[0] == Utterance("", "", pause["section_start_ms"])
    assert utterances[1] == Utterance("Chapter 1", "Chapter one.", pause["heading_ms"])
    assert heard(utterances)[1:] == [
        ("It was dark.", pause["sentence_ms"]),
        ("It rained.", pause["paragraph_ms"]),
        ("Then it stopped.", pause["section_end_ms"]),
    ]


def test_display_text_is_kept_beside_the_spoken_text(config):
    utterances = narrate(config, Paragraph("Dr. Jekyll paid $5."))
    assert [(u.text, u.spoken) for u in utterances if u.spoken][-1] == (
        "Dr. Jekyll paid $5.",
        "Doctor Jekyll paid five dollars.",
    )


def test_a_section_without_a_heading_says_its_title(config, pause):
    utterances = narrate(config, Paragraph("Rain fell."), title="The Storm")
    assert heard(utterances) == [
        ("The Storm.", pause["heading_ms"]),
        ("Rain fell.", pause["section_end_ms"]),
    ]
    assert utterances[1].text == "The Storm"


def test_a_heading_after_page_markers_still_counts_as_the_first_block(config):
    utterances = narrate(config, PageMarker("7"), Heading(1, "Storms"), Paragraph("Rain."))
    assert spoken(utterances) == ["Storms.", "Rain."]


def test_a_section_with_no_blocks_says_its_title(config, pause):
    assert heard(narrate(config, title="Blank Page")) == [("Blank Page.", pause["section_end_ms"])]


@pytest.mark.parametrize(
    ("heading", "said"),
    [
        ("Who Goes There?", "Who Goes There?"),
        ("Wait!", "Wait!"),
        ("Part I: Dawn", "Part one: Dawn."),
    ],
)
def test_headings_end_with_one_closing_mark(config, heading, said):
    assert spoken(narrate(config, Heading(2, heading)))[0] == said


def test_a_heading_after_text_gets_a_breath_before_it(config, pause):
    utterances = narrate(
        config, Heading(1, "One"), ListBlock(("a",)), Heading(2, "Two"), Paragraph("B.")
    )
    before_two = utterances[[u.spoken for u in utterances].index("Two.") - 1]
    assert before_two.pause_ms == pause["paragraph_ms"]


def test_sentences_and_paragraphs_get_their_pauses(config, pause):
    utterances = narrate(config, Heading(1, "H"), Paragraph("One. Two! Three?"), Paragraph("Four."))
    assert heard(utterances)[1:] == [
        ("One.", pause["sentence_ms"]),
        ("Two!", pause["sentence_ms"]),
        ("Three?", pause["paragraph_ms"]),
        ("Four.", pause["section_end_ms"]),
    ]


def test_a_scene_break_lengthens_the_pause_before_it(config, pause):
    utterances = narrate(
        config, Heading(1, "H"), Paragraph("Before."), SceneBreak(), Paragraph("After.")
    )
    assert heard(utterances)[1:] == [
        ("Before.", pause["scene_break_ms"]),
        ("After.", pause["section_end_ms"]),
    ]


def test_the_section_end_pause_is_last(config, pause):
    utterances = narrate(config, Paragraph("Only."), SceneBreak())
    assert utterances[-1].pause_ms == pause["section_end_ms"]
    assert utterances[-1].spoken == "Only."


def test_sections_are_numbered_from_one(config):
    narrations = narrate_book(
        book(Section("A", blocks=[Paragraph("x.")]), Section("B", blocks=[Paragraph("y.")])),
        config,
    )
    assert [(n.number, n.section.title) for n in narrations] == [(1, "A"), (2, "B")]
    assert narrations[0].words() == 2  # "A." and "x."


# Lists and tables.


def test_ordered_list_items_are_numbered(config, pause):
    utterances = narrate(
        config, Heading(1, "H"), ListBlock(("milk", "eggs"), ordered=True), Paragraph("Done.")
    )
    assert " ".join(spoken(utterances)) == "H. one. milk two. eggs Done."
    pauses = dict(heard(utterances))
    assert pauses["one. milk"] == pause["list_item_ms"]
    assert pauses["two. eggs"] == pause["paragraph_ms"]


def test_ordered_items_keep_their_numbers_before_capitals(config):
    utterances = narrate(config, ListBlock(("Buy milk.", "Get eggs."), ordered=True))
    assert " ".join(spoken(utterances)[1:]) == "one. Buy milk. two. Get eggs."


def test_unordered_list_items_are_not_numbered(config, pause):
    utterances = narrate(config, Heading(1, "H"), ListBlock(("Milk.", "Eggs.")), Paragraph("x."))
    assert heard(utterances)[1:3] == [
        ("Milk.", pause["list_item_ms"]),
        ("Eggs.", pause["paragraph_ms"]),
    ]


TABLE = Table(rows=(("Name", "Age"), ("Ann", "30"), ("Bob", "")), header_rows=1, caption="Ages")


def test_tables_are_read_row_by_row_with_header_labels(config, pause):
    utterances = narrate(config, Heading(1, "H"), TABLE, Paragraph("After."))
    assert heard(utterances)[1:4] == [
        ("Table: Ages.", pause["sentence_ms"]),
        ("Row one: Name: Ann; Age: thirty.", pause["list_item_ms"]),
        ("Row two: Name: Bob.", pause["paragraph_ms"]),  # empty cells are skipped
    ]


def test_a_table_without_headers_or_caption(config):
    table = Table(rows=(("Ann", "30"), ("Bob", "41")))
    assert spoken(narrate(config, Heading(1, "H"), table))[1:] == [
        "Table.",
        "Row one: Ann; thirty.",
        "Row two: Bob; forty-one.",
    ]


def test_a_header_cell_is_not_repeated_as_its_own_label(config):
    table = Table(rows=(("Item", "Done"), ("Pack", "Done")), header_rows=1)
    assert spoken(narrate(config, Heading(1, "H"), table))[-1] == "Row one: Item: Pack; Done."


def test_tables_can_be_skipped(config, narration, pause):
    narration["tables"] = "skip"
    utterances = narrate(config, Heading(1, "H"), TABLE, Paragraph("After."))
    assert heard(utterances)[1:3] == [
        ("Table: Ages.", pause["sentence_ms"]),
        ("Table not read.", pause["paragraph_ms"]),
    ]
    assert not any("Ann" in s for s in spoken(utterances))


# Images.


def image_words(config, image: Image) -> list[str]:
    return spoken(narrate(config, Heading(1, "H"), image, Paragraph("After.")))[1:-1]


def test_described_images_are_read(config):
    assert image_words(config, Image(alt="A map of London")) == ["Image: A map of London."]
    assert image_words(config, Image(alt="Who drew this?")) == ["Image: Who drew this?"]


def test_decorative_images_are_skipped(config, narration):
    narration["announce_undescribed_images"] = True
    assert image_words(config, Image(alt="")) == []


@pytest.mark.parametrize(("announce", "words"), [(False, []), (True, ["Image."])])
def test_undescribed_images_follow_the_setting(config, narration, announce, words):
    narration["announce_undescribed_images"] = announce
    assert image_words(config, Image(alt=None)) == words


@pytest.mark.parametrize(
    ("image", "words"),
    [
        (Image(alt=None, caption="Fig 1"), ["Image.", "Fig one."]),
        (Image(alt="", caption="The square"), ["Image.", "The square."]),
        (Image(alt="A square", caption="Soho."), ["Image: A square.", "Soho."]),
    ],
)
def test_captions_are_always_read(config, image, words):
    assert image_words(config, image) == words


def test_images_end_with_a_paragraph_pause(config, pause):
    utterances = narrate(config, Heading(1, "H"), Image(alt="A cat"), Paragraph("After."))
    assert dict(heard(utterances))["Image: A cat."] == pause["paragraph_ms"]


# Notes.

NOTE = Footnote("n1", "Written in 1886.", label="1")


def notes_book(*body_blocks, back_notes=(NOTE,)):
    return book(
        Section("One", blocks=list(body_blocks)),
        Section("Notes", kind="back", blocks=[Heading(1, "Notes"), *back_notes]),
    )


def test_notes_after_paragraph_are_read_right_after_it(config, pause):
    narrations = narrate_book(
        notes_book(Paragraph("He wrote it.", note_refs=("n1",)), Paragraph("Later.")),
        config,
    )
    [one] = narrations  # the notes section had nothing left to say
    assert heard(one.utterances)[1:] == [
        ("He wrote it.", pause["paragraph_ms"]),
        ("Note: Written in eighteen eighty-six.", pause["paragraph_ms"]),
        ("Later.", pause["section_end_ms"]),
    ]


def test_a_section_of_notes_already_read_is_left_out(config, caplog):
    with caplog.at_level(logging.INFO, logger="dogear.narration"):
        narrations = narrate_book(notes_book(Paragraph("He wrote it.", note_refs=("n1",))), config)
    assert [n.section.title for n in narrations] == ["One"]
    assert "Section 2, Notes, was left out" in caplog.text


def test_a_notes_section_with_an_unreferenced_note_is_kept(config):
    other = Footnote("n2", "Never referred to.")
    narrations = narrate_book(
        notes_book(Paragraph("He wrote it.", note_refs=("n1",)), back_notes=(NOTE, other)),
        config,
    )
    assert [n.section.title for n in narrations] == ["One", "Notes"]
    # The note read after its paragraph isn't read again; the other one is read here.
    assert spoken(narrations[1].utterances) == ["Notes.", "Note: Never referred to."]


@pytest.mark.parametrize("mode", ["where_printed", "end_of_section"])
def test_a_notes_section_is_kept_when_notes_are_not_read_after_paragraphs(config, narration, mode):
    narration["footnotes"] = mode
    narrations = narrate_book(notes_book(Paragraph("He wrote it.", note_refs=("n1",))), config)
    assert [n.section.title for n in narrations] == ["One", "Notes"]
    assert "Note: Written in eighteen eighty-six." in spoken(narrations[1].utterances)


def test_a_note_printed_in_the_same_section_is_read_once(config):
    utterances = narrate(
        config,
        Heading(1, "H"),
        Paragraph("He wrote it.", note_refs=("n1",)),
        Paragraph("Later."),
        NOTE,
    )
    assert spoken(utterances) == [
        "H.",
        "He wrote it.",
        "Note: Written in eighteen eighty-six.",
        "Later.",
    ]


def test_a_note_referred_to_twice_is_read_once(config):
    utterances = narrate(
        config,
        Heading(1, "H"),
        Paragraph("First.", note_refs=("n1",)),
        Paragraph("Second.", note_refs=("n1",)),
        NOTE,
    )
    assert [s for s in spoken(utterances) if s.startswith("Note")] == [
        "Note: Written in eighteen eighty-six."
    ]


def test_a_reference_to_a_missing_note_is_ignored(config):
    utterances = narrate(config, Heading(1, "H"), Paragraph("Text.", note_refs=("gone",)))
    assert spoken(utterances) == ["H.", "Text."]


def test_notes_where_printed(config, narration, pause):
    narration["footnotes"] = "where_printed"
    utterances = narrate(
        config,
        Heading(1, "H"),
        Paragraph("He wrote it.", note_refs=("n1",)),
        Paragraph("Later."),
        NOTE,
    )
    assert heard(utterances)[1:] == [
        ("He wrote it.", pause["paragraph_ms"]),
        ("Later.", pause["paragraph_ms"]),
        ("Note: Written in eighteen eighty-six.", pause["section_end_ms"]),
    ]


def test_notes_at_the_end_of_the_section(config, narration, pause):
    narration["footnotes"] = "end_of_section"
    second = Footnote("n2", "See chapter 2.")
    utterances = narrate(
        config,
        Heading(1, "H"),
        Paragraph("He wrote it.", note_refs=("n1",)),
        NOTE,
        Paragraph("Later.", note_refs=("n2",)),
        second,
    )
    assert heard(utterances)[1:] == [
        ("He wrote it.", pause["paragraph_ms"]),
        ("Later.", pause["paragraph_ms"]),
        ("Notes.", pause["heading_ms"]),
        ("Note: Written in eighteen eighty-six.", pause["paragraph_ms"]),
        ("Note: See chapter two.", pause["section_end_ms"]),
    ]


def test_notes_can_be_skipped(config, narration):
    narration["footnotes"] = "skip"
    utterances = narrate(
        config, Heading(1, "H"), Paragraph("He wrote it.", note_refs=("n1",)), NOTE
    )
    assert spoken(utterances) == ["H.", "He wrote it."]


def test_notes_follow_their_own_language(config):
    note = Footnote("n1", "Écrit en 1886.", lang="fr")
    utterances = narrate(config, Heading(1, "H"), Paragraph("Text.", note_refs=("n1",)), note)
    assert spoken(utterances)[-1] == "Note: Écrit en mille huit cent quatre-vingt-six."


# Pages.


def test_pages_are_silent_by_default(config):
    assert spoken(narrate(config, Heading(1, "H"), PageMarker("42"), Paragraph("Text."))) == [
        "H.",
        "Text.",
    ]


def test_pages_can_be_announced(config, narration, pause):
    narration["announce_pages"] = True
    utterances = narrate(config, Heading(1, "H"), PageMarker("42"), Paragraph("Text."))
    assert heard(utterances)[1] == ("Page forty-two.", pause["sentence_ms"])


# Languages.

FORTY_TWO = {
    "en": "I have forty-two cats.",
    "fr": "I have quarante-deux cats.",
    "de": "I have zweiundvierzig cats.",
    "es": "I have cuarenta y dos cats.",
}


@pytest.mark.parametrize(
    ("book_lang", "section_lang", "block_lang", "expected"),
    [
        (None, None, None, "en"),
        ("fr", None, None, "fr"),
        ("fr", "de", None, "de"),
        ("fr", "de", "es", "es"),
        (None, None, "es", "es"),
    ],
)
def test_block_language_beats_section_beats_book(
    config, book_lang, section_lang, block_lang, expected
):
    section = Section(
        "Title", lang=section_lang, blocks=[Paragraph("I have 42 cats.", lang=block_lang)]
    )
    [narration] = narrate_book(book(section, lang=book_lang), config)
    assert spoken(narration.utterances)[-1] == FORTY_TWO[expected]


def test_spoken_titles_use_the_section_language(config):
    section = Section("Chapitre 12", lang="fr", blocks=[Paragraph("Texte.")])
    [narration] = narrate_book(book(section, lang="en"), config)
    assert spoken(narration.utterances)[0] == "Chapitre douze."


# Settings change what is heard.


def test_pause_settings_change_the_pauses(config, pause):
    pause.update(
        sentence_ms=111,
        paragraph_ms=222,
        heading_ms=333,
        list_item_ms=144,
        scene_break_ms=555,
        section_start_ms=66,
        section_end_ms=777,
    )
    utterances = narrate(
        config,
        Heading(1, "H"),
        Paragraph("One. Two."),
        SceneBreak(),
        ListBlock(("a", "b")),
        Paragraph("End."),
    )
    assert utterances[0].pause_ms == 66
    assert heard(utterances) == [
        ("H.", 333),
        ("One.", 111),
        ("Two.", 555),
        ("a", 144),
        ("b", 222),
        ("End.", 777),
    ]


def test_word_settings_change_the_words(config, narration):
    narration["words"].update(
        image="Picture",
        note="Footnote",
        notes="Endnotes",
        table="Grid",
        row="Line",
        page="Leaf",
        table_skipped="Grid left out.",
    )
    narration["announce_pages"] = True
    narration["footnotes"] = "end_of_section"
    table = Table(rows=(("x",),))
    said = spoken(
        narrate(
            config,
            Heading(1, "H"),
            PageMarker("3"),
            Image(alt="A cat"),
            table,
            Paragraph("Text.", note_refs=("n1",)),
            NOTE,
        )
    )
    assert said == [
        "H.",
        "Leaf three.",
        "Picture: A cat.",
        "Grid.",
        "Line one: x.",
        "Text.",
        "Endnotes.",
        "Footnote: Written in eighteen eighty-six.",
    ]
    narration["tables"] = "skip"
    assert spoken(narrate(config, Heading(1, "H"), table))[1:] == ["Grid.", "Grid left out."]
