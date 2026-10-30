"""What a standalone build carries: its folder, programs, espeak-ng data, and voice files."""

import os
from types import SimpleNamespace

from dogear import bundle

SHA = "a" * 64
OTHER_SHA = "b" * 64


def test_a_normal_install_has_no_bundled_folder():
    assert bundle.folder() is None
    assert bundle.program("ffmpeg") is None
    assert bundle.espeak_data("espeak-ng") is None
    assert bundle.model("kokoro/onnx/model.onnx", SHA) is None


def test_the_folder_is_inside_pyinstallers_folder(standalone_build):
    assert bundle.folder() == standalone_build.folder
    assert standalone_build.folder.parent.name == "_internal"


def test_other_freezers_keep_the_folder_by_the_program(tmp_path, monkeypatch):
    fake_sys = SimpleNamespace(frozen=True, executable=str(tmp_path / "dogear"))
    monkeypatch.setattr(bundle, "sys", fake_sys)
    assert bundle.folder() == tmp_path / bundle.FOLDER


def test_bundled_programs_are_found_by_name(standalone_build):
    ffmpeg = standalone_build.add_program("ffmpeg")
    assert bundle.program("ffmpeg") == ffmpeg
    assert bundle.program("ffprobe") is None  # this build doesn't carry it


def test_windows_programs_end_in_exe(standalone_build, monkeypatch):
    monkeypatch.setattr(bundle, "os", SimpleNamespace(name="nt"))
    path = standalone_build.folder / bundle.TOOLS / "ffmpeg.exe"
    path.write_text("a bundled program", encoding="utf-8")
    assert bundle.program("ffmpeg") == path


def test_espeak_data_is_given_only_to_the_bundled_espeak(standalone_build, tmp_path):
    espeak = standalone_build.add_program("espeak-ng")
    assert bundle.espeak_data(str(espeak)) == espeak.parent
    assert bundle.espeak_data(str(tmp_path / "elsewhere" / "espeak-ng")) is None


def test_a_bundled_model_is_used_when_its_checksum_matches(standalone_build):
    path = standalone_build.add_model("kokoro/voices/af_heart.bin", SHA)
    assert bundle.model("kokoro/voices/af_heart.bin", SHA) == path


def test_a_bundled_model_with_another_checksum_is_not_used(standalone_build):
    standalone_build.add_model("kokoro/voices/af_heart.bin", SHA)
    assert bundle.model("kokoro/voices/af_heart.bin", OTHER_SHA) is None


def test_models_missing_from_the_manifest_or_the_disk_are_not_used(standalone_build):
    assert bundle.model("kokoro/voices/bf_emma.bin", SHA) is None
    path = standalone_build.add_model("kokoro/voices/af_heart.bin", SHA)
    path.unlink()
    assert bundle.model("kokoro/voices/af_heart.bin", SHA) is None


def test_bundled_model_folders_are_found_by_their_downloads_checksum(standalone_build):
    folder = standalone_build.add_model_folder("spacy/en_core_web_sm-3.8.0", SHA)
    assert bundle.model("spacy/en_core_web_sm-3.8.0", SHA) == folder


def test_a_normal_install_runs_programs_in_its_own_environment():
    assert bundle.program_environment() is None


def test_programs_get_the_library_path_from_before_the_build_changed_it(
    standalone_build, monkeypatch
):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/dogear/_internal:/usr/local/lib")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib")
    env = bundle.program_environment()
    assert env["LD_LIBRARY_PATH"] == "/usr/local/lib"
    assert "LD_LIBRARY_PATH_ORIG" not in env


def test_programs_get_no_library_path_if_there_was_none(standalone_build, monkeypatch):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/dogear/_internal")
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    env = bundle.program_environment()
    assert "LD_LIBRARY_PATH" not in env
    assert env["PATH"] == os.environ["PATH"]


def test_a_build_without_a_manifest_bundles_no_models(standalone_build):
    (standalone_build.folder / bundle.MODELS / bundle.MANIFEST).unlink()
    bundle._manifest.cache_clear()
    assert bundle.model("kokoro/voices/af_heart.bin", SHA) is None
