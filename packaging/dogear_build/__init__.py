"""Building Dogear's standalone installers. `packaging/build.py` runs these steps in order.

Each module does one step: `pins` reads what to download, `fetch` downloads it, `programs`
builds ffmpeg and espeak-ng, `voice` gathers the default voice, `freeze` runs PyInstaller,
`assemble` puts the bundle together, `notices` writes the third-party notices, and
`linux`, `macos`, and `windows` make each platform's installer.
"""


class BuildError(Exception):
    """Something the person building can fix; the message says what."""
