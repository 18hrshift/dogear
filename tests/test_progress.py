"""Progress lines for long renders, timed with a fake clock."""

import pytest

from dogear.render.progress import Progress, describe_duration


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def lines():
    return []


def progress(clock, lines, total_words=100, total_sections=2, every_seconds=120) -> Progress:
    return Progress(total_words, total_sections, every_seconds, lines.append, clock)


def test_no_estimate_before_anything_new_is_rendered(clock, lines):
    p = progress(clock, lines)
    p.section_done(1, "The Storm")
    p.sentence(40, cached=True)
    p.section_done(1, "The Storm")
    assert lines == ["Section 1 of 2 done: The Storm."] * 2


def test_no_estimate_from_less_than_a_second_of_rendering(clock, lines):
    p = progress(clock, lines)
    p.sentence(10, cached=False, seconds=0.5)
    p.section_done(1, "A")
    assert lines == ["Section 1 of 2 done: A."]


def test_less_than_a_minute_left(clock, lines):
    p = progress(clock, lines)
    p.sentence(50, cached=False, seconds=10)
    p.section_done(1, "A")
    assert lines == ["Section 1 of 2 done: A. Less than a minute left."]


def test_hours_and_minutes_left(clock, lines):
    p = progress(clock, lines, total_words=7510)
    p.sentence(10, cached=False, seconds=10)  # a second a word, 7,500 words to go
    p.section_done(1, "A")
    assert lines == ["Section 1 of 2 done: A. About 2 hours 5 minutes left."]


def test_cached_words_are_done_but_do_not_set_the_pace(clock, lines):
    p = progress(clock, lines, total_words=1000)
    p.sentence(500, cached=True)
    p.sentence(10, cached=False, seconds=60)  # 6 seconds a word, 490 words to go
    p.section_done(1, "A")
    assert lines == ["Section 1 of 2 done: A. About 49 minutes left."]


def test_no_estimate_when_nothing_is_left(clock, lines):
    p = progress(clock, lines, total_words=10)
    p.sentence(10, cached=False, seconds=30)
    p.section_done(2, "B")
    assert lines == ["Section 2 of 2 done: B."]


def test_check_ins_wait_for_the_configured_gap(clock, lines):
    p = progress(clock, lines, total_words=4, total_sections=3, every_seconds=120)
    p.sentence(1, cached=True)
    clock.now += 119
    p.check_in(1, "The Storm")
    assert lines == []
    clock.now += 1
    p.check_in(1, "The Storm")
    assert lines == ["Working on section 1 of 3, The Storm. 25% of the book done."]
    clock.now += 100
    p.check_in(1, "The Storm")
    assert len(lines) == 1
    clock.now += 20
    p.check_in(1, "The Storm")
    assert len(lines) == 2


def test_a_finished_section_restarts_the_gap(clock, lines):
    p = progress(clock, lines, every_seconds=60)
    clock.now += 50
    p.section_done(1, "A")
    clock.now += 50
    p.check_in(2, "B")
    assert lines == ["Section 1 of 2 done: A."]
    clock.now += 10
    p.check_in(2, "B")
    assert lines[-1].startswith("Working on section 2 of 2, B.")


def test_check_in_includes_the_estimate(clock, lines):
    p = progress(clock, lines, total_words=300, every_seconds=0)
    p.sentence(100, cached=False, seconds=100)
    p.check_in(1, "A")
    assert lines == ["Working on section 1 of 2, A. 33% of the book done. About 3 minutes left."]


def test_check_in_with_no_words(clock, lines):
    p = progress(clock, lines, total_words=0, every_seconds=0)
    p.check_in(1, "Blank")
    assert lines == ["Working on section 1 of 2, Blank. 0% of the book done."]


def test_summary_of_new_sentences(clock, lines):
    p = progress(clock, lines)
    p.sentence(3, cached=False, seconds=2)
    p.sentence(4, cached=False, seconds=2)
    clock.now += 125
    assert p.summary() == "Spoke 2 sentences (2 new) in 2 minutes."


def test_summary_with_cached_sentences(clock, lines):
    p = progress(clock, lines)
    for _ in range(1000):
        p.sentence(1, cached=False, seconds=1)
    for _ in range(500):
        p.sentence(1, cached=True)
    clock.now += 3720
    assert p.summary() == (
        "Spoke 1,500 sentences (1,000 new, 500 already made in an earlier run) in 1 hour 2 minutes."
    )


def test_sentences_and_the_summary_print_nothing(clock, lines):
    p = progress(clock, lines)
    p.sentence(3, cached=False, seconds=5)
    p.sentence(3, cached=True)
    p.summary()  # the caller decides where the summary goes
    assert lines == []


@pytest.mark.parametrize(
    ("seconds", "words"),
    [
        (0, "less than a minute"),
        (29, "less than a minute"),
        (30, "less than a minute"),  # rounds half to even: 0 minutes
        (31, "1 minute"),
        (60, "1 minute"),
        (89, "1 minute"),
        (91, "2 minutes"),
        (3599, "1 hour"),
        (3600, "1 hour"),
        (3660, "1 hour 1 minute"),
        (7200, "2 hours"),
        (7500, "2 hours 5 minutes"),
        (86_400, "24 hours"),
    ],
)
def test_describe_duration(seconds, words):
    assert describe_duration(seconds) == words
