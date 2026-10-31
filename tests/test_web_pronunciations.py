"""The Pronunciations page: listing, adding, changing, and removing the page's words,
trying any text with Listen, and the errors and limits."""

import json
import os
import sys
from pathlib import Path

import lxml.html
import pytest
from web_samples import changed_elsewhere, sample_app, sample_config, save_form, visitor

from dogear.web import atomic, child
from dogear.web.settings import WordLimits
from dogear.web.spelling_forms import form_limits

FAKE = Path(__file__).parent / "fake_dogear.py"


@pytest.fixture
def commands(monkeypatch, tmp_path):
    monkeypatch.setattr(child, "dogear_command", lambda: [sys.executable, str(FAKE)])
    log = tmp_path / "commands.jsonl"
    monkeypatch.setenv("DOGEAR_FAKE_LOG", str(log))
    return log


@pytest.fixture
def running(tmp_path, commands):
    app = sample_app(tmp_path / "web")
    client = visitor(app)
    with client:
        yield app, client


def tree_of(response):
    return lxml.html.fromstring(response.text)


def texts(tree, xpath):
    return [" ".join(e.text_content().split()) for e in tree.xpath(xpath)]


def saved(app):
    return [(e.word, e.sounds_like, e.phonemes) for e in app.state.page_words.entries()]


def add(client, word, spelling):
    return client.post(
        "/pronunciations/add", data={"word": word, "spelling": spelling}, follow_redirects=False
    )


def test_an_empty_list_says_so_and_offers_to_add_and_try(running):
    app, client = running
    response = client.get("/pronunciations")
    assert response.status_code == 200
    tree = tree_of(response)
    assert tree.xpath("//title/text()") == ["Pronunciations - Dogear"]
    assert tree.xpath("//nav//a[@aria-current='page']/text()") == ["Pronunciations"]
    assert texts(tree, "//h2") == ["Add a word", "Try saying something", "Your words"]
    assert "No words yet." in response.text
    assert tree.xpath("//form[@action='/pronunciations/try']/@data-listen") == ["try-status"]
    assert tree.xpath("//*[@id='try-status']/@role") == ["status"]
    assert tree.xpath("//script/@src") == ["/static/listen.js"]


def test_add_change_and_remove_words(running):
    app, client = running
    response = add(client, "  Utterson ", "utter son")
    assert response.headers["location"] == "/pronunciations?done=added"
    add(client, "Lanyon", "lan yon")
    page = client.get("/pronunciations?done=added")
    tree = tree_of(page)
    assert texts(tree, "//p[@class='notice']") == ["Added. Its Listen button is with it below."]
    assert texts(tree, "//legend") == ["Lanyon", "Utterson"]
    assert tree.xpath("//input[@id='say-2']/@value") == ["utter son"]
    assert texts(tree, "//button[@form='listen-2']") == ["Listen to Utterson"]
    [listen_form] = tree.xpath("//form[@id='listen-2']")
    assert dict(listen_form.form_values()) == {
        "text": "Utterson",
        "back": "/pronunciations#word-2",
    }

    # A word added again, in other capitals, gets the new spelling.
    add(client, "UTTERSON", "utter sun")
    assert saved(app) == [("Lanyon", "lan yon", None), ("UTTERSON", "utter sun", None)]

    response = client.post(
        "/pronunciations",
        data={"word-1": "Lanyon", "say-1": "", "word-2": "UTTERSON", "say-2": "utter son"},
        follow_redirects=False,
    )
    assert response.headers["location"] == "/pronunciations?done=saved"
    assert saved(app) == [("UTTERSON", "utter son", None)]
    assert texts(tree_of(client.get("/pronunciations?done=saved")), "//p[@class='notice']") == [
        "Saved."
    ]


def typed(form, word, spelling):
    """`form` with `spelling` typed in the "Say it like" field of `word`."""
    [number] = [k[len("word-") :] for k, v in form.items() if k.startswith("word-") and v == word]
    return {**form, f"say-{number}": spelling}


def test_a_page_opened_earlier_saves_only_what_it_changed(running):
    app, client = running
    add(client, "Utterson", "utter son")
    add(client, "Lanyon", "lan yon")
    earlier = save_form(client, "/pronunciations")  # another tab, or Back
    assert earlier == {
        "word-1": "Lanyon",
        "was-1": "lan yon",
        "say-1": "lan yon",
        "word-2": "Utterson",
        "was-2": "utter son",
        "say-2": "utter son",
    }
    client.post(
        "/pronunciations", data=typed(save_form(client, "/pronunciations"), "Utterson", "utter sun")
    )
    response = client.post(
        "/pronunciations", data=typed(earlier, "Lanyon", "lanny on"), follow_redirects=False
    )
    assert response.headers["location"] == "/pronunciations?done=saved"
    assert saved(app) == [("Lanyon", "lanny on", None), ("Utterson", "utter sun", None)]
    # Nor does it bring back a word removed since.
    client.post("/pronunciations", data=typed(save_form(client, "/pronunciations"), "Lanyon", ""))
    client.post("/pronunciations", data=earlier)
    assert saved(app) == [("Utterson", "utter sun", None)]


def test_a_word_changed_in_another_window_is_not_overwritten(running):
    app, client = running
    add(client, "Utterson", "utter son")
    add(client, "Poole", "pool")
    page = changed_elsewhere(
        client,
        "/pronunciations",
        "Utterson",
        "otter son",
        lambda: app.state.page_words.save({"Utterson": "utter sun"}),
    )
    tree = lxml.html.fromstring(page)
    message = (
        "Utterson was changed in another window since this page was opened. "
        "It now says: utter sun. Check it and save again."
    )
    links = tree.xpath("//*[@role='alert']//a")
    assert [(a.get("href"), a.text_content()) for a in links] == [("#say-2", message)]
    assert texts(tree, "//p[@id='say-2-error']") == [f"Error: {message}"]
    assert tree.xpath("//input[@id='say-2']/@aria-describedby") == ["say-2-error"]
    assert saved(app) == [("Poole", "pool", None), ("Utterson", "utter sun", None)]
    # What was typed is kept, and saving again saves it.
    [form] = tree.xpath("//form[@action='/pronunciations']")
    again = dict(form.form_values())
    assert (again["say-2"], again["was-2"]) == ("otter son", "utter sun")
    response = client.post("/pronunciations", data=again, follow_redirects=False)
    assert response.headers["location"] == "/pronunciations?done=saved"
    assert saved(app) == [("Poole", "pool", None), ("Utterson", "otter son", None)]


def test_a_word_removed_in_another_window_says_so(running):
    app, client = running
    add(client, "Utterson", "utter son")
    page = changed_elsewhere(
        client,
        "/pronunciations",
        "Utterson",
        "otter son",
        lambda: app.state.page_words.save({"Utterson": ""}),
    )
    assert (
        "Utterson was changed in another window since this page was opened. It now has no "
        "spelling. Check it and save again." in page
    )
    assert saved(app) == []


def test_an_entry_outside_the_limits_can_be_removed(tmp_path, commands):
    config = sample_config(tmp_path / "web")
    config["web"]["max_word_chars"] = 8
    app = sample_app(tmp_path / "web", config)
    long = "Dr. Henry Jekyll"  # saved by hand, or before the limit was lowered
    app.state.settings.words_file.write_text(
        f'[words]\n"{long}" = "doctor jekyll"\n"Mr. Edward Hyde" = "mister hyde"\nPoole = "pool"\n',
        encoding="utf-8",
    )
    with visitor(app) as client:
        form = typed(save_form(client, "/pronunciations"), long, "")
        form = typed(form, "Poole", "pooh")  # the other long word is left as it is
        response = client.post("/pronunciations", data=form, follow_redirects=False)
        assert response.headers["location"] == "/pronunciations?done=saved"
        assert saved(app) == [("Mr. Edward Hyde", "mister hyde", None), ("Poole", "pooh", None)]
        # Changing one is checked as a new word is, and says why it can't be saved.
        form = typed(save_form(client, "/pronunciations"), "Mr. Edward Hyde", "mister hide")
        response = client.post("/pronunciations", data=form, follow_redirects=False)
    assert response.status_code == 400
    assert "Mr. Edward Hyde can&#39;t be saved: A word can be at most 8" in response.text
    assert saved(app) == [("Mr. Edward Hyde", "mister hyde", None), ("Poole", "pooh", None)]


def test_adding_needs_a_word_and_a_spelling_and_keeps_what_was_typed(running):
    app, client = running
    response = add(client, "  ", "")
    assert response.status_code == 400
    tree = tree_of(response)
    assert tree.xpath("//title/text()") == ["Error: Pronunciations - Dogear"]
    links = tree.xpath("//*[@role='alert']//a")
    assert [(a.get("href"), a.text_content()) for a in links] == [
        ("#add-word", "Type the word as the book writes it."),
        ("#add-spelling", 'Type how the word should sound, such as "utter son" for Utterson.'),
    ]
    assert tree.xpath("//input[@id='add-word']/@aria-describedby") == [
        "add-word-hint add-word-error"
    ]
    response = add(client, "Hyde\nJekyll", "hide")
    tree = tree_of(response)
    assert tree.xpath("//input[@id='add-spelling']/@value") == ["hide"]
    assert "control characters" in texts(tree, "//p[@id='add-word-error']")[0]
    assert saved(app) == []


def test_the_web_settings_limit_what_can_be_added(tmp_path, commands):
    config = sample_config(tmp_path / "web")
    config["web"].update(max_pronunciations=1, max_word_chars=6, max_spelling_chars=8)
    app = sample_app(tmp_path / "web", config)
    with visitor(app) as client:
        too_long = tree_of(add(client, "Uttersons", "utter son"))
        assert texts(too_long, "//p[@id='add-word-error']") == [
            "Error: A word can be at most 6 characters long."
        ]
        assert texts(too_long, "//p[@id='add-spelling-error']") == [
            "Error: How to say the word can be at most 8 characters long."
        ]
        assert add(client, "Hyde", "hide").status_code == 303
        full = add(client, "Poole", "pool")
        assert full.status_code == 400
        assert "holds at most 1 words" in full.text
        assert tree_of(full).xpath("//*[@role='alert']//a/@href") == ["#add-word"]
        assert saved(app) == [("Hyde", "hide", None)]


def test_phoneme_entries_are_listed_but_not_changed(running):
    app, client = running
    app.state.settings.words_file.write_text(
        '[words]\nLanyon = { phonemes = "lˈænjən" }\nPoole = "pool"\n', encoding="utf-8"
    )
    tree = tree_of(client.get("/pronunciations"))
    assert texts(tree, "//legend") == ["Poole"]
    assert texts(tree, "//ul[@class='phoneme-list']/li") == ["Lanyon: lˈænjən"]
    assert (
        "lists them but doesn't change them"
        in texts(tree, "//h2[.='Words with exact phonemes']/following-sibling::p[1]")[0]
    )
    response = add(client, "lanyon", "lan yon")
    assert response.status_code == 400
    assert "Lanyon has exact phonemes" in response.text
    client.post("/pronunciations", data={"word-1": "Poole", "say-1": ""})
    assert saved(app) == [("Lanyon", None, "lˈænjən")]


def test_try_saying_something_with_the_pages_words(running, commands):
    app, client = running
    add(client, "Utterson", "utter son")
    response = client.post(
        "/pronunciations/try", data={"text": "Mr. Utterson"}, follow_redirects=False
    )
    assert response.status_code == 303
    page = client.get(response.headers["location"]).text
    assert "<p>Said: Mr. utter son</p>" in page
    assert '<a href="/pronunciations#try">Back to Pronunciations</a>' in page
    say = [json.loads(line) for line in commands.read_text().splitlines()][-1]
    assert say[-2:] == ["--", "Mr. Utterson"]
    assert say[say.index("--words") + 1] == str(app.state.settings.words_file)

    answer = client.post(
        "/pronunciations/try", data={"text": "Lanyon"}, headers={"Accept": "application/json"}
    )
    assert answer.status_code == 202
    assert answer.json()["status_url"].startswith("/listen/")


def test_trying_nothing_is_an_error_on_the_field(running):
    app, client = running
    response = client.post("/pronunciations/try", data={"text": " ... "})
    assert response.status_code == 400
    tree = tree_of(response)
    assert tree.xpath("//*[@role='alert']//a/@href") == ["#try-text"]
    assert tree.xpath("//input[@id='try-text']/@value") == [" ... "]
    answer = client.post(
        "/pronunciations/try", data={"text": ""}, headers={"Accept": "application/json"}
    )
    assert answer.status_code == 400
    assert answer.json()["error"] == "Type a word or a sentence to say."


def test_a_word_file_broken_by_hand_is_reported_not_overwritten(running):
    app, client = running
    words_file = app.state.settings.words_file
    words_file.write_text("[words]\nUtterson = utter son\n", encoding="utf-8")
    response = client.get("/pronunciations")
    assert response.status_code == 500
    assert "Dogear can&#39;t read its word list" in response.text
    assert "is not valid TOML" in response.text
    assert add(client, "Hyde", "hide").status_code == 500
    assert words_file.read_text(encoding="utf-8") == "[words]\nUtterson = utter son\n"


def test_a_word_file_another_program_has_open_is_reported(running, monkeypatch):
    app, client = running
    add(client, "Utterson", "utter son")
    words_file = app.state.settings.words_file
    monkeypatch.setattr(atomic.time, "sleep", lambda seconds: None)
    real_replace = os.replace

    def in_use(source, target):
        if os.fspath(target) == os.fspath(words_file):
            raise PermissionError(13, "The process cannot access the file")
        real_replace(source, target)

    monkeypatch.setattr(atomic.os, "replace", in_use)
    response = client.post(
        "/pronunciations", data=typed(save_form(client, "/pronunciations"), "Utterson", "utter sun")
    )
    assert response.status_code == 500
    tree = tree_of(response)
    assert texts(tree, "//h1") == ["Dogear couldn't save the words"]
    page = " ".join(tree.text_content().split())
    assert "another program had the pronunciation file open" in page
    assert "Try saving again in a moment." in page
    assert "disk" not in page
    assert saved(app) == [("Utterson", "utter son", None)]


def test_the_save_form_is_bounded_by_the_word_limits(tmp_path, commands):
    limits = WordLimits(entries=3, word_chars=10, spelling_chars=10)
    most_bytes, most_fields = form_limits(limits)
    assert most_fields == 25  # word-N, was-N, and say-N for each, and a few more
    assert most_bytes > 3 * 9 * 30
    config = sample_config(tmp_path / "web")
    config["web"].update(max_pronunciations=3, max_word_chars=10, max_spelling_chars=10)
    app = sample_app(tmp_path / "web", config)
    with visitor(app) as client:
        response = client.post("/pronunciations", data={"word-1": "x" * 300_000, "say-1": "y"})
        assert response.status_code == 413


def test_the_pronunciations_pages_need_the_cookie_and_dogears_own_forms(running):
    app, client = running
    stranger = visitor(app, signed_in=False)
    assert stranger.get("/pronunciations").status_code == 403
    for path in ("/pronunciations", "/pronunciations/add", "/pronunciations/try"):
        assert stranger.post(path, data={"word": "Hyde", "spelling": "hide"}).status_code == 403
        response = client.post(
            path,
            data={"word": "Hyde", "spelling": "hide", "text": "Hyde"},
            headers={"Origin": "http://evil.example"},
        )
        assert response.status_code == 403
    assert saved(app) == []
