from dogear.output.playlist import EXTENSION, PlaylistEntry, m3u_text, write_playlist

ENTRIES = [
    PlaylistEntry("01 - Chapter One.mp3", "Chapter One", 61.4),
    PlaylistEntry("02 - Café.mp3", "Café:\nthe sequel", 2.6),
]


def test_extended_m3u_with_relative_paths_and_crlf():
    assert m3u_text(ENTRIES) == (
        "#EXTM3U\r\n"
        "#EXTINF:61,Chapter One\r\n"
        "01 - Chapter One.mp3\r\n"
        "#EXTINF:3,Café: the sequel\r\n"
        "02 - Café.mp3\r\n"
    )


def test_written_as_utf8_without_bom_keeping_crlf(tmp_path):
    path = tmp_path / f"book{EXTENSION}"
    write_playlist(path, ENTRIES)
    data = path.read_bytes()
    assert data.startswith(b"#EXTM3U\r\n")
    assert "Café".encode() in data
    assert b"\n" not in data.replace(b"\r\n", b"")
    assert EXTENSION == ".m3u"
