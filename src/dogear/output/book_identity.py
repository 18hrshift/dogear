"""What a talking book says about itself: a stable identifier and who narrates it."""

from __future__ import annotations

import uuid

from dogear.config import Config
from dogear.document import Metadata
from dogear.voice.engines import engine_named

# Fixed, so the same book always gets the same identifier.
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://github.com/18hrshift/dogear-app")


def book_uid(metadata: Metadata) -> str:
    """A urn:uuid for the talking book, the same each time the same book is made.

    A reading app then treats a remade book as a new version of the one it has, keeping
    the listener's place. It is not the source's ISBN: the talking book is its own edition.
    """
    seed = "\n".join([metadata.identifier or "", metadata.title, *metadata.authors])
    return f"urn:uuid:{uuid.uuid5(_NAMESPACE, seed)}"


def narrator(config: Config) -> str:
    """Who reads the book, said plainly: the voice is synthetic."""
    engine = engine_named(config["voice"]["engine"])
    return f"{config['voice']['voice']}, a synthetic {engine.title} voice"
