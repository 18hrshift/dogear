"""The talking book's accessibility claims follow from what is in it, and claim no more."""

import pytest
from readalong_builder import metadata, talking_book

from dogear.document import Heading, Image, PageMarker, Paragraph, Section, Table
from dogear.output.epub3_a11y import accessibility_metadata, page_source

PLAIN = Section("One", blocks=[Heading(1, "One"), Paragraph("Words. More words.")])
PAGED = Section("Two", blocks=[Heading(1, "Two"), PageMarker("12"), Paragraph("Text.")])
TABLED = Section(
    "Three",
    blocks=[Heading(1, "Three"), Table(rows=(("Name", "Age"), ("Ann", "30")), header_rows=1)],
)
PICTURED = Section("Four", blocks=[Heading(1, "Four"), Image(alt="A map.")])
VOICE = "af_heart, a synthetic Kokoro voice"


def claims(config, tmp_path, *sections, book_metadata=None) -> dict[str, list[str]]:
    built, meta = talking_book(config, tmp_path, *sections, book_metadata=book_metadata)
    found: dict[str, list[str]] = {}
    for name, value in accessibility_metadata(built, meta, VOICE):
        found.setdefault(name, []).append(value)
    return found


def test_a_fully_read_book_claims_complete_audio_in_step_with_the_text(config, tmp_path):
    found = claims(config, tmp_path, PLAIN, TABLED)
    assert found["schema:accessMode"] == ["textual", "auditory"]
    assert found["schema:accessModeSufficient"] == ["textual", "auditory"]
    assert found["schema:accessibilityFeature"] == [
        "tableOfContents",
        "readingOrder",
        "structuralNavigation",
        "synchronizedAudioText",
    ]
    assert found["schema:accessibilityHazard"] == ["none"]
    [summary] = found["schema:accessibilitySummary"]
    assert VOICE in summary and "not been evaluated" in summary


def test_skipped_tables_mean_the_audio_isnt_complete(config, tmp_path):
    config["narration"]["tables"] = "skip"
    found = claims(config, tmp_path, PLAIN, TABLED)
    assert found["schema:accessModeSufficient"] == ["textual"]
    assert "synchronizedAudioText" not in found["schema:accessibilityFeature"]
    assert "Tables were left out of the narration." in found["schema:accessibilitySummary"][0]


def test_a_table_of_headers_only_is_shown_but_not_read(config, tmp_path):
    headers = Section("H", blocks=[Heading(1, "H"), Table(rows=(("A", "B"),), header_rows=1)])
    found = claims(config, tmp_path, headers)
    assert found["schema:accessModeSufficient"] == ["textual"]


def test_pictures_are_words_so_no_visual_mode_or_alternative_text_is_claimed(config, tmp_path):
    found = claims(config, tmp_path, PICTURED)
    assert "visual" not in found["schema:accessMode"]
    assert "alternativeText" not in found["schema:accessibilityFeature"]
    assert "Pictures are not included" in found["schema:accessibilitySummary"][0]


def test_page_numbers_bring_page_claims_and_their_source(config, tmp_path):
    book = metadata(identifier="urn:isbn:9780000000002")
    found = claims(config, tmp_path, PAGED, book_metadata=book)
    features = found["schema:accessibilityFeature"]
    assert "pageBreakMarkers" in features and "pageNavigation" in features
    assert found["pageBreakSource"] == ["urn:isbn:9780000000002"]
    assert "Print page numbers" in found["schema:accessibilitySummary"][0]


def test_no_page_claims_without_pages(config, tmp_path):
    found = claims(config, tmp_path, PLAIN)
    assert "pageNavigation" not in found["schema:accessibilityFeature"]
    assert "pageBreakSource" not in found


@pytest.mark.parametrize(
    ("fields", "source"),
    [
        ({"identifier": " isbn-42 "}, "isbn-42"),
        ({"identifier": None, "authors": ["Ann", "Bob"]}, "A Book, by Ann, Bob"),
        ({"identifier": "", "authors": []}, "A Book"),
    ],
)
def test_the_page_source_falls_back_to_title_and_authors(fields, source):
    assert page_source(metadata(**fields)) == source


def test_no_conformance_is_claimed(config, tmp_path):
    found = claims(config, tmp_path, PLAIN, PAGED)
    assert not {"dcterms:conformsTo", "a11y:certifiedBy"} & set(found)
