"""The checks every request passes before any page sees it.

1. On this computer only (not --lan), the Host header must be 127.0.0.1, localhost, or
   [::1] with Dogear's port. A web page elsewhere can point its own name at 127.0.0.1
   (DNS rebinding), and this stops it from reaching Dogear that way.
2. A form (any request that isn't GET or HEAD) must come from Dogear's own pages: its
   Origin header, or failing that its Referer, must match the address it was sent to.
3. Every page but the access pages, help, and the stylesheet and script needs the
   access cookie. Without it, the page asks for the access link.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from dogear.web.access_key import AccessKey, cookie_name
from dogear.web.settings import WebSettings
from dogear.web.templating import message, render

OPEN_PATHS = {"/start", "/access", "/help"}
OPEN_PREFIXES = ("/static/",)
LOCAL_NAMES = ("127.0.0.1", "localhost", "[::1]")


class Guard:
    def __init__(self, app: ASGIApp, *, settings: WebSettings, key: AccessKey) -> None:
        self.app = app
        self.settings = settings
        self.key = key
        self.cookie = cookie_name(settings.port)
        self.local_hosts = {f"{name}:{settings.port}" for name in LOCAL_NAMES}
        if settings.port == 80:  # browsers leave out the usual port
            self.local_hosts.update(LOCAL_NAMES)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        refusal = self.refusal(Request(scope, receive))
        if refusal is None:
            await self.app(scope, receive, send)
        else:
            await refusal(scope, receive, send)

    def refusal(self, request: Request) -> Response | None:
        if (
            not self.settings.lan
            and request.headers.get("host", "").lower() not in self.local_hosts
        ):
            return message(
                request,
                400,
                "Wrong address",
                "Dogear doesn't answer to this address",
                "Open Dogear with the link it showed in its window when it started.",
            )
        if request.method not in ("GET", "HEAD") and not same_origin(request):
            return message(
                request,
                403,
                "Form not accepted",
                "This form didn't come from Dogear's page",
                "Dogear only takes forms sent from its own pages. Go back to Dogear's page, "
                "reload it, and try again.",
            )
        if self._open(request.url.path) or self.has_cookie(request):
            return None
        return access_page(request, status_code=403)

    def has_cookie(self, request: Request) -> bool:
        value = request.cookies.get(self.cookie)
        return value is not None and self.key.cookie_matches(value)

    @staticmethod
    def _open(path: str) -> bool:
        return path in OPEN_PATHS or path.startswith(OPEN_PREFIXES)


def same_origin(request: Request) -> bool:
    expected = f"{request.url.scheme}://{request.headers.get('host', '')}".lower()
    origin = request.headers.get("origin")
    if origin is not None:
        return origin.lower() == expected  # "null" never matches
    referer = request.headers.get("referer")
    if not referer:
        return False
    parts = urlsplit(referer)
    return f"{parts.scheme}://{parts.netloc}".lower() == expected


def access_page(
    request: Request, *, status_code: int, errors: dict[str, str] | None = None, typed: str = ""
) -> Response:
    # A cookie set by the access link isn't sent when the link was opened from another
    # site (SameSite=Strict), though the browser has it. A link from this page sends it.
    from_elsewhere = request.headers.get("sec-fetch-site") == "cross-site"
    return render(
        request,
        "access.html",
        "Access link needed",
        status_code=status_code,
        errors=errors,
        typed=typed,
        offer_continue=from_elsewhere and request.method == "GET",
    )
