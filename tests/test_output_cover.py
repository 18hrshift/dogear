import logging

from audio_builder import image_bytes

from dogear.document import Cover
from dogear.output.cover import write_cover


def test_no_cover_gives_none(tmp_path):
    assert write_cover(None, tmp_path) is None


def test_jpeg_and_png_get_their_own_demuxer(tmp_path):
    jpeg = write_cover(Cover(image_bytes("JPEG"), "image/jpeg"), tmp_path)
    assert jpeg.path.name == "cover.jpg"
    assert jpeg.input_args() == ["-f", "jpeg_pipe", "-i", str(jpeg.path)]
    png = write_cover(Cover(image_bytes("PNG"), "image/png"), tmp_path)
    assert png.path.read_bytes() == image_bytes("PNG")
    assert png.demuxer == "png_pipe"


def test_format_comes_from_the_bytes_not_the_label(tmp_path):
    cover = write_cover(Cover(image_bytes("PNG"), "image/jpeg"), tmp_path)
    assert cover.demuxer == "png_pipe"


def test_something_else_is_left_out_with_a_warning(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        assert write_cover(Cover(b"#EXTM3U\nhttp://example.com/x", "image/png"), tmp_path) is None
    assert "isn't a JPEG or PNG" in caplog.text
    assert list(tmp_path.iterdir()) == []
