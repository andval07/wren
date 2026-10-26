from wren.engine import render_html
from wren.layout import DrawRect, DrawText, FixedMetrics


def texts(source, width=800):
    page = render_html(source, None, width, FixedMetrics(), load_external=False)
    return [c for c in page.display_list if isinstance(c, DrawText)]


def test_first_word_at_body_margin():
    t = texts("<p>hello</p>")[0]
    # body margin 8px, p margin-top 16px: top margin of body and p add up
    assert t.x == 8
    assert t.text == "hello"


def test_words_wrap_at_width():
    # 16px sans: each 4-char word is 32px wide, a space is 8px
    words = texts("<p>" + "abcd " * 10 + "</p>", width=8 * 2 + 100)
    ys = sorted({w.y for w in words})
    assert len(ys) > 1
    for w in words:
        assert w.x + 32 <= 8 + 100


def test_space_between_words():
    a, b = texts("<p>ab cd</p>")
    assert b.x == a.x + 16 + 8


def test_heading_is_bigger_and_bold():
    h, p = texts("<h1>T</h1><p>x</p>")
    assert h.font.size == 32 and h.font.bold
    assert p.font.size == 16 and p.y > h.y


def test_sibling_margins_collapse():
    a, b = texts('<div style="margin-bottom:30px">a</div>'
                 '<div style="margin-top:10px">b</div>')
    # line height 20px + collapsed gap 30px
    assert b.y - a.y == 20 + 30


def test_padding_and_background():
    page = render_html('<div style="padding:10px;background:#ff0000">x</div>',
                       None, 800, FixedMetrics(), load_external=False)
    rect = next(c for c in page.display_list if isinstance(c, DrawRect))
    text = next(c for c in page.display_list if isinstance(c, DrawText))
    assert rect.color == "#ff0000"
    assert text.x == rect.x1 + 10
    assert rect.y2 - rect.y1 == 20 + 20


def test_center_and_max_width():
    t = texts('<div style="max-width:200px;margin:0 auto">x</div>')[0]
    assert t.x == 8 + (784 - 200) / 2


def test_text_align_center():
    t = texts('<p style="text-align:center">ab</p>', width=216)[0]
    assert t.x == 8 + (200 - 16) / 2


def test_br_and_display_none():
    words = texts("a<br>b<span style='display:none'>hidden</span>")
    assert [w.text for w in words] == ["a", "b"]
    assert words[1].y > words[0].y


def test_link_href_and_list_bullet():
    words = texts("<ul><li><a href='/x'>go</a></li></ul>")
    bullet, link = words
    assert bullet.text == "•" and bullet.x < link.x
    assert link.href == "/x" and link.x == 8 + 40


def test_ordered_list_numbers():
    words = texts("<ol><li>a<li>b</ol>")
    assert [w.text for w in words] == ["1.", "a", "2.", "b"]


def test_pre_keeps_lines():
    words = texts("<pre>a  b\nc</pre>")
    assert [w.text for w in words] == ["a  b", "c"]
    assert words[0].font.family == "monospace"
