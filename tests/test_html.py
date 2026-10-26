from wren.html import Element, Text, decode_entities, parse, tree_to_lines


def dump(source):
    return "\n".join(tree_to_lines(parse(source)))


def find(node, tag):
    if isinstance(node, Element) and node.tag == tag:
        return node
    for child in node.children:
        found = find(child, tag)
        if found is not None:
            return found
    return None


def test_implicit_html_head_body():
    assert dump("<title>T</title><p>x") == "\n".join([
        "<html>", "  <head>", "    <title>", "      'T'",
        "  <body>", "    <p>", "      'x'",
    ])


def test_text_only_document():
    assert dump("hi") == "<html>\n  <body>\n    'hi'"


def test_p_closes_p():
    assert dump("<p>a<p>b") == "\n".join([
        "<html>", "  <body>", "    <p>", "      'a'", "    <p>", "      'b'",
    ])


def test_li_closes_li_but_not_nested_list():
    body = find(parse("<ul><li>a<ul><li>b</ul><li>c</ul>"), "ul")
    items = [c for c in body.children if isinstance(c, Element)]
    assert [c.tag for c in items] == ["li", "li"]
    assert find(items[0], "ul") is not None


def test_block_closes_open_p():
    body = find(parse("<p>a<div>b</div>"), "body")
    assert [c.tag for c in body.children] == ["p", "div"]


def test_void_and_self_closing():
    body = find(parse("a<br>b<img src=x.png/>c"), "body")
    assert [getattr(c, "tag", None) for c in body.children] == \
        [None, "br", None, "img", None]


def test_attributes_quoted_unquoted_and_bare():
    a = find(parse('<a href="/x?a=1&amp;b=2" class=big hidden>t</a>'), "a")
    assert a.attributes == {"href": "/x?a=1&b=2", "class": "big", "hidden": ""}


def test_uppercase_tags_and_attrs():
    a = find(parse('<A HREF="/x">t</A>'), "a")
    assert a.attributes["href"] == "/x"


def test_comments_and_doctype_dropped():
    assert dump("<!DOCTYPE html><!-- hi <p>no</p> -->x") == \
        "<html>\n  <body>\n    'x'"


def test_script_content_is_raw_text():
    script = find(parse("<script>if (a < b && c) { x = '</p>' }</script>"),
                  "script")
    assert script.children[0].text == "if (a < b && c) { x = '</p>' }"


def test_stray_end_tags_ignored():
    assert dump("</div>a</span>") == "<html>\n  <body>\n    'a'"


def test_unclosed_tags_closed_at_eof():
    b = find(parse("<div><b>bold"), "b")
    assert isinstance(b.children[0], Text)
    assert b.parent.tag == "div"


def test_lone_less_than_is_text():
    assert find(parse("1 < 2"), "body").children[0].text == "1 < 2"


def test_entities():
    assert decode_entities("&lt;a&gt; &amp; &copy; &#65;&#x42;") == \
        "<a> & © AB"
    assert decode_entities("AT&T &unknown; &") == "AT&T &unknown; &"


def test_parent_links():
    dom = parse("<div><p>x</p></div>")
    p = find(dom, "p")
    assert p.parent.tag == "div"
    assert p.children[0].parent is p
