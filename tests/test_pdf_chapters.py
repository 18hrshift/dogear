"""Chapter detection methods and back-matter rules, tested on hand-made pages."""

import pytest

from dogear.errors import ConfigError
from dogear.extract.pdf_chapters import (
    CHAPTER_DIVIDER,
    METHODS,
    Boundary,
    ChapterSource,
    by_bookmarks,
    by_chapter_dividers,
    by_font_size,
    by_page_split,
    by_pattern,
    detect_chapters,
    is_back_matter_heading,
    mark_back_matter,
)
from dogear.extract.pdf_text import Layout, Line, Page

LAYOUT = Layout(body_size=11.0, heading_size=15.4, line_pitch=14.0, gap_ratio=1.3, indent=7.7)


def page(index: int, *texts: str, size: float = 11.0) -> Page:
    """A page whose first line is `texts[0]` in `size` type, then body lines."""
    lines = [
        Line(t, 72 + i * 14, 83 + i * 14, 72, 540, size if i == 0 else 11.0, len(t))
        for i, t in enumerate(texts)
    ]
    return Page(index=index, label=str(index + 1), lines=tuple(lines))


def source(pages, outline=(), page_split_size=20) -> ChapterSource:
    """`outline` holds bookmark levels, top level first."""
    return ChapterSource(pages, [list(level) for level in outline], LAYOUT, page_split_size)


@pytest.mark.parametrize(
    "text",
    ["Chapter 3", "CHAPTER XII", "Chapter iv", "Chapter Ten", "chapter twenty-one", "Chapter 7."],
)
def test_chapter_divider_matches(text):
    assert CHAPTER_DIVIDER.fullmatch(text)


@pytest.mark.parametrize(
    "text", ["Chapter 3: The Storm", "Chapters 1", "In Chapter 3", "Chapter mild", "Chapter"]
)
def test_chapter_divider_rejects(text):
    assert not CHAPTER_DIVIDER.fullmatch(text)


def test_bookmarks_sorted_and_deduped():
    pages = [page(i, "text") for i in range(10)]
    outline = [[(6, "Two"), (2, "One"), (6, "Two again"), (40, "Out of range")]]
    assert by_bookmarks(source(pages, outline)) == [Boundary(2, "One"), Boundary(6, "Two")]


CHAPTERS = [(0, "Chapter 1"), (3, "Chapter 2"), (6, "Chapter 3"), (8, "Chapter 4")]


def test_single_top_level_bookmark_uses_its_chapters():
    pages = [page(i, "text") for i in range(10)]
    outline = [[(0, "Alice in Wonderland")], CHAPTERS, [(1, "A section")]]
    assert by_bookmarks(source(pages, outline)) == [Boundary(p, t) for p, t in CHAPTERS]


def test_two_parts_holding_chapters_stay_parts():
    pages = [page(i, "text") for i in range(10)]
    outline = [[(0, "Part I"), (6, "Part II")], CHAPTERS]
    assert by_bookmarks(source(pages, outline)) == [Boundary(0, "Part I"), Boundary(6, "Part II")]


def test_top_level_on_one_page_uses_the_next_level():
    pages = [page(i, "text") for i in range(10)]
    outline = [[(0, "Cover"), (0, "Title page")], CHAPTERS]
    assert [b.title for b in by_bookmarks(source(pages, outline))] == [t for _, t in CHAPTERS]


def test_no_bookmark_level_with_two_pages():
    pages = [page(i, "text") for i in range(10)]
    assert by_bookmarks(source(pages, [[(0, "Book")], [(0, "Only chapter")]])) == []
    assert by_bookmarks(source(pages, [])) == []


def test_chapter_dividers():
    pages = [
        page(0, "Contents"),
        page(1, "Chapter One", "It began."),
        page(2, "more text"),
        page(3, "CHAPTER II", "It went on."),
        page(4, "Chapter 3: Not a divider"),
    ]
    found = by_chapter_dividers(source(pages))
    assert found == [Boundary(1, "Chapter One"), Boundary(3, "CHAPTER II")]


def test_font_size_takes_heading_text_as_title():
    pages = [
        page(0, "Down the Rabbit-Hole", "Alice was", size=22),
        page(1, "body text"),
        page(2, "The Pool of Tears", "Curiouser", size=22),
    ]
    found = by_font_size(source(pages))
    assert found == [Boundary(0, "Down the Rabbit-Hole"), Boundary(2, "The Pool of Tears")]


def test_pattern_looks_at_the_first_lines():
    pages = [
        page(0, "an epigraph", "Prologue", "text"),
        page(1, "a", "b", "c", "d", "e", "Chapter 9 is too far down"),
        page(2, "Part Two", "text"),
    ]
    assert by_pattern(source(pages)) == [Boundary(0, "Prologue"), Boundary(2, "Part Two")]


def test_repeated_title_on_following_pages_is_one_section():
    pages = [page(0, "Chapter 1"), page(1, "Chapter 1"), page(2, "Chapter 2")]
    assert [b.page for b in by_chapter_dividers(source(pages))] == [0, 2]


def test_page_split():
    pages = [page(i, "text") for i in range(5)]
    found = by_page_split(source(pages, page_split_size=2))
    assert found == [Boundary(0, "Part 1"), Boundary(2, "Part 2"), Boundary(4, "Part 3")]


def test_cascade_takes_the_first_method_with_two_sections():
    pages = [page(0, "Chapter 1", size=22), page(1, "x"), page(2, "Chapter 2", size=22)]
    outline = [[(0, "One"), (2, "Two")]]
    assert detect_chapters(["bookmarks", "font_size"], source(pages, outline))[0] == "bookmarks"
    assert detect_chapters(["font_size", "bookmarks"], source(pages, outline))[0] == "font_size"
    assert detect_chapters(["pattern"], source(pages[:2])) is None  # only one found


def test_page_split_accepted_with_one_part():
    pages = [page(0, "text"), page(1, "text")]
    assert detect_chapters(["bookmarks", "page_split"], source(pages)) == (
        "page_split",
        [Boundary(0, "Part 1")],
    )


def test_unknown_method():
    with pytest.raises(ConfigError) as caught:
        detect_chapters(["bookmarks", "magic"], source([page(0, "x")]))
    assert "magic" in caught.value.message
    for name in METHODS:
        assert name in caught.value.hint


def test_no_methods():
    with pytest.raises(ConfigError):
        detect_chapters([], source([page(0, "x")]))


@pytest.mark.parametrize(
    "text", ["Notes", "Index", "About the Author", "ACKNOWLEDGMENTS", "Appendix A: Tables"]
)
def test_back_matter_headings(text):
    assert is_back_matter_heading(text)


@pytest.mark.parametrize(
    "text",
    [
        "notes were passed between them",  # lowercase: carries on a sentence
        "Notes from the field were scattered across the desk in great untidy piles",
        "Conclusion",  # part of the book's argument, read as body
    ],
)
def test_not_back_matter_headings(text):
    assert not is_back_matter_heading(text)


def test_back_matter_boundaries_classified():
    pages = [page(i, "text") for i in range(8)]
    boundaries = [
        Boundary(0, "Acknowledgments"),
        Boundary(2, "Chapter 1"),
        Boundary(4, "Chapter 2"),
        Boundary(6, "Index"),
    ]
    kinds = [b.kind for b in mark_back_matter(boundaries, pages)]
    assert kinds == ["front", "body", "body", "back"]


def test_back_matter_pages_after_the_last_chapter():
    pages = [
        page(0, "Chapter 1"),
        page(1, "Notes from the field were scattered across the desk in great untidy piles"),
        page(2, "Notes", "1. A note."),
        page(3, "NOTES", "2. Another note."),  # a running header, not a new section
        page(4, "Bibliography", "Carroll, L."),
    ]
    marked = mark_back_matter([Boundary(0, "Chapter 1")], pages)
    assert marked == [
        Boundary(0, "Chapter 1"),
        Boundary(2, "Notes", "back"),
        Boundary(4, "Bibliography", "back"),
    ]


def test_only_back_matter_is_back():
    pages = [page(i, "text") for i in range(4)]
    marked = mark_back_matter([Boundary(0, "Appendix"), Boundary(2, "Index")], pages)
    assert [b.kind for b in marked] == ["back", "back"]
