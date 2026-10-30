"""The access key and the checks in front of every page: cookie, Host, and Origin."""

import asyncio
import os
import stat

import pytest
from web_samples import BASE, KEY, PORT, sample_app, visitor

from dogear.errors import DogearError
from dogear.web.access_key import KEY_FILE, AccessKey, WrongKeyDelay, load_or_make_key


@pytest.fixture
def app(tmp_path):
    return sample_app(tmp_path)


def test_without_the_cookie_every_page_asks_for_the_access_link(app):
    client = visitor(app, signed_in=False)
    for path in ["/", "/books/AAAAAAAAAAAAAAAA", "/books/AAAAAAAAAAAAAAAA/status"]:
        response = client.get(path)
        assert response.status_code == 403
        assert "<h1>This page needs Dogear's access link</h1>" in response.text
        assert "<title>Access link needed - Dogear</title>" in response.text


def test_help_and_the_stylesheet_need_no_cookie(app):
    client = visitor(app, signed_in=False)
    assert client.get("/help").status_code == 200
    assert client.get("/static/dogear.css").status_code == 200


def test_the_access_link_sets_a_strict_http_only_cookie_and_leaves_the_address_bar(app):
    client = visitor(app, signed_in=False)
    response = client.get(f"/start?key={KEY}", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"dogear_access_{PORT}=")
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Max-Age=34560000" in cookie
    assert KEY.replace("-", "") not in cookie.replace("-", "")
    home = client.get("/")
    assert home.status_code == 200
    assert "<h1>Make a talking book</h1>" in home.text
    assert KEY not in home.text


def test_a_wrong_link_is_refused_without_showing_the_key_it_had(app):
    client = visitor(app, signed_in=False)
    response = client.get("/start?key=abcde-fghjk-mnpqr-stuvw-xyz22", follow_redirects=False)
    assert response.status_code == 403
    assert "set-cookie" not in response.headers
    assert "<title>Error: Access link needed - Dogear</title>" in response.text
    assert "That access link isn&#39;t right." in response.text
    assert "xyz22" not in response.text


def test_the_typed_key_ignores_case_spaces_and_hyphens(app):
    client = visitor(app, signed_in=False)
    typed = KEY.upper().replace("-", " ")
    response = client.post("/access", data={"key": typed}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/").status_code == 200


def test_a_wrong_typed_key_keeps_what_was_typed_and_says_why(app):
    client = visitor(app, signed_in=False)
    response = client.post("/access", data={"key": "<b>wrong</b>"})
    assert response.status_code == 403
    assert 'value="&lt;b&gt;wrong&lt;/b&gt;"' in response.text
    assert 'role="alert"' in response.text
    assert 'href="#access-key"' in response.text
    assert 'aria-describedby="access-key-hint access-key-error"' in response.text


def test_an_empty_key_is_an_error(app):
    response = visitor(app, signed_in=False).post("/access", data={"key": " "})
    assert response.status_code == 400
    assert "Type the access key." in response.text


def test_a_cookie_from_another_key_is_refused(app):
    client = visitor(app, signed_in=False)
    client.cookies.set(f"dogear_access_{PORT}", "0" * 64)
    assert client.get("/").status_code == 403


def test_the_access_page_offers_to_continue_after_a_link_from_another_site(app):
    client = visitor(app, signed_in=False)
    page = client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).text
    assert "continue to Dogear</a>" in page
    assert "continue to Dogear" not in client.get("/").text


@pytest.mark.parametrize(
    "host", ["evil.example:8765", "127.0.0.1:9999", "192.168.1.5:8765", "127.0.0.1"]
)
def test_on_this_computer_only_local_host_names_are_answered(app, host):
    response = visitor(app).get("/", headers={"Host": host})
    assert response.status_code == 400
    assert "Dogear doesn&#39;t answer to this address" in response.text


@pytest.mark.parametrize(
    "host", ["127.0.0.1:8765", "localhost:8765", "[::1]:8765", "LOCALHOST:8765"]
)
def test_local_host_names_are_answered(app, host):
    assert visitor(app).get("/", headers={"Host": host}).status_code == 200


def test_on_the_network_any_host_name_is_answered(tmp_path):
    app = sample_app(tmp_path, lan=True)
    client = visitor(app)
    response = client.get("/", headers={"Host": "192.168.1.5:8765"})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "http://evil.example"},
        {"Origin": "null"},
        {"Origin": "http://127.0.0.1:9999"},
        {"Origin": "", "Referer": "http://evil.example/page"},
    ],
)
def test_forms_from_elsewhere_are_refused(app, headers):
    client = visitor(app)
    response = client.post(f"/books/{'A' * 16}/stop", headers=headers)
    assert response.status_code == 403
    assert "This form didn&#39;t come from Dogear&#39;s page" in response.text


def test_a_form_with_no_origin_or_referer_is_refused(app):
    client = visitor(app)
    del client.headers["Origin"]
    assert client.post(f"/books/{'A' * 16}/stop").status_code == 403


def test_a_referer_from_the_page_itself_is_enough(app):
    client = visitor(app)
    del client.headers["Origin"]
    response = client.post(f"/books/{'A' * 16}/stop", headers={"Referer": f"{BASE}/"})
    assert response.status_code == 404  # past the checks; there's no such book


def test_every_response_has_the_security_headers(app):
    response = visitor(app).get("/")
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "same-origin"
    assert response.headers["cache-control"] == "no-store"


def test_the_key_is_made_once_and_kept(tmp_path):
    first = load_or_make_key(tmp_path)
    again = load_or_make_key(tmp_path)
    assert first.text == again.text
    assert len(first.text) == 29
    if os.name != "nt":
        mode = stat.S_IMODE((tmp_path / KEY_FILE).stat().st_mode)
        assert mode == 0o600


def test_a_key_file_dogear_did_not_make_is_an_error(tmp_path):
    (tmp_path / KEY_FILE).write_text("password\n")
    with pytest.raises(DogearError, match="doesn't hold a key Dogear made"):
        load_or_make_key(tmp_path)


def test_keys_compare_by_content_only():
    key = AccessKey(KEY)
    assert key.matches(KEY)
    assert key.matches(" " + KEY.upper() + "\n")
    assert not key.matches(KEY[:-1])
    assert not key.matches("")
    assert key.cookie_matches(key.cookie_value())
    assert not key.cookie_matches("")


def test_wrong_keys_wait_longer_each_time_until_a_right_one():
    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    delay = WrongKeyDelay(clock=lambda: 100.0, sleep=sleep)
    for _ in range(4):
        asyncio.run(delay.wait("10.0.0.2"))
        delay.missed("10.0.0.2")
    asyncio.run(delay.wait("10.0.0.3"))  # another address doesn't wait
    assert waits == [0.5, 1.0, 2.0]
    asyncio.run(delay.wait("10.0.0.2"))
    assert waits == [0.5, 1.0, 2.0, 4.0]
    delay.cleared("10.0.0.2")
    asyncio.run(delay.wait("10.0.0.2"))
    assert waits == [0.5, 1.0, 2.0, 4.0]


def test_wrong_key_waits_are_capped_and_forgotten():
    now = [0.0]
    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    delay = WrongKeyDelay(clock=lambda: now[0], sleep=sleep)
    for _ in range(20):
        delay.missed("a")
    asyncio.run(delay.wait("a"))
    assert waits == [WrongKeyDelay.MAX_SECONDS]
    now[0] += WrongKeyDelay.FORGET_AFTER
    asyncio.run(delay.wait("a"))
    assert waits == [WrongKeyDelay.MAX_SECONDS]
    for n in range(WrongKeyDelay.MAX_ADDRESSES + 10):
        delay.missed(f"address {n}")
    assert len(delay._misses) == WrongKeyDelay.MAX_ADDRESSES


def test_wrong_keys_on_the_page_are_slowed_down(app, monkeypatch):
    waits = []

    async def sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr(app.state.wrong_keys, "_sleep", sleep)
    client = visitor(app, signed_in=False)
    for _ in range(3):
        client.post("/access", data={"key": "nope"})
    client.get("/start?key=nope")
    assert waits == [0.5, 1.0, 2.0]
