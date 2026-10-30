"""Checking what `dogear outline --json` sent back before the web page uses it."""

import json
from dataclasses import replace

from web_samples import sample_summary

from dogear.book_summary import summary_to_json
from dogear.web.reading import MAX_SECTIONS, Problem, parse_outline, problem_from_output


def outline_json(summary) -> bytes:
    return json.dumps(summary_to_json(summary)).encode()


def test_a_good_outline_is_read():
    assert parse_outline(outline_json(sample_summary())) == sample_summary()


def test_output_that_is_not_a_summary_is_a_bug_report():
    problem = parse_outline(b"{not json")
    assert isinstance(problem, Problem)
    assert "couldn't understand the list" in problem.error
    assert problem.hint.startswith("This is a bug in Dogear.")


def test_a_book_with_no_sections_says_so():
    problem = parse_outline(outline_json(replace(sample_summary(), sections=())))
    assert problem.error == "Dogear found no sections to read in this book."


def test_too_many_sections_for_a_page():
    summary = sample_summary()
    first = summary.sections[0]
    many = tuple(replace(first, number=n) for n in range(1, MAX_SECTIONS + 2))
    problem = parse_outline(outline_json(replace(summary, sections=many)))
    assert "more sections than the web page can list" in problem.error


def test_long_titles_are_cut_for_the_page():
    summary = sample_summary()
    long_section = replace(summary.sections[0], title="y" * 1000)
    parsed = parse_outline(
        outline_json(replace(summary, title="x" * 1000, sections=(long_section,)))
    )
    assert len(parsed.title) == 300
    assert parsed.title.endswith("...")
    assert len(parsed.sections[0].title) == 300


def test_error_lines_become_the_problem():
    found = problem_from_output("Some progress.\nError: It broke.\nWhat to do: Fix it.\n")
    assert (found.error, found.hint) == ("It broke.", "Fix it.")
    unknown = problem_from_output("Traceback (most recent call last):\n")
    assert unknown.error == "Dogear stopped because of a problem it didn't expect."
