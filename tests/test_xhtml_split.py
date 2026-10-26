import pytest
from lxml import etree

from dogear.extract.xhtml_split import split_body

XHTML = "http://www.w3.org/1999/xhtml"


def body_of(inner: str) -> etree._Element:
    return etree.fromstring(f'<body xmlns="{XHTML}">{inner}</body>')


def by_id(body: etree._Element, element_id: str) -> etree._Element:
    return next(el for el in body.iter() if el.get("id") == element_id)


def markup(el: etree._Element) -> str:
    return etree.tostring(el, encoding="unicode").replace(f' xmlns="{XHTML}"', "")


def test_no_starts_returns_the_body_unchanged():
    body = body_of("<p>One</p>")
    assert split_body(body, []) == [body]
    assert markup(body) == "<body><p>One</p></body>"


def test_cut_inside_a_paragraph_keeps_the_text_on_each_side():
    body = body_of('<p>Before <a id="x"/>after <em>it</em>.</p><p>Next</p>')
    first, second = split_body(body, [by_id(body, "x")])
    assert markup(first) == "<body><p>Before </p></body>"
    assert markup(second) == '<body><p><a id="x"/>after <em>it</em>.</p><p>Next</p></body>'


def test_enclosing_elements_are_copied_without_their_id():
    body = body_of(
        '<section id="s" xml:lang="fr" class="c"><p>a</p><h2 id="h">T</h2><p>b</p></section>'
        "tail<p>c</p>"
    )
    first, second = split_body(body, [by_id(body, "h")])
    assert (
        markup(first) == '<body><section id="s" xml:lang="fr" class="c"><p>a</p></section></body>'
    )
    assert markup(second) == (
        '<body><section xml:lang="fr" class="c"><h2 id="h">T</h2><p>b</p></section>'
        "tail<p>c</p></body>"
    )


def test_several_starts_including_one_inside_another():
    body = body_of(
        '<p>front</p><div id="part"><h1>Part</h1><div id="ch1"><p>one</p></div>'
        '<div id="ch2"><p>two</p></div></div><p>end</p>'
    )
    starts = [by_id(body, i) for i in ("part", "ch1", "ch2")]
    parts = split_body(body, starts)
    assert [markup(p) for p in parts] == [
        "<body><p>front</p></body>",
        '<body><div id="part"><h1>Part</h1></div></body>',
        '<body><div><div id="ch1"><p>one</p></div></div></body>',
        '<body><div><div id="ch2"><p>two</p></div></div><p>end</p></body>',
    ]


def test_body_itself_is_not_a_start():
    body = body_of("<p>One</p>")
    with pytest.raises(ValueError):
        split_body(body, [body])
