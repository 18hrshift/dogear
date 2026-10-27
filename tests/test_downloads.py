"""Downloading voice files: checksums, size caps, progress lines, and the spaCy unpack.

Downloads read `file://` URLs from tmp_path or a patched urlopen. Nothing here uses the
network.
"""

import hashlib
import io
import urllib.error
import zipfile

import pytest

from dogear.errors import DownloadError
from dogear.voice import downloads
from dogear.voice.catalog import catalog, spacy_model_dir, spacy_wheel
from dogear.voice.downloads import RemoteFile, download, ensure_files, megabytes
from dogear.voice.spacy_model import unpack_spacy_model


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def served(tmp_path, name: str, data: bytes) -> str:
    """A `file://` URL that serves `data`."""
    source = tmp_path / "server" / name
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(data)
    return source.as_uri()


def remote(tmp_path, name="voice.bin", data=b"voice data", **overrides) -> RemoteFile:
    fields = {
        "url": served(tmp_path, name, data),
        "sha256": sha256(data),
        "size": len(data),
        "path": tmp_path / "models" / "kokoro" / name,
    }
    return RemoteFile(**{**fields, **overrides})


def leftovers(remote_file: RemoteFile) -> list[str]:
    folder = remote_file.path.parent
    return sorted(p.name for p in folder.iterdir()) if folder.is_dir() else []


def test_download_writes_the_file(tmp_path):
    file = remote(tmp_path, data=b"x" * 1000)
    lines = []
    download(file, 5, lines.append)
    assert file.path.read_bytes() == b"x" * 1000
    assert leftovers(file) == ["voice.bin"]  # no .part file left behind
    assert lines == []  # small files download quietly


def test_checksum_mismatch_removes_the_file(tmp_path):
    file = remote(tmp_path, sha256="0" * 64)
    with pytest.raises(DownloadError) as err:
        download(file, 5, print)
    assert "voice.bin" in err.value.message
    assert "checksum" in err.value.message
    assert "report it" in err.value.hint
    assert leftovers(file) == []


def test_download_bigger_than_declared_is_stopped(tmp_path):
    data = b"y" * 100
    file = remote(tmp_path, data=data, size=40)
    with pytest.raises(DownloadError, match="bigger than expected") as err:
        download(file, 5, print)
    assert err.value.hint
    assert leftovers(file) == []


def test_size_is_an_upper_bound_not_an_exact_size(tmp_path):
    data = b"small"
    file = remote(tmp_path, data=data, size=1 << 20)
    download(file, 5, print)
    assert file.path.read_bytes() == data


def test_missing_source_becomes_a_download_error_with_a_hint(tmp_path):
    file = RemoteFile(
        url=(tmp_path / "server" / "gone.bin").as_uri(),
        sha256="0" * 64,
        size=10,
        path=tmp_path / "models" / "gone.bin",
    )
    with pytest.raises(DownloadError) as err:
        download(file, 5, print)
    assert err.value.message.startswith("Couldn't download gone.bin:")
    assert "internet connection" in err.value.hint
    assert err.value.__cause__ is None  # no traceback chain for a problem the user can fix
    assert leftovers(file) == []


@pytest.mark.parametrize(
    "error",
    [
        urllib.error.URLError("Name or service not known"),
        TimeoutError("timed out"),
        ConnectionResetError("connection reset"),
    ],
)
def test_network_errors_become_download_errors(tmp_path, monkeypatch, error):
    def fail(url, timeout):
        raise error

    monkeypatch.setattr(downloads.urllib.request, "urlopen", fail)
    file = remote(tmp_path)
    with pytest.raises(DownloadError, match="Couldn't download voice.bin") as err:
        download(file, 5, print)
    assert "internet connection" in err.value.hint
    assert leftovers(file) == []


class BrokenResponse(io.BytesIO):
    """A response that sends some bytes, then loses the connection."""

    def read(self, size=-1):
        if self.tell():
            raise ConnectionResetError("connection reset by peer")
        return super().read(4)


def test_connection_lost_midway_leaves_no_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        downloads.urllib.request, "urlopen", lambda url, timeout: BrokenResponse(b"12345678")
    )
    file = remote(tmp_path, data=b"12345678")
    with pytest.raises(DownloadError, match="connection reset by peer"):
        download(file, 5, print)
    assert leftovers(file) == []


def test_timeout_is_passed_to_urlopen(tmp_path, monkeypatch):
    seen = []

    def fake_urlopen(url, timeout):
        seen.append((url, timeout))
        return io.BytesIO(b"voice data")

    monkeypatch.setattr(downloads.urllib.request, "urlopen", fake_urlopen)
    file = remote(tmp_path)
    download(file, 42, print)
    assert seen == [(file.url, 42)]


def test_big_files_report_each_quarter(tmp_path, monkeypatch):
    monkeypatch.setattr(downloads, "_REPORT_FROM", 100)
    monkeypatch.setattr(downloads, "_CHUNK", 10)
    file = remote(tmp_path, name="model.onnx", data=bytes(range(200)))
    lines = []
    download(file, 5, lines.append)
    assert lines == [
        "model.onnx: 25% downloaded.",
        "model.onnx: 50% downloaded.",
        "model.onnx: 75% downloaded.",
        "model.onnx: 100% downloaded.",
    ]


def test_files_below_the_threshold_report_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(downloads, "_REPORT_FROM", 201)
    monkeypatch.setattr(downloads, "_CHUNK", 10)
    lines = []
    download(remote(tmp_path, data=bytes(200)), 5, lines.append)
    assert lines == []


def test_ensure_files_downloads_only_missing_files(tmp_path, config):
    present = remote(tmp_path, name="present.bin", data=b"old")
    present.path.parent.mkdir(parents=True, exist_ok=True)
    present.path.write_bytes(b"already here")
    missing = remote(tmp_path, name="missing.bin", data=b"new" * 1000)
    lines = []
    ensure_files([present, missing], config, lines.append)
    assert present.path.read_bytes() == b"already here"  # not fetched again
    assert missing.path.read_bytes() == b"new" * 1000
    assert lines == [
        "Downloading voice files, 1 MB in all. This only happens once.",
        "Voice files downloaded.",
    ]


def test_ensure_files_does_nothing_when_everything_is_there(tmp_path, config, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("nothing should be downloaded")

    monkeypatch.setattr(downloads.urllib.request, "urlopen", no_network)
    file = remote(tmp_path)
    file.path.parent.mkdir(parents=True)
    file.path.write_bytes(b"voice data")
    lines = []
    ensure_files([file], config, lines.append)
    assert lines == []


def test_ensure_files_uses_the_configured_timeout(tmp_path, config, monkeypatch):
    config["models"]["download_timeout_seconds"] = 7
    timeouts = []

    def fake_urlopen(url, timeout):
        timeouts.append(timeout)
        return io.BytesIO(b"voice data")

    monkeypatch.setattr(downloads.urllib.request, "urlopen", fake_urlopen)
    ensure_files([remote(tmp_path)], config, lambda line: None)
    assert timeouts == [7]


def test_ensure_files_reports_the_total_size(tmp_path, config, monkeypatch):
    monkeypatch.setattr(downloads, "download", lambda remote, timeout, report: None)
    files = [
        remote(tmp_path, name="a.bin", size=300_000_000),
        remote(tmp_path, name="b.bin", size=25_000_000),
    ]
    lines = []
    ensure_files(files, config, lines.append)
    assert lines[0] == "Downloading voice files, 325 MB in all. This only happens once."


@pytest.mark.parametrize(
    ("size", "text"),
    [(0, "1 MB"), (400_000, "1 MB"), (1_000_000, "1 MB"), (12_806_118, "13 MB")],
)
def test_megabytes(size, text):
    assert megabytes(size) == text


# The spaCy model, unpacked from its wheel.

MODEL_DIR = catalog()["spacy"]["model_dir"]  # "en_core_web_sm/en_core_web_sm-3.8.0"


def build_wheel(models_dir, members: dict[str, bytes]):
    path = spacy_wheel(models_dir).path
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def model_wheel(models_dir, extra: dict[str, bytes] | None = None):
    return build_wheel(
        models_dir,
        {
            "en_core_web_sm/__init__.py": b"import spacy",
            "en_core_web_sm/meta.json": b"{}",
            f"{MODEL_DIR}/config.cfg": b"[nlp]",
            f"{MODEL_DIR}/meta.json": b'{"name": "core_web_sm"}',
            f"{MODEL_DIR}/vocab/strings.json": b"[]",
            f"{MODEL_DIR}/tagger/model": b"weights",
            "en_core_web_sm-3.8.0.dist-info/METADATA": b"Name: en-core-web-sm",
            **(extra or {}),
        },
    )


def files_under(folder):
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


def test_unpack_keeps_only_the_model_folder(tmp_path):
    wheel = model_wheel(tmp_path)
    target = unpack_spacy_model(tmp_path)
    assert target == spacy_model_dir(tmp_path)
    assert target == tmp_path / "spacy" / "en_core_web_sm-3.8.0"
    assert files_under(target) == ["config.cfg", "meta.json", "tagger/model", "vocab/strings.json"]
    assert (target / "meta.json").read_bytes() == b'{"name": "core_web_sm"}'
    assert files_under(tmp_path / "spacy") == [
        f"en_core_web_sm-3.8.0/{name}" for name in files_under(target)
    ]  # no staging folder, no Python package
    assert not wheel.exists()


def test_unpack_rejects_paths_that_climb_out(tmp_path):
    wheel = model_wheel(tmp_path, {f"{MODEL_DIR}/../../../escaped.txt": b"gotcha"})
    with pytest.raises(DownloadError, match="unsafe path"):
        unpack_spacy_model(tmp_path)
    assert not any(p.name == "escaped.txt" for p in tmp_path.rglob("*"))
    assert not spacy_model_dir(tmp_path).exists()
    assert wheel.exists()


def test_unpack_rejects_absolute_paths(tmp_path):
    model_wheel(tmp_path, {f"{MODEL_DIR}//tmp/escaped.txt": b"gotcha"})
    with pytest.raises(DownloadError, match="unsafe path"):
        unpack_spacy_model(tmp_path)
    assert not spacy_model_dir(tmp_path).exists()


def test_unpack_rejects_a_wheel_without_the_model(tmp_path):
    build_wheel(
        tmp_path,
        {
            "en_core_web_sm/__init__.py": b"",
            f"{MODEL_DIR}/meta.json": b"{}",  # no config.cfg
        },
    )
    with pytest.raises(DownloadError, match="doesn't contain the spaCy model"):
        unpack_spacy_model(tmp_path)
    assert not (tmp_path / "spacy").exists() or files_under(tmp_path / "spacy") == []


def test_unpack_reuses_an_unpacked_model(tmp_path):
    target = spacy_model_dir(tmp_path)
    target.mkdir(parents=True)
    (target / "config.cfg").write_text("[nlp]", encoding="utf-8")
    # No wheel on disk: reading it would fail.
    assert unpack_spacy_model(tmp_path) == target


def test_unpack_replaces_a_leftover_staging_folder(tmp_path):
    staging = spacy_model_dir(tmp_path).with_name("en_core_web_sm-3.8.0.part")
    staging.mkdir(parents=True)
    (staging / "stale.bin").write_bytes(b"from a crashed run")
    model_wheel(tmp_path)
    target = unpack_spacy_model(tmp_path)
    assert "stale.bin" not in files_under(target)
    assert not staging.exists()
