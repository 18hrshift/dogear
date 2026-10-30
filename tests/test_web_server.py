"""`dogear serve` and its `[web]` settings: each setting changes what the server does."""

import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest
from web_samples import BASE, sample_app, sample_config, visitor

from dogear import cli, paths
from dogear.errors import ConfigError, DogearError
from dogear.web import server
from dogear.web.server import ServeOptions, bind, lock_web_folder, serve
from dogear.web.settings import web_settings


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture
def no_server(monkeypatch):
    """serve() without serving: uvicorn's run is replaced, and Ctrl+C pressed at once."""
    runs = []

    def run(self, sockets):
        runs.append([listener.getsockname() for listener in sockets])
        raise KeyboardInterrupt

    monkeypatch.setattr(server.uvicorn.Server, "run", run)
    opened = []
    monkeypatch.setattr(server.webbrowser, "open", opened.append)
    return SimpleNamespace(runs=runs, opened=opened)


def test_serve_says_where_to_go_and_stops_cleanly(tmp_path, no_server):
    config = sample_config(tmp_path)
    port = free_port()
    config["web"]["port"] = port
    said = []
    assert serve(ServeOptions(), config, said.append) == 0
    key = (tmp_path / "access-key.txt").read_text().strip()
    link = f"http://127.0.0.1:{port}/start?key={key}"
    assert said[0] == f"Dogear is running. Open this link in a web browser: {link}"
    assert said[-2] == "Keep this window open while you use Dogear. Press Ctrl+C to stop."
    assert said[-1] == "Stopped."
    assert no_server.opened == [link]
    assert no_server.runs == [[("127.0.0.1", port)]]


def test_no_browser_opens_none(tmp_path, no_server):
    config = sample_config(tmp_path)
    config["web"]["port"] = free_port()
    serve(ServeOptions(open_browser=False), config, lambda line: None)
    assert no_server.opened == []


def test_port_option_beats_the_config(tmp_path, no_server):
    config = sample_config(tmp_path)
    port = free_port()
    said = []
    serve(ServeOptions(port=port, open_browser=False), config, said.append)
    assert f"http://127.0.0.1:{port}/start?key=" in said[0]


def test_on_the_network_it_listens_everywhere_and_warns(tmp_path, no_server, monkeypatch):
    monkeypatch.setattr(server, "lan_address", lambda: "192.168.1.20")
    config = sample_config(tmp_path)
    port = free_port()
    said = []
    serve(ServeOptions(port=port, lan=True, open_browser=False), config, said.append)
    assert said[1].startswith(
        f"On a phone or another computer on the same network, open: http://192.168.1.20:{port}/start?key="
    )
    assert said[2] == "Anyone on this network who has the link can use Dogear."
    assert no_server.runs == [[("0.0.0.0", port)]]


def test_a_port_in_use_is_a_plain_error(tmp_path):
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        settings = web_settings(sample_config(tmp_path), port=port)
        with pytest.raises(DogearError, match=f"Port {port} is in use already") as raised:
            bind(settings)
    assert raised.value.hint.startswith("If it is, use the link that window shows.")


def test_a_second_server_on_the_same_folder_is_refused(tmp_path, no_server):
    config = sample_config(tmp_path)
    config["web"]["port"] = free_port()
    with lock_web_folder(tmp_path):
        with pytest.raises(DogearError) as raised:
            serve(ServeOptions(open_browser=False), config, lambda line: None)
        assert raised.value.message == f"Dogear is already running with the web folder {tmp_path}."
        assert raised.value.hint.startswith("Use the link shown in the window where it's running.")
        assert no_server.runs == []  # refused before listening or touching the books
    serve(ServeOptions(open_browser=False), config, lambda line: None)
    assert len(no_server.runs) == 1
    # The lock is let go when the server stops, so it can start again.
    serve(ServeOptions(open_browser=False), config, lambda line: None)
    assert len(no_server.runs) == 2


def test_the_port_setting_changes_the_port_and_the_host_check(tmp_path):
    config = sample_config(tmp_path)
    config["web"]["port"] = 9123
    app = sample_app(tmp_path, config, port=None)
    assert app.state.settings.port == 9123
    client = visitor(app)
    assert client.get("/", headers={"Host": "127.0.0.1:9123"}).status_code == 200
    assert client.get("/", headers={"Host": "127.0.0.1:8765"}).status_code == 400
    listener = bind(web_settings(config, port=free_port()))
    listener.close()


def test_the_upload_limit_setting_changes_the_limit(tmp_path):
    config = sample_config(tmp_path)
    config["web"]["max_upload_mb"] = 2
    client = visitor(sample_app(tmp_path, config))
    two_and_a_bit = b"x" * (2 * 1024 * 1024 + 10)
    assert client.post("/books", files={"book": ("a.pdf", two_and_a_bit, "")}).status_code == 413
    one_and_a_bit = b"x" * (1024 * 1024 + 10)
    response = client.post("/books", files={"book": ("a.pdf", one_and_a_bit, "")})
    assert response.status_code == 200
    assert "up to 2 MB" in client.get("/").text


def test_the_dir_setting_changes_where_books_are_kept(tmp_path):
    config = sample_config(tmp_path / "elsewhere")
    client = visitor(sample_app(tmp_path / "elsewhere", config))
    client.post("/books", files={"book": ("a.epub", b"ok", "")})
    [folder] = (tmp_path / "elsewhere" / "books").iterdir()
    assert (folder / "book.epub").read_bytes() == b"ok"


def test_the_usual_web_folder_is_in_the_data_folder(config, monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "_platform_dir", lambda kind: tmp_path / kind)
    assert paths.web_dir(config) == tmp_path / "data" / "web"
    config["web"]["dir"] = str(tmp_path / "mine")
    assert paths.web_dir(config) == tmp_path / "mine"


def test_the_read_timeout_setting_is_used(tmp_path):
    config = sample_config(tmp_path)
    config["web"]["read_timeout_seconds"] = 42
    assert web_settings(config).read_timeout_seconds == 42


@pytest.mark.parametrize(
    ("key", "value"),
    [("port", 0), ("port", 70000), ("max_upload_mb", 0), ("read_timeout_seconds", 0)],
)
def test_bad_web_settings_are_errors(tmp_path, key, value):
    config = sample_config(tmp_path)
    config["web"][key] = value
    with pytest.raises(ConfigError):
        web_settings(config)


def test_the_serve_command_passes_its_options(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(server, "serve", lambda options, config: seen.append(options) or 0)
    settings_file = tmp_path / "d.toml"
    settings_file.write_text("")
    argv = ["serve", "--port", "9000", "--lan", "--no-browser", "--config", str(settings_file)]
    assert cli.main(argv) == 0
    assert seen == [
        ServeOptions(port=9000, lan=True, open_browser=False, config_file=settings_file)
    ]


def test_python_dash_m_dogear_runs_the_command():
    result = subprocess.run(
        [sys.executable, "-m", "dogear", "--version"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert result.stdout.startswith("dogear ")


def test_the_samples_use_the_default_port(config):
    assert BASE.endswith(f":{config['web']['port']}")
