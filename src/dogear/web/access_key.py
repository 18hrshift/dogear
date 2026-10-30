"""The access key: made once, kept in the web folder, and checked on every visit.

The key is in the link `dogear serve` prints. Opening the link swaps it for a cookie, so
it isn't seen again in the address bar, a page, or a log. The cookie holds a value
derived from the key, not the key itself.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import re
import secrets
import time
from collections import OrderedDict
from pathlib import Path

from dogear.errors import DogearError

KEY_FILE = "access-key.txt"
# Letters and digits that can't be mistaken for each other when read aloud or typed on
# a phone: no 0, o, 1, l, or i. 25 of these 30 are about 122 bits.
ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
KEY_LENGTH = 25
GROUP = 5  # shown as five groups of five, joined by hyphens
_KEY_PATTERN = re.compile(f"[{ALPHABET}]{{{KEY_LENGTH}}}")
COOKIE_MAX_AGE = 400 * 24 * 60 * 60  # the longest browsers keep a cookie


class AccessKey:
    def __init__(self, key: str) -> None:
        self._key = normalize(key)
        if not _KEY_PATTERN.fullmatch(self._key):
            raise ValueError("not an access key")

    @property
    def text(self) -> str:
        """The key as shown in the link: 'abcde-fghjk-...'."""
        return "-".join(self._key[i : i + GROUP] for i in range(0, KEY_LENGTH, GROUP))

    def matches(self, typed: str) -> bool:
        """Whether `typed` is this key, ignoring case, spaces, and hyphens. Takes the same
        time however much of it is right."""
        return hmac.compare_digest(
            normalize(typed).encode("utf-8", "replace"), self._key.encode("ascii")
        )

    def cookie_value(self) -> str:
        return hmac.new(
            self._key.encode("ascii"), b"dogear access cookie", hashlib.sha256
        ).hexdigest()

    def cookie_matches(self, value: str) -> bool:
        return hmac.compare_digest(value.encode("utf-8", "replace"), self.cookie_value().encode())


def normalize(typed: str) -> str:
    return "".join(c for c in typed.lower() if c not in " -\t\r\n")


def cookie_name(port: int) -> str:
    """Browsers share cookies between ports, so each port gets its own name."""
    return f"dogear_access_{port}"


def load_or_make_key(folder: Path) -> AccessKey:
    """The key kept in `folder`, made there (readable by this user only) on first run."""
    path = folder / KEY_FILE
    folder.mkdir(parents=True, exist_ok=True)
    try:
        return _read_key(path)
    except FileNotFoundError:
        pass
    key = "".join(secrets.choice(ALPHABET) for _ in range(KEY_LENGTH))
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:  # another Dogear made it just now
        return _read_key(path)
    with os.fdopen(descriptor, "w", encoding="ascii") as file:
        file.write(AccessKey(key).text + "\n")
    return AccessKey(key)


def _read_key(path: Path) -> AccessKey:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return AccessKey(text)
    except ValueError:
        raise DogearError(
            f"The access key file {path} doesn't hold a key Dogear made.",
            hint="Delete the file and start Dogear again. It makes a new key and a new link.",
        ) from None


class WrongKeyDelay:
    """Slows down repeated wrong keys from one address: each wrong key doubles the wait
    before the next answer, up to MAX_SECONDS. A right key clears it."""

    FIRST_SECONDS = 0.5
    MAX_SECONDS = 30.0
    FORGET_AFTER = 15 * 60
    MAX_ADDRESSES = 1000  # oldest are forgotten first

    def __init__(self, clock=time.monotonic, sleep=asyncio.sleep) -> None:
        self._clock = clock
        self._sleep = sleep
        self._misses: OrderedDict[str, tuple[int, float]] = OrderedDict()

    async def wait(self, address: str) -> None:
        """Before checking a key from `address`, wait as long as its earlier misses say."""
        misses, last = self._misses.get(address, (0, 0.0))
        if misses and self._clock() - last < self.FORGET_AFTER:
            await self._sleep(min(self.MAX_SECONDS, self.FIRST_SECONDS * 2 ** (misses - 1)))

    def missed(self, address: str) -> None:
        misses, last = self._misses.pop(address, (0, 0.0))
        if self._clock() - last >= self.FORGET_AFTER:
            misses = 0
        self._misses[address] = (min(misses + 1, 64), self._clock())
        while len(self._misses) > self.MAX_ADDRESSES:
            self._misses.popitem(last=False)

    def cleared(self, address: str) -> None:
        self._misses.pop(address, None)
