"""Footnotes at the foot of PDF pages: hand-placed lines for the rules, then PDFs."""

from dataclasses import replace

import pytest
from pdf_builder import ALICE, INDENT, MARGIN, TEXT_WIDTH, PdfBuilder, marked, wrap
from pdf_lines import body_lines, layout_for, ln

from dogear.document import Footnote, PageMarker, Paragraph
from dogear.extract.pdf import extract
from dogear.extract.pdf_notes import find_notes, link_note_refs, marker_label, note_lines
from dogear.extract.pdf_text import Line, Page, remove_spans

OH_DEAR = "“Oh dear! Oh dear! I shall be late!”"


@pytest.fixture
def layout(config):
    return layout_for(config)


def with_mark(text: str, marker: str) -> Line:
    """A body line ending in a raised marker, such as "well¹"."""
    full = f"{text}{marker}"
    return replace(ln(full, 72, x1=540), raised=((len(text), len(full)),))


def note(text: str, top: float) -> Line:
    return ln(text, top, size=8)


def page(index: int, *lines: Line) -> Page:
    return Page(index, str(index + 1), tuple(lines))


def texts(lines) -> list[str]:
    return [line.text for line in lines]


# Finding notes


def test_note_block_found_and_split(layout):
    body = [with_mark("the well was very deep", "1"), *body_lines(86, 3)]
    notes = [note("1 Down, down, down.", 700), note("2 Would the fall never", 710)]
    notes.append(note("come to an end?", 720))
    [found] = find_notes([page(0, *body, *notes)], layout)
    assert texts(found.lines) == texts(body)
    assert [(n.note_id, n.label, texts(n.lines)) for n in found.notes] == [
        ("page1-note1", "1", ["Down, down, down."]),
        ("page1-note2", "2", ["Would the fall never", "come to an end?"]),
    ]


def test_raised_markers_in_the_notes_are_evidence_enough(layout):
    first = replace(note("*Down, down, down.", 700), raised=((0, 1),))
    [found] = find_notes([page(0, *body_lines(72, 3), first)], layout)
    assert [(n.label, texts(n.lines)) for n in found.notes] == [("*", ["Down, down, down."])]


def test_small_type_without_evidence_stays_text(layout):
    # Numbered lines in small type, but nothing on the page points at them.
    lines = [*body_lines(72, 3), note("1 Down, down, down.", 700), note("2 Down.", 710)]
    [found] = find_notes([page(0, *lines)], layout)
    assert texts(found.lines) == texts(lines)
    assert found.notes == ()


def test_a_page_all_in_small_type_has_no_notes(layout):
    lines = [note("1 an index entry", 72 + i * 10) for i in range(5)]
    assert find_notes([page(0, *lines)], layout)[0].lines == tuple(lines)


def test_numbered_notes_count_up(layout):
    # "1865" can't be a marker (too long), but "12" could; it isn't note 2, so it stays
    # in note 1.
    lines = [
        with_mark("the well was very deep", "1"),
        note("1 Down, down, down. There were", 700),
        note("12 lamps hanging from the roof.", 710),
    ]
    [found] = find_notes([page(0, *lines)], layout)
    assert [texts(n.lines) for n in found.notes] == [
        ["Down, down, down. There were", "12 lamps hanging from the roof."]
    ]


def test_note_carried_on_to_the_next_page(layout):
    first = page(0, with_mark("the well was very deep", "1"), note("1 Down, down,", 700))
    second = page(
        1,
        with_mark("so she went on", "2"),
        note("down. Would the fall never come to an end?", 690),
        note("2 Down.", 700),
    )
    one, two = find_notes([first, second], layout)
    assert [texts(n.lines) for n in one.notes] == [
        ["Down, down,", "down. Would the fall never come to an end?"]
    ]
    assert [(n.note_id, texts(n.lines)) for n in two.notes] == [("page2-note1", ["Down."])]
    assert texts(two.lines) == ["so she went on2"]


def test_small_type_after_a_finished_note_is_not_carried_on(layout):
    first = page(0, with_mark("the well was very deep", "1"), note("1 Down, down, down.", 700))
    second = page(1, *body_lines(72, 2), note("A quotation set small.", 700))
    one, two = find_notes([first, second], layout)
    assert texts(one.notes[0].lines) == ["Down, down, down."]
    assert texts(two.lines)[-1] == "A quotation set small."


# Linking references


def test_references_linked_and_markers_removed(layout):
    lines = [with_mark("the well was very deep", "1"), with_mark("x squared is x", "2")]
    found = find_notes([page(0, *lines, note("1 Down, down, down.", 700))], layout)
    [linked] = link_note_refs(found)
    first, second = linked.lines
    assert (first.text, first.note_refs) == ("the well was very deep", ("page1-note1",))
    # "2" matches no note on the page, so it stays: it may be an exponent.
    assert (second.text, second.note_refs) == ("x squared is x2", ())


def test_superscript_digit_characters_match_plain_ones():
    assert marker_label("¹²") == "12"
    assert marker_label(" * ") == "*"


@pytest.mark.parametrize(
    ("text", "span", "expected"),
    [
        ("the well¹ was deep", (8, 9), "the well was deep"),
        ("the well ¹ was deep", (9, 10), "the well was deep"),
        ("the well ¹", (9, 10), "the well"),
        ("¹The well", (0, 1), "The well"),
    ],
)
def test_remove_spans(text, span, expected):
    line = replace(ln(text, 0), raised=(span,))
    assert remove_spans(line, [span]).text == expected


def test_remove_spans_moves_the_other_spans():
    line = replace(ln("a¹ b² c", 0), raised=((1, 2), (4, 5)))
    kept = remove_spans(line, [(1, 2)])
    assert (kept.text, kept.raised) == ("a b² c", ((3, 4),))
    assert kept.chars == line.chars - 1


# End to end


def notes_page(path, *, raised=False):
    pdf = PdfBuilder(path)
    pdf.paragraph(marked(ALICE[0], "reading,", "1"))
    pdf.paragraph(marked(ALICE[1], "daisy-chain", "2"))
    pdf.footnotes([("1", ALICE[4]), ("2", OH_DEAR)], raised=raised)
    return pdf.save()


def blocks(path, config):
    [section] = extract(path, config).sections
    return section.blocks


@pytest.mark.parametrize("raised", [False, True])
def test_footnotes_read_as_notes(tmp_path, config, raised):
    assert blocks(notes_page(tmp_path / "notes.pdf", raised=raised), config) == [
        PageMarker("1"),
        Paragraph(ALICE[0], note_refs=("page1-note1",)),
        Paragraph(ALICE[1], note_refs=("page1-note2",)),
        Footnote("page1-note1", ALICE[4], label="1"),
        Footnote("page1-note2", OH_DEAR, label="2"),
    ]


def test_note_symbols(tmp_path, config):
    pdf = PdfBuilder(tmp_path / "symbols.pdf")
    pdf.paragraph(marked(ALICE[0], "reading,", "*"))
    pdf.paragraph(marked(ALICE[1], "daisy-chain", "†"))
    pdf.footnotes([("*", ALICE[4]), ("†", OH_DEAR)])
    found = [b for b in blocks(pdf.save(), config) if isinstance(b, Footnote)]
    assert [(n.label, n.text) for n in found] == [("*", ALICE[4]), ("†", OH_DEAR)]


def test_note_and_paragraph_carried_on_to_the_next_page(tmp_path, config):
    lines = wrap(ALICE[3], [TEXT_WIDTH - INDENT])
    assert not lines[1].endswith(".")
    head, tail = (
        "Either the well was very deep, or she fell very slowly, for she had",
        (
            "plenty of time as she went down to look about her and to wonder what was going to "
            "happen next."
        ),
    )
    pdf = PdfBuilder(tmp_path / "across.pdf")
    pdf.paragraph(marked(ALICE[0], "reading,", "1"))
    pdf.line(lines[0], x=MARGIN + INDENT)
    pdf.line(lines[1])
    pdf.footnotes([("1", head)])
    pdf.new_page()
    for line in lines[2:]:
        pdf.line(line)
    pdf.paragraph(marked(ALICE[2], "itself,", "2"))
    pdf.footnotes([(None, tail), ("2", OH_DEAR)])
    assert blocks(pdf.save(), config) == [
        PageMarker("1"),
        Paragraph(ALICE[0], note_refs=("page1-note1",)),
        PageMarker("2"),
        Paragraph(ALICE[3]),  # no longer cut in two by the notes between its halves
        Footnote("page1-note1", ALICE[4], label="1"),
        Paragraph(ALICE[2], note_refs=("page2-note1",)),
        Footnote("page2-note1", OH_DEAR, label="2"),
    ]


def test_note_ids_are_unique_in_the_book(tmp_path, config):
    pdf = PdfBuilder(tmp_path / "two.pdf")
    for text in ALICE[:2]:
        pdf.paragraph(marked(text, "Alice" if "Alice" in text else "she", "1"))
        pdf.footnotes([("1", OH_DEAR)])
        pdf.new_page()
    found = [b for b in blocks(pdf.save(), config) if isinstance(b, Footnote)]
    assert [n.note_id for n in found] == ["page1-note1", "page2-note1"]


def test_notes_with_page_numbers_below_them(tmp_path, config):
    pdf = PdfBuilder(tmp_path / "numbered.pdf", footer=lambda page: str(page + 1))
    for n in range(3):
        pdf.paragraph(marked(ALICE[n], "Alice" if "Alice" in ALICE[n] else "she", "1"))
        pdf.footnotes([("1", OH_DEAR)])
        pdf.new_page()
    found = [b for b in blocks(pdf.save(), config) if isinstance(b, Footnote)]
    assert [n.text for n in found] == [OH_DEAR] * 3


def test_note_marker_rise_ratio_comes_from_config(tmp_path, config):
    path = notes_page(tmp_path / "notes.pdf")
    config["pdf"]["note_marker_rise_ratio"] = 2.0  # higher than the markers are raised
    found = blocks(path, config)
    assert not any(isinstance(b, Footnote) for b in found)
    texts = [b.text for b in found if isinstance(b, Paragraph)]
    assert "reading,1 but" in texts[0]  # the marker is read as text
    assert texts[-1] == f"1 {ALICE[4]} 2 {OH_DEAR}"  # and so are the notes


def test_note_lines_stop_above_a_page_number_set_apart(layout):
    lines = (
        with_mark("the well was very deep", "1"),
        note("1 Down, down, down. Would the fall", 700),
        note("never come to an end?", 710),
        ln("12", 745, size=9),
    )
    assert texts(note_lines(page(0, *lines), layout)) == [
        "1 Down, down, down. Would the fall",
        "never come to an end?",
    ]


def test_note_lines_need_the_page_to_point_at_them(layout):
    assert note_lines(page(0, *body_lines(72, 2), note("1 Down, down, down.", 700)), layout) == []
