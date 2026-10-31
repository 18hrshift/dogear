"""THIRD-PARTY-NOTICES.txt: what it lists, and that each part's license text is in it."""

import io
import tarfile
from importlib import metadata

import pytest
from dogear_build import BuildError, notices
from dogear_build.notices import license_files, license_name, runtime_distributions, write_notices
from dogear_build.pins import Pins, Source


def names(dists):
    return {d.metadata["Name"].lower().replace("_", "-") for d in dists}


def test_runtime_packages_are_dogears_requirements_and_theirs():
    found = names(runtime_distributions())
    assert {"onnxruntime", "spacy", "misaki", "numpy", "lxml", "num2words", "thinc"} <= found
    assert "dogear" not in found
    assert not {"pytest", "ruff", "reportlab", "pyinstaller"} & found  # dev and build only


def test_license_files_come_from_the_licenses_folder_and_by_name():
    numpy = license_files(metadata.distribution("numpy"))
    assert any(f.parts[1] == "licenses" for f in numpy)
    onnxruntime = [f.name for f in license_files(metadata.distribution("onnxruntime"))]
    assert "LICENSE" in onnxruntime and "ThirdPartyNotices.txt" in onnxruntime


def test_license_names_stay_on_one_line():
    for dist in runtime_distributions():
        assert "\n" not in license_name(dist)
    assert license_name(metadata.distribution("misaki")) != ""


def make_archive(path, top, files):
    with tarfile.open(path, "w:gz") as tar:
        for name, text in files.items():
            data = text.encode()
            info = tarfile.TarInfo(f"{top}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


def source(key, **changes):
    fields = dict(
        key=key,
        name=key.title(),
        version="1.0",
        license="MIT",
        homepage="https://example.org",
        url=f"https://example.org/{key}-1.0.tar.gz",
        mirrors=(),
        sha256="a" * 64,
        size=1,
        license_files=("COPYING",),
        bundled=f"the {key} program",
    )
    return Source(**{**fields, **changes})


@pytest.fixture
def spacy_model(tmp_path):
    folder = tmp_path / "en_core_web_sm-3.8.0"
    folder.mkdir()
    (folder / "LICENSE").write_text("MIT License for the model", encoding="utf-8")
    (folder / "LICENSES_SOURCES").write_text("Sources of the model's data", encoding="utf-8")
    return folder


def test_notices_hold_every_part_and_its_license(tmp_path, spacy_model, monkeypatch):
    # PyInstaller is installed for builds only; its part is checked below when it is.
    monkeypatch.setattr(notices, "_pyinstaller", lambda: ["PyInstaller's part"])
    program, helper = source("program"), source("helper", bundled="", license_files=())
    make_archive(tmp_path / program.archive_name, "program-1.0", {"COPYING": "Program license"})
    pins = Pins(platforms={}, sources={"program": program, "helper": helper})
    path = tmp_path / notices.NAME
    write_notices(path, pins, tmp_path, spacy_model)
    text = path.read_text(encoding="utf-8")
    assert "Program 1.0\nLicense: MIT\nIn this copy: the program program" in text
    assert f"Source code, exactly as built: {program.url}" in text
    assert "Program license" in text
    assert "Helper" not in text  # used only to build, so not bundled
    assert "Kokoro-82M" in text and "MIT License for the model" in text
    assert "Python " in text and "PSF" in text
    for dist in runtime_distributions():
        assert f"\n{dist.metadata['Name']} {dist.version}\n" in text
    assert "PyInstaller's part" in text


def test_pyinstallers_part_has_its_license():
    pytest.importorskip("PyInstaller", reason="installed with --group installer")
    lines = notices._pyinstaller()
    assert lines[0].startswith("PyInstaller ")
    assert any("GNU GENERAL PUBLIC LICENSE" in line for line in lines)


def test_a_license_file_missing_from_an_archive_stops_the_build(tmp_path, spacy_model):
    program = source("program", license_files=("LICENSE.md",))
    make_archive(tmp_path / program.archive_name, "program-1.0", {"COPYING": "text"})
    pins = Pins(platforms={}, sources={"program": program})
    with pytest.raises(BuildError, match="has no LICENSE.md"):
        write_notices(tmp_path / notices.NAME, pins, tmp_path, spacy_model)
