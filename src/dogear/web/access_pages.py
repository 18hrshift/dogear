"""Opening Dogear with its access link, or by typing the key from it.

A right key sets the access cookie and goes to the home page, so the key leaves the
address bar. Wrong keys from one address are answered more and more slowly.
"""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from dogear.web.access_key import COOKIE_MAX_AGE, AccessKey, WrongKeyDelay, cookie_name
from dogear.web.forms import FormTooBig, first, read_form
from dogear.web.guard import access_page
from dogear.web.settings import WebSettings

MAX_KEY_CHARS = 200
WRONG_LINK = "That access link isn't right. Check that you copied all of it, or type the key."
WRONG_KEY = "That isn't the access key. Check it and try again."
NO_KEY = "Type the access key."


async def start(request: Request) -> Response:
    """GET /start?key=...: the access link."""
    candidate = request.query_params.get("key", "")[:MAX_KEY_CHARS]
    if await _right_key(request, candidate):
        return _let_in(request)
    # The wrong key from the link isn't shown: it may be most of the right one.
    return access_page(request, status_code=403, errors={"key": WRONG_LINK})


async def access(request: Request) -> Response:
    """POST /access: the key typed into the access page."""
    try:
        typed = first(await read_form(request), "key")[:MAX_KEY_CHARS]
    except FormTooBig:
        typed = ""
    if not typed.strip():
        return access_page(request, status_code=400, errors={"key": NO_KEY})
    if await _right_key(request, typed):
        return _let_in(request)
    return access_page(request, status_code=403, errors={"key": WRONG_KEY}, typed=typed)


async def _right_key(request: Request, candidate: str) -> bool:
    key: AccessKey = request.app.state.key
    delay: WrongKeyDelay = request.app.state.wrong_keys
    address = request.client.host if request.client else ""
    await delay.wait(address)
    if key.matches(candidate):
        delay.cleared(address)
        return True
    delay.missed(address)
    return False


def _let_in(request: Request) -> Response:
    key: AccessKey = request.app.state.key
    settings: WebSettings = request.app.state.settings
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(
        cookie_name(settings.port),
        key.cookie_value(),
        max_age=COOKIE_MAX_AGE,
        path="/",
        httponly=True,
        samesite="strict",
    )
    return response
