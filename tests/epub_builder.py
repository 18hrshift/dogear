"""Write small synthetic EPUBs for tests.

`build_epub` writes an EPUB 3 by default: `mimetype` first and stored uncompressed,
META-INF/container.xml, an OPF, a navigation document, and one XHTML file per `Doc`.
With `nav=False, ncx=True` it writes an EPUB 2 with an NCX table of contents instead.
The table of contents lists each `Doc` with a `toc_title`, or the `Toc` tree passed as
`toc`. `Resource`s are other manifest files, such as images.
Text arguments are inserted as raw XML, so tests can use entities and markup in them.
"""

from __future__ import annotations

import itertools
import zipfile
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote


@dataclass
class Doc:
    href: str  # relative to the OPF folder, not URL-encoded: "text/chapter 1.xhtml"
    body: str = ""  # inner XHTML of <body>
    toc_title: str | None = None  # listed in the table of contents when set
    landmark: str | None = None  # epub:type tokens of a landmarks link when set
    body_attrs: str = ""
    html_attrs: str = ""
    linear: bool = True
    media_type: str = "application/xhtml+xml"
    raw: str | bytes | None = None  # the whole file, instead of a generated XHTML document
    missing: bool = False  # listed in the manifest but not written to the archive


@dataclass
class Toc:
    href: str  # relative to the OPF folder, not URL-encoded, with an optional "#fragment"
    title: str
    children: Sequence[Toc] = ()


@dataclass
class Resource:
    href: str  # relative to the OPF folder, not URL-encoded
    data: bytes | None  # None: listed in the manifest but not written to the archive
    media_type: str
    properties: str = ""
    id: str | None = None  # default: res1, res2, ...


def xhtml(body: str, *, body_attrs: str = "", html_attrs: str = "", title: str = "Doc") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" {html_attrs}>
<head><title>{title}</title></head>
<body {body_attrs}>
{body}
</body>
</html>
"""


def container_xml(opf_path: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="{opf_path}" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


def encryption_xml(paths: Sequence[str], algorithm: str) -> str:
    entries = "".join(
        f"""<enc:EncryptedData>
  <enc:EncryptionMethod Algorithm="{algorithm}"/>
  <enc:CipherData><enc:CipherReference URI="{quote(p)}"/></enc:CipherData>
</enc:EncryptedData>"""
        for p in paths
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container"
  xmlns:enc="http://www.w3.org/2001/04/xmlenc#">{entries}</encryption>
"""


def build_epub(
    path: Path,
    docs: Sequence[Doc],
    *,
    title: str | None = "Test Book",
    creators: Sequence[str] = ("Ada Writer",),
    language: str | None = "en",
    identifiers: Sequence[tuple[str, str]] = (("bookid", "urn:uuid:0000-test"),),
    unique_identifier: str = "bookid",
    publisher: str | None = None,
    nav: bool = True,
    nav_in_spine: bool = False,
    ncx: bool = False,
    page_list: Sequence[tuple[str, str, str]] = (),  # (doc href, element id, label)
    spine: Sequence[str] | None = None,  # manifest ids in reading order; default: docs order
    opf_dir: str = "OEBPS",
    files: Mapping[str, str | bytes] | None = None,  # archive path -> content, added last
    toc: Sequence[Toc] | None = None,  # default: a flat list of the docs with a toc_title
    resources: Sequence[Resource] = (),
    cover_meta: str | None = None,  # content of an EPUB 2 <meta name="cover">
    guide: Sequence[tuple[str, str]] = (),  # (type, href) references
) -> Path:
    def in_opf_dir(name: str) -> str:
        return f"{opf_dir}/{name}" if opf_dir else name

    ids = [f"doc{i}" for i, _ in enumerate(docs, start=1)]
    if toc is None:
        toc = [Toc(d.href, d.toc_title) for d in docs if d.toc_title]
    opf_path = in_opf_dir("content.opf")
    contents: dict[str, str | bytes] = {
        "META-INF/container.xml": container_xml(opf_path),
        opf_path: _opf(
            docs,
            ids,
            title=title,
            creators=creators,
            language=language,
            identifiers=identifiers,
            unique_identifier=unique_identifier,
            publisher=publisher,
            nav=nav,
            nav_in_spine=nav_in_spine,
            ncx=ncx,
            spine=spine,
            resources=resources,
            cover_meta=cover_meta,
            guide=guide,
        ),
    }
    if nav:
        contents[in_opf_dir("nav.xhtml")] = _nav(docs, toc, page_list)
    if ncx:
        contents[in_opf_dir("toc.ncx")] = _ncx(toc, page_list)
    for doc in docs:
        if doc.missing:
            continue
        content = doc.raw
        if content is None:
            content = xhtml(doc.body, body_attrs=doc.body_attrs, html_attrs=doc.html_attrs)
        contents[in_opf_dir(doc.href)] = content
    for resource in resources:
        if resource.data is not None:
            contents[in_opf_dir(resource.href)] = resource.data
    contents.update(files or {})

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")  # stored
        for name, content in contents.items():
            zf.writestr(name, content, compress_type=zipfile.ZIP_DEFLATED)
    return path


def _opf(
    docs: Sequence[Doc],
    ids: Sequence[str],
    *,
    title: str | None,
    creators: Sequence[str],
    language: str | None,
    identifiers: Sequence[tuple[str, str]],
    unique_identifier: str,
    publisher: str | None,
    nav: bool,
    nav_in_spine: bool,
    ncx: bool,
    spine: Sequence[str] | None,
    resources: Sequence[Resource],
    cover_meta: str | None,
    guide: Sequence[tuple[str, str]],
) -> str:
    meta = [f'<dc:identifier id="{id_}">{value}</dc:identifier>' for id_, value in identifiers]
    meta += [f"<dc:title>{title}</dc:title>"] if title is not None else []
    meta += [f"<dc:creator>{c}</dc:creator>" for c in creators]
    meta += [f"<dc:language>{language}</dc:language>"] if language else []
    meta += [f"<dc:publisher>{publisher}</dc:publisher>"] if publisher else []
    meta += [f'<meta name="cover" content="{cover_meta}"/>'] if cover_meta is not None else []
    items = [
        f'<item id="{id_}" href="{quote(d.href)}" media-type="{d.media_type}"/>'
        for id_, d in zip(ids, docs, strict=True)
    ]
    if nav:
        items.append(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        )
    if ncx:
        items.append('<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>')
    for i, r in enumerate(resources, start=1):
        props = f' properties="{r.properties}"' if r.properties else ""
        items.append(
            f'<item id="{r.id or f"res{i}"}" href="{quote(r.href)}" '
            f'media-type="{r.media_type}"{props}/>'
        )
    refs_xml = "".join(
        f'<reference type="{kind}" href="{quote(href)}" title="{kind}"/>' for kind, href in guide
    )
    guide_xml = f"<guide>{refs_xml}</guide>" if guide else ""
    linear = {id_: d.linear for id_, d in zip(ids, docs, strict=True)}
    order = list(spine) if spine is not None else list(ids)
    if nav_in_spine:
        order.insert(0, "nav")
    refs = [
        f'<itemref idref="{id_}" linear="{"yes" if linear.get(id_, True) else "no"}"/>'
        for id_ in order
    ]
    return f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="{"3.0" if nav else "2.0"}"
  unique-identifier="{unique_identifier}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    {"".join(meta)}
  </metadata>
  <manifest>{"".join(items)}</manifest>
  <spine{' toc="ncx"' if ncx else ""}>{"".join(refs)}</spine>{guide_xml}
</package>
"""


def _quote_href(href: str) -> str:
    return quote(href, safe="/#")


def _nav_list(entries: Sequence[Toc]) -> str:
    items = "".join(
        f'<li><a href="{_quote_href(e.href)}">{e.title}</a>'
        f"{_nav_list(e.children) if e.children else ''}</li>"
        for e in entries
    )
    return f"<ol>{items}</ol>"


def _nav(docs: Sequence[Doc], toc: Sequence[Toc], page_list: Sequence[tuple[str, str, str]]) -> str:
    landmarks = "".join(
        f'<li><a epub:type="{d.landmark}" href="{quote(d.href)}">{d.landmark}</a></li>'
        for d in docs
        if d.landmark
    )
    pages = "".join(
        f'<li><a href="{quote(href)}#{id_}">{label}</a></li>' for href, id_, label in page_list
    )
    body = f'<nav epub:type="toc" id="toc"><h1>Contents</h1>{_nav_list(toc)}</nav>'
    if landmarks:
        body += f'<nav epub:type="landmarks" hidden=""><ol>{landmarks}</ol></nav>'
    if pages:
        body += f'<nav epub:type="page-list" hidden=""><ol>{pages}</ol></nav>'
    return xhtml(body, title="Contents")


def _nav_points(entries: Sequence[Toc], numbers: Iterator[int]) -> str:
    points = []
    for e in entries:
        n = next(numbers)
        points.append(
            f'<navPoint id="np{n}" playOrder="{n}"><navLabel><text>{e.title}</text></navLabel>'
            f'<content src="{_quote_href(e.href)}"/>{_nav_points(e.children, numbers)}</navPoint>'
        )
    return "".join(points)


def _ncx(toc: Sequence[Toc], page_list: Sequence[tuple[str, str, str]]) -> str:
    points = _nav_points(toc, itertools.count(1))
    pages = "".join(
        f'<pageTarget id="pt{i}" type="normal" value="{label}">'
        f'<navLabel><text>{label}</text></navLabel><content src="{quote(href)}#{id_}"/>'
        "</pageTarget>"
        for i, (href, id_, label) in enumerate(page_list, start=1)
    )
    page_xml = f"<pageList>{pages}</pageList>" if pages else ""
    return f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="urn:uuid:0000-test"/></head>
<docTitle><text>Test Book</text></docTitle>
<navMap>{points}</navMap>{page_xml}
</ncx>
"""
