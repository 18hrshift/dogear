"""The installers' own scripts and files: Linux's install.sh and uninstall.sh, the macOS
launcher and Info.plist, and the read-me files. The shell scripts run for real, in a
fake home folder, on Linux and macOS."""

import os
import plistlib
import subprocess
import tarfile

import pytest
from dogear_build import BuildError, linux, macos
from dogear_build.pins import load

posix_only = pytest.mark.skipif(os.name == "nt", reason="sh scripts for Linux and macOS")


def fake_bundle(folder):
    """A frozen dogear folder whose program records how it was run."""
    bundle = folder / "dogear"
    bundle.mkdir(parents=True)
    program = bundle / "dogear"
    program.write_text('#!/bin/sh\necho "dogear ran with: $*"\n', encoding="utf-8")
    program.chmod(0o755)
    (bundle / "THIRD-PARTY-NOTICES.txt").write_text("notices", encoding="utf-8")
    return bundle


def run_sh(script, home, *args):
    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    return subprocess.run(
        ["sh", str(script), *args], env=env, capture_output=True, text=True, check=False
    )


@pytest.fixture
def unpacked(tmp_path):
    """The Linux download, unpacked: a fake bundle beside the real scripts."""
    folder = tmp_path / "Dogear-linux"
    fake_bundle(folder)
    for name in linux.SCRIPTS:
        (folder / name).write_bytes((linux.FILES / name).read_bytes())
    return folder


@posix_only
def test_install_puts_dogear_in_the_menu_and_on_path(unpacked, tmp_path):
    home = tmp_path / "home"
    result = run_sh(unpacked / "install.sh", home)
    assert result.returncode == 0, result.stderr
    target = home / ".local" / "opt" / "dogear"
    assert (target / "dogear").is_file() and (target / "uninstall.sh").is_file()
    link = home / ".local" / "bin" / "dogear"
    assert os.readlink(link) == str(target / "dogear")
    desktop = (home / ".local" / "share" / "applications" / "dogear.desktop").read_text()
    assert f'Exec="{target}/dogear" serve' in desktop
    assert "Terminal=true" in desktop and "Name=Dogear" in desktop
    assert "keep it open while you use Dogear" in result.stdout


@posix_only
def test_install_again_replaces_the_old_copy(unpacked, tmp_path):
    home = tmp_path / "home"
    run_sh(unpacked / "install.sh", home)
    stale = home / ".local" / "opt" / "dogear" / "stale-file"
    stale.write_text("from an older version", encoding="utf-8")
    assert run_sh(unpacked / "install.sh", home).returncode == 0
    assert not stale.exists()


@posix_only
@pytest.mark.parametrize(
    ("home_name", "exec_path"),
    [
        ("my home", "my home"),
        ('say "hi"', 'say \\\\"hi\\\\"'),
        ("cost $5", "cost \\\\$5"),
        ("back\\slash", "back\\\\\\\\slash"),
        ("100%", "100%%"),
    ],
)
def test_desktop_entry_quotes_unusual_paths(unpacked, tmp_path, home_name, exec_path):
    home = tmp_path / home_name
    assert run_sh(unpacked / "install.sh", home).returncode == 0
    desktop = (home / ".local" / "share" / "applications" / "dogear.desktop").read_text()
    [line] = [line for line in desktop.splitlines() if line.startswith("Exec=")]
    expected = f"{tmp_path}/{exec_path}/.local/opt/dogear/dogear"
    assert line == f'Exec="{expected}" serve'


@posix_only
def test_uninstall_removes_what_install_added(unpacked, tmp_path):
    home = tmp_path / "home"
    run_sh(unpacked / "install.sh", home)
    result = run_sh(home / ".local" / "opt" / "dogear" / "uninstall.sh", home)
    assert result.returncode == 0, result.stderr
    assert not (home / ".local" / "opt" / "dogear").exists()
    assert not (home / ".local" / "bin" / "dogear").exists()
    assert not (home / ".local" / "share" / "applications" / "dogear.desktop").exists()
    assert "Dogear is uninstalled." in result.stdout


@posix_only
def test_uninstall_leaves_a_dogear_command_it_didnt_make(unpacked, tmp_path):
    home = tmp_path / "home"
    run_sh(unpacked / "install.sh", home)
    link = home / ".local" / "bin" / "dogear"
    link.unlink()
    link.symlink_to("/usr/bin/true")
    run_sh(home / ".local" / "opt" / "dogear" / "uninstall.sh", home)
    assert link.is_symlink()


@posix_only
def test_install_without_the_bundle_says_what_to_do(tmp_path):
    folder = tmp_path / "partial"
    folder.mkdir()
    (folder / "install.sh").write_bytes((linux.FILES / "install.sh").read_bytes())
    result = run_sh(folder / "install.sh", tmp_path / "home")
    assert result.returncode == 1
    assert "What to do: unpack the whole download" in result.stderr


def test_the_tarball_holds_the_bundle_scripts_and_read_me(tmp_path):
    frozen = fake_bundle(tmp_path / "frozen")
    output = linux.make_tarball(frozen, tmp_path, "Dogear-1.0-linux-x86_64", print)
    with tarfile.open(output) as tar:
        members = {m.name: m for m in tar.getmembers()}
    top = "Dogear-1.0-linux-x86_64"
    for name in ("install.sh", "uninstall.sh", "README.txt", "dogear/dogear"):
        assert f"{top}/{name}" in members
    assert members[f"{top}/install.sh"].mode == 0o755
    assert all(m.uid == 0 and m.uname == "" for m in members.values())


# macOS.


@posix_only
def test_the_mac_launcher_opens_terminal_running_dogear_serve(tmp_path):
    app = macos.make_app(fake_bundle(tmp_path / "frozen"), tmp_path / "it's here", "1.0", "14.0")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_open = fake_bin / "open"
    fake_open.write_text('#!/bin/sh\necho "$@" > "$OPENED"\n', encoding="utf-8")
    fake_open.chmod(0o755)
    env = {
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "TMPDIR": str(tmp_path),
        "OPENED": str(tmp_path / "opened.txt"),
    }
    program = app / "Contents" / "MacOS" / macos.EXECUTABLE
    subprocess.run([str(program)], env=env, check=True)
    command_file = tmp_path / "Dogear.command"
    assert (tmp_path / "opened.txt").read_text().split() == ["-a", "Terminal", str(command_file)]
    # The .command file runs the dogear inside the app, even with a quote in its path.
    ran = subprocess.run([str(command_file)], capture_output=True, text=True, check=True)
    assert ran.stdout == "dogear ran with: serve\n"


def test_the_app_names_its_program_and_minimum_macos(tmp_path):
    minimum = load().platform("macos-arm64")["minimum_os"]
    app = macos.make_app(fake_bundle(tmp_path / "frozen"), tmp_path, "1.2.3", minimum)
    with (app / "Contents" / "Info.plist").open("rb") as f:
        info = plistlib.load(f)
    assert info["CFBundleExecutable"] == macos.EXECUTABLE
    assert info["LSMinimumSystemVersion"] == minimum
    assert info["CFBundleShortVersionString"] == "1.2.3"
    assert (app / "Contents" / "Resources" / "dogear" / "dogear").is_file()


def test_the_mac_read_me_names_the_minimum_macos():
    major = load().platform("macos-arm64")["minimum_os"].split(".")[0]
    text = (macos.FILES / macos.README).read_text(encoding="utf-8")
    assert f"macOS {major} " in text


def test_a_busy_hdiutil_is_tried_again(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, check):
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.CalledProcessError(16, command)  # "Resource busy"

    monkeypatch.setattr(macos.subprocess, "run", fake_run)
    monkeypatch.setattr(macos.time, "sleep", lambda seconds: None)
    frozen = fake_bundle(tmp_path / "frozen")
    output = macos.make_dmg(frozen, tmp_path, tmp_path / "work", "Dogear-1.0", "1.0", "14.0", print)
    assert output == tmp_path / "Dogear-1.0.dmg"
    assert len(calls) == 2 and calls[0][:2] == ["hdiutil", "create"]


def test_hdiutil_failing_every_time_stops_the_build(tmp_path, monkeypatch):
    def fake_run(command, check):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(macos.subprocess, "run", fake_run)
    monkeypatch.setattr(macos.time, "sleep", lambda seconds: None)
    frozen = fake_bundle(tmp_path / "frozen")
    with pytest.raises(BuildError, match="couldn't make the disk image"):
        macos.make_dmg(frozen, tmp_path, tmp_path / "work", "Dogear-1.0", "1.0", "14.0", print)
