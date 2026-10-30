"""`dogear serve`: start the web page, say where to open it, and stop cleanly on Ctrl+C.

Output is plain sentences on stdout. The access key appears only in the links printed
here; the server's own request log is off, so it is never written anywhere else.
"""

from __future__ import annotations

import errno
import os
import signal
import socket
import sys
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import uvicorn

from dogear.config import Config
from dogear.errors import DogearError
from dogear.file_lock import FileLock
from dogear.web.access_key import AccessKey, load_or_make_key
from dogear.web.app import create_app
from dogear.web.settings import LOCAL_HOST, WebSettings, web_settings

GRACEFUL_SECONDS = 5  # for open connections to finish when stopping
# In the web folder, locked while a server uses the folder.
LOCK_FILE = "serve.lock"


@dataclass(frozen=True)
class ServeOptions:
    port: int | None = None  # None: web.port from the config
    lan: bool = False
    open_browser: bool = True
    config_file: Path | None = None


def serve(options: ServeOptions, config: Config, say: Callable[[str], None] = print) -> int:
    settings = web_settings(
        config, port=options.port, lan=options.lan, config_file=options.config_file
    )
    with lock_web_folder(settings.dir):
        return _serve(settings, options, config, say)


def _serve(
    settings: WebSettings, options: ServeOptions, config: Config, say: Callable[[str], None]
) -> int:
    key = load_or_make_key(settings.dir)
    listener = bind(settings)
    app = create_app(settings, config, key)
    local = start_link(LOCAL_HOST, settings.port, key)
    say(f"Dogear is running. Open this link in a web browser: {local}")
    if settings.lan:
        address = lan_address()
        if address:
            say(
                "On a phone or another computer on the same network, open: "
                f"{start_link(address, settings.port, key)}"
            )
        else:
            say("Dogear couldn't find this computer's address on the network.")
        say("Anyone on this network who has the link can use Dogear.")
    say(f"Books, what's made from them, and the access key are kept in {settings.dir}")
    say("Keep this window open while you use Dogear. Press Ctrl+C to stop.")
    sys.stdout.flush()
    if options.open_browser:
        webbrowser.open(local)
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            log_config=None,  # Dogear's own logging; nothing about requests
            access_log=False,  # the access link holds the key
            timeout_graceful_shutdown=GRACEFUL_SECONDS,
            lifespan="on",
        )
    )
    previous = _stop_on_sigterm()
    try:
        server.run(sockets=[listener])
    except KeyboardInterrupt:
        pass  # Ctrl+C: the server has already stopped the books and closed
    finally:
        signal.signal(signal.SIGTERM, previous)
        listener.close()
    say("Stopped.")
    return 0


def lock_web_folder(folder: Path) -> FileLock:
    """Keep the web folder to this server while it runs. A second server on the same
    folder would clear the first one's uploads and change its books under it."""
    folder.mkdir(parents=True, exist_ok=True)
    lock = FileLock.try_acquire(folder / LOCK_FILE)
    if lock is None:
        raise DogearError(
            f"Dogear is already running with the web folder {folder}.",
            hint="Use the link shown in the window where it's running. To run a second "
            "Dogear at the same time, give it its own folder with web.dir in a settings "
            "file.",
        )
    return lock


def bind(settings: WebSettings) -> socket.socket:
    """The listening socket, so a port that's taken is a plain error before anything else."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if os.name != "nt":
        # Restarting right after stopping reuses the port. (On Windows this option would
        # let two programs share a port, so it's left off there.)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind((settings.listen_host, settings.port))
        listener.listen(128)
    except OSError as e:
        listener.close()
        if e.errno in (errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", -1)):
            raise DogearError(
                f"Port {settings.port} is in use already. Dogear may be running in another window.",
                hint="If it is, use the link that window shows. If not, start Dogear with "
                f"--port {settings.port + 1}.",
            ) from None
        raise DogearError(
            f"Dogear couldn't listen on port {settings.port}: {e.strerror or e}.",
            hint="Choose another port with --port, such as 8766.",
        ) from None
    return listener


def start_link(host: str, port: int, key: AccessKey) -> str:
    return f"http://{host}:{port}/start?key={key.text}"


def lan_address() -> str | None:
    """This computer's address on its local network, or None if it has none. Connecting
    a UDP socket sends nothing; it only picks the interface a packet would leave by."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))  # an address reserved for documentation
        address = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    return None if address.startswith(("127.", "0.")) else address


def _stop_on_sigterm():
    """Treat SIGTERM (`docker stop`, a service manager) like Ctrl+C. The server handles
    it first and stops cleanly, then raises it again, which lands here."""

    def stop(signum, frame):
        raise KeyboardInterrupt

    return signal.signal(signal.SIGTERM, stop)
