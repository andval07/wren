import pytest

from wren import css
from wren.html import Element, parse


def styled(source, sheet=""):
    dom = parse(source)
    css.style(dom, css.sort_rules(css.default_rules(), css.parse(sheet)))
    return dom


def find(node, tag, ident=None):
    if isinstance(node, Element) and node.tag == tag and \
            (ident is None or node.attributes.get("id") == ident):
        return node
    for child in node.children:
        found = find(child, tag, ident)
        if found is not None:
            return found
    return None


def test_parse_rules_and_declarations():
    rules = css.parse("p { color: red; margin: 1px 2px } h1,h2{font-size:3em}")
    assert len(rules) == 3
    assert rules[0][1] == {"color": "red", "margin-top": "1px",
                           "margin-right": "2px", "margin-bottom": "1px",
                           "margin-left": "2px"}


def test_comments_at_rules_and_bad_selectors_skipped():
    rules = css.parse("""
        /* a comment */
        @media (max-width: 600px) { p { color: red } }
        @import url(x.css);
        a:hover { color: blue }
        input[type=text] { color: blue }
        b { font-weight: bold }
    """)
    assert len(rules) == 1
    assert rules[0][1] == {"font-weight": "bold"}


@pytest.mark.parametrize("selector,spec", [
    ("p", 1), (".a", 10), ("#x", 100), ("p.a.b", 21),
    ("div p", 2), ("#x .a p", 111), ("ul > li", 2), ("*", 0),
])
def test_specificity(selector, spec):
    sel, _ = css.parse(selector + " {}")[0]
    assert sel.specificity == spec


def test_specificity_beats_source_order():
    dom = styled('<p id=x class=c>t</p>', "#x { color: red } .c { color: blue }"
                 " p { color: green }")
    assert find(dom, "p").style["color"] == "red"


def test_later_rule_wins_on_tie():
    dom = styled("<p>t</p>", "p { color: red } p { color: blue }")
    assert find(dom, "p").style["color"] == "blue"


def test_author_beats_browser_sheet():
    # browser.css sets h1 to 2em with a two-part selector-free rule;
    # the page's own rule must still win
    dom = styled("<h1>t</h1>", "h1 { font-size: 10px }")
    assert find(dom, "h1").style["font-size"] == "10px"


def test_inline_style_wins():
    dom = styled('<p id=x style="color: lime">t</p>', "#x { color: red }")
    assert find(dom, "p").style["color"] == "lime"


def test_descendant_and_child_selectors():
    sheet = "div span { color: red } div > b { color: blue }"
    dom = styled("<div><p><span id=s>a</span><b id=b1>b</b></p><b id=b2>c</b>"
                 "</div>", sheet)
    assert find(dom, "span").style["color"] == "red"
    assert find(dom, "b", "b1").style["color"] == "black"
    assert find(dom, "b", "b2").style["color"] == "blue"


def test_inheritance_and_non_inheritance():
    dom = styled("<div><p>t</p></div>",
                 "div { color: red; background-color: blue }")
    p = find(dom, "p")
    assert p.style["color"] == "red"
    assert "background-color" not in p.style
    assert p.children[0].style["color"] == "red"  # text node


def test_font_size_units_resolve_against_parent():
    dom = styled("<div><p><span>t</span></p></div>",
                 "div { font-size: 20px } p { font-size: 150% } span "
                 "{ font-size: 0.5em }")
    assert find(dom, "p").style["font-size"] == "30px"
    assert find(dom, "span").style["font-size"] == "15px"
    assert find(dom, "h1") is None


def test_default_sheet():
    dom = styled("<title>t</title><h1>a</h1><b>b</b><a href=x>c</a>")
    assert find(dom, "h1").style["font-size"] == "32px"
    assert find(dom, "b").style["font-weight"] == "bold"
    assert find(dom, "a").style["color"] == "#0000ee"
    assert find(dom, "head").style["display"] == "none"


@pytest.mark.parametrize("value,expected", [
    ("red", "#ff0000"), ("#abc", "#aabbcc"), ("#A1B2C3", "#a1b2c3"),
    ("rgb(255, 0, 10)", "#ff000a"), ("rgb(100% 0% 0%)", "#ff0000"),
    ("transparent", None), ("rgba(0,0,0,0)", None), ("nonsense", None),
    ("#12", None),
])
def test_parse_color(value, expected):
    assert css.parse_color(value) == expected


@pytest.mark.parametrize("value,px", [
    ("10px", 10), ("2em", 32), ("1.5rem", 24), ("12pt", 16), ("50%", 50),
    ("auto", 0), ("bad", 0),
])
def test_length_px(value, px):
    assert css.length_px(value, 16, 100) == px
