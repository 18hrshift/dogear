"""A stand-in for a standalone (PyInstaller) build of Dogear, for tests.

It fakes only what `dogear.bundle` looks at: `sys.frozen` and `sys._MEIPASS`, replaced
on the `sys` that module sees (not the real one), and the bundled folder's contents.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from dogear import bundle


class FakeBuild:
    def __init__(self, root: Path, monkeypatch) -> None:
        internal = root / "_internal"
        self.folder = internal / bundle.FOLDER
        (self.folder / bundle.TOOLS).mkdir(parents=True)
        (self.folder / bundle.MODELS).mkdir(parents=True)
        self.manifest: dict[str, dict[str, str]] = {}
        fake_sys = SimpleNamespace(
            frozen=True, _MEIPASS=str(internal), executable=str(root / "dogear")
        )
        monkeypatch.setattr(bundle, "sys", fake_sys)
        self._save()

    def add_program(self, name: str) -> Path:
        path = self.folder / bundle.TOOLS / (name + (".exe" if os.name == "nt" else ""))
        path.write_text("a bundled program", encoding="utf-8")
        return path

    def add_model(self, relative: str, sha256: str, content: bytes = b"bundled") -> Path:
        """A bundled voice file, listed in the manifest with `sha256`."""
        path = self.folder / bundle.MODELS / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.manifest[relative] = {"sha256": sha256}
        self._save()
        return path

    def add_model_folder(self, relative: str, sha256: str) -> Path:
        """A bundled unpacked model folder, listed with the SHA-256 of its download."""
        path = self.folder / bundle.MODELS / relative
        path.mkdir(parents=True, exist_ok=True)
        (path / "config.cfg").write_text("[nlp]", encoding="utf-8")
        self.manifest[relative] = {"sha256": sha256}
        self._save()
        return path

    def _save(self) -> None:
        manifest = self.folder / bundle.MODELS / bundle.MANIFEST
        manifest.write_text(json.dumps({"files": self.manifest}), encoding="utf-8")
        bundle._manifest.cache_clear()
