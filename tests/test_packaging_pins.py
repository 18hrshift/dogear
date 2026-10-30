"""packaging/pins.toml and the platform names the installer build uses."""

from types import SimpleNamespace

import pytest
from dogear_build import BuildError, pins
from dogear_build.pins import load, platform_key

GOOD = """\
[platforms]
linux-x86_64 = {}

[sources.example]
name = "Example"
version = "1.0"
license = "MIT"
homepage = "https://example.org"
url = "https://example.org/example-1.0.tar.gz"
sha256 = "%s"
size = 10
license_files = ["COPYING"]
bundled = "example"
"""


def write_pins(tmp_path, text):
    path = tmp_path / "pins.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_real_pins_load_and_cover_every_installer_platform():
    loaded = load()
    assert set(loaded.platforms) == {"linux-x86_64", "macos-arm64", "windows-x86_64"}
    assert {"lame", "ffmpeg", "espeak-ng", "sonic"} <= set(loaded.sources)
    names = [source.archive_name for source in loaded.sources.values()]
    assert len(set(names)) == len(names)


def test_every_bundled_program_names_its_license_and_source():
    for source in load().sources.values():
        if source.bundled:
            assert source.license and source.license_files and source.url.startswith("https://")


def test_macos_names_its_oldest_version():
    assert load().platform("macos-arm64")["minimum_os"] == "14.0"


def test_an_unknown_platform_is_an_error():
    with pytest.raises(BuildError, match="aren't built for linux-riscv64"):
        load().platform("linux-riscv64")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (('sha256 = "%s"', 'sha256 = "abc"'), "64 lowercase hex"),
        (("https://example.org/example-1.0.tar.gz", "http://example.org/e.tar.gz"), "https URL"),
        (("example-1.0.tar.gz", "example-1.0.zip"), ".tar.gz or .tar.xz"),
        (("size = 10", "size = 0"), "size in bytes"),
        (('license_files = ["COPYING"]', "license_files = []"), "list its license_files"),
    ],
)
def test_mistakes_in_pins_stop_the_build(tmp_path, change, message):
    old, new = change
    text = GOOD.replace(old, new)
    if "%s" in text:
        text = text % ("a" * 64)
    with pytest.raises(BuildError, match=message):
        load(write_pins(tmp_path, text))


def test_archive_names_carry_the_checksum(tmp_path):
    [source] = load(write_pins(tmp_path, GOOD % ("a" * 64))).sources.values()
    assert source.archive_name == "example-1.0-aaaaaaaaaaaa.tar.gz"


@pytest.mark.parametrize(
    ("system", "machine", "key"),
    [
        ("linux", "x86_64", "linux-x86_64"),
        ("darwin", "arm64", "macos-arm64"),
        ("win32", "AMD64", "windows-x86_64"),
        ("linux", "aarch64", "linux-arm64"),
    ],
)
def test_platform_key(monkeypatch, system, machine, key):
    monkeypatch.setattr(pins, "sys", SimpleNamespace(platform=system))
    monkeypatch.setattr(pins.platform, "machine", lambda: machine)
    assert platform_key() == key
