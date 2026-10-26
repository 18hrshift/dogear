import pytest

from dogear.output.filenames import MAX_NAME_BYTES, safe_filename, track_filenames


def test_track_names_are_numbered_and_cleaned():
    names = track_filenames(['Chapter 1: "Why?" <a/b>|*', "Line\nbreak\tand tab"], ".mp3")
    assert names == ["01 - Chapter 1 Why a b.mp3", "02 - Line break and tab.mp3"]


@pytest.mark.parametrize(
    ("count", "first", "last"),
    [
        (1, "01", "01"),
        (9, "01", "09"),
        (99, "01", "99"),
        (100, "001", "100"),
        (1000, "0001", "1000"),
    ],
)
def test_numbers_are_zero_padded_so_names_sort_in_order(count, first, last):
    names = track_filenames(["Part"] * count, ".mp3")
    assert names[0] == f"{first} - Part.mp3"
    assert names[-1] == f"{last} - Part.mp3"
    assert sorted(names) == names


def test_title_with_nothing_usable_keeps_just_the_number():
    assert track_filenames(["One", "???", " . "], ".mp3")[1:] == ["02.mp3", "03.mp3"]


@pytest.mark.parametrize(
    ("stem", "expected"),
    [
        ("The End. . .", "The End.m3u"),
        ("Wait...   ", "Wait.m3u"),
        ("...And Then", "And Then.m3u"),
        ("Café", "Café.m3u"),  # decomposed accent becomes one character
        ("???", "playlist.m3u"),
    ],
)
def test_dots_spaces_and_unicode_forms(stem, expected):
    assert safe_filename(stem, ".m3u", fallback="playlist") == expected


@pytest.mark.parametrize("stem", ["CON", "con", "Nul", "COM1", "lpt9", "CON.notes", "AUX ", "COM¹"])
def test_windows_reserved_names_are_changed(stem):
    name = safe_filename(stem, ".m3u")
    assert name.startswith("_")


@pytest.mark.parametrize("stem", ["Console", "Auxiliary", "COM10", "Nullify"])
def test_names_that_only_start_like_reserved_ones_are_kept(stem):
    assert safe_filename(stem, ".m3u") == f"{stem}.m3u"


@pytest.mark.parametrize("char", ["é", "文", "\U0001f600"])
def test_long_names_are_cut_at_a_character_boundary(char):
    name = track_filenames([char * 300], ".mp3")[0]
    assert len(name.encode("utf-8")) <= MAX_NAME_BYTES
    assert name.startswith("01 - " + char)
    assert name.endswith(char + ".mp3")


def test_cut_never_leaves_a_trailing_space_or_dot():
    stem = "a" * (MAX_NAME_BYTES - len(".mp3") - 1) + " b"
    assert safe_filename(stem, ".mp3") == "a" * (MAX_NAME_BYTES - len(".mp3") - 1) + ".mp3"
