"""Writing an EPUB's files into its zip container (OCF), the way reading apps expect.

The `mimetype` file comes first and uncompressed, so a program can tell an EPUB from
its opening bytes. Audio and images are stored as they are: they're compressed already.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
MIMETYPE = b"application/epub+zip"
_ALREADY_COMPRESSED = (".mp3", ".jpg", ".jpeg", ".png")


def write_container(path: Path, package_path: str, files: list[tuple[str, bytes | Path]]) -> None:
    """Zip an EPUB at `path`. `files` are (name inside the book, its bytes or a file to
    copy); `package_path` is the package document's name among them."""
    names = [name for name, _ in files]
    if package_path not in names:
        raise ValueError(f"The package document {package_path} isn't among the book's files.")
    if len(set(names)) != len(names):
        raise ValueError("Two of the book's files have the same name.")
    with zipfile.ZipFile(path, "w") as book:
        book.writestr(zipfile.ZipInfo("mimetype"), MIMETYPE, compress_type=zipfile.ZIP_STORED)
        book.writestr("META-INF/container.xml", container_xml(package_path), zipfile.ZIP_DEFLATED)
        for name, content in files:
            kind = (
                zipfile.ZIP_STORED if name.endswith(_ALREADY_COMPRESSED) else zipfile.ZIP_DEFLATED
            )
            if isinstance(content, Path):
                book.write(content, name, kind)
            else:
                book.writestr(name, content, kind)


def container_xml(package_path: str) -> bytes:
    """META-INF/container.xml, which tells a reading app where the package document is."""
    root = etree.Element(f"{{{CONTAINER_NS}}}container", version="1.0", nsmap={None: CONTAINER_NS})
    rootfiles = etree.SubElement(root, f"{{{CONTAINER_NS}}}rootfiles")
    etree.SubElement(
        rootfiles,
        f"{{{CONTAINER_NS}}}rootfile",
        {"full-path": package_path, "media-type": "application/oebps-package+xml"},
    )
    return etree.tostring(root, xml_declaration=True, encoding="utf-8", pretty_print=True)
