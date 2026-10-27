"""Per-user folders for voice models and the speech cache, on each platform.

The platform is faked by replacing the `os` and `sys` that `dogear.paths` sees, not the
real modules, so pathlib keeps working on the machine running the tests.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from dogear import paths
from dogear.paths import cache_dir, models_dir


@pytest.fixture
def home(tmp_path, monkeypatch):
    folder = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: folder))
    return folder


def platform(monkeypatch, *, os_name="posix", sys_platform="linux", **env):
    monkeypatch.setattr(paths, "os", SimpleNamespace(name=os_name, environ=env))
    monkeypatch.setattr(paths, "sys", SimpleNamespace(platform=sys_platform))


def test_linux_defaults(config, home, monkeypatch):
    platform(monkeypatch)
    assert models_dir(config) == home / ".local" / "share" / "dogear" / "models"
    assert cache_dir(config) == home / ".cache" / "dogear"


def test_linux_follows_xdg(config, home, monkeypatch, tmp_path):
    platform(
        monkeypatch,
        XDG_DATA_HOME=str(tmp_path / "data"),
        XDG_CACHE_HOME=str(tmp_path / "cache"),
    )
    assert models_dir(config) == tmp_path / "data" / "dogear" / "models"
    assert cache_dir(config) == tmp_path / "cache" / "dogear"


def test_empty_xdg_variables_are_ignored(config, home, monkeypatch):
    platform(monkeypatch, XDG_DATA_HOME="", XDG_CACHE_HOME="")
    assert models_dir(config) == home / ".local" / "share" / "dogear" / "models"
    assert cache_dir(config) == home / ".cache" / "dogear"


def test_macos_defaults(config, home, monkeypatch, tmp_path):
    # XDG variables are a Linux convention; macOS ignores them.
    platform(monkeypatch, sys_platform="darwin", XDG_DATA_HOME=str(tmp_path / "xdg"))
    library = home / "Library"
    assert models_dir(config) == library / "Application Support" / "dogear" / "models"
    assert cache_dir(config) == library / "Caches" / "dogear"


def test_windows_uses_local_app_data(config, home, monkeypatch, tmp_path):
    local = tmp_path / "AppData" / "Local"
    platform(monkeypatch, os_name="nt", sys_platform="win32", LOCALAPPDATA=str(local))
    assert models_dir(config) == local / "dogear" / "models"
    assert cache_dir(config) == local / "dogear" / "Cache"


def test_windows_without_local_app_data(config, home, monkeypatch):
    platform(monkeypatch, os_name="nt", sys_platform="win32")
    local = home / "AppData" / "Local"
    assert models_dir(config) == local / "dogear" / "models"
    assert cache_dir(config) == local / "dogear" / "Cache"


@pytest.mark.parametrize(
    ("os_name", "sys_platform"), [("posix", "linux"), ("posix", "darwin"), ("nt", "win32")]
)
def test_config_overrides_every_platform(
    config, home, monkeypatch, tmp_path, os_name, sys_platform
):
    platform(monkeypatch, os_name=os_name, sys_platform=sys_platform)
    config["models"]["dir"] = str(tmp_path / "voices")
    config["render"]["cache_dir"] = str(tmp_path / "speech-cache")
    assert models_dir(config) == tmp_path / "voices"
    assert cache_dir(config) == tmp_path / "speech-cache"


def test_config_paths_expand_the_home_folder(config, monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))  # where expanduser looks on Linux and macOS
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # and on Windows
    config["models"]["dir"] = "~/voices"
    config["render"]["cache_dir"] = "~/speech-cache"
    assert models_dir(config) == tmp_path / "voices"
    assert cache_dir(config) == tmp_path / "speech-cache"
