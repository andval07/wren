"""Layout engine: turns a styled DOM into boxes with x, y, width, height."""

from typing import NamedTuple

from .css import length_px, parse_color
from .html import Element, Text

LINE_HEIGHT = 1.25
BULLET_GAP = 8


class Font(NamedTuple):
    family: str  # "sans-serif", "serif" or "monospace"
    size: float
    bold: bool
    italic: bool


class FixedMetrics:
    """Font metrics that do not need a window. Every character in a font has
    the same width, so layout in tests is exact and the same on every OS."""

    def measure(self, text, font):
        per_char = 0.6 if font.family == "monospace" else 0.5
        if font.bold:
            per_char += 0.05
        return round(len(text) * font.size * per_char, 2)

    def ascent(self, font):
        return round(font.size * 0.8, 2)

    def descent(self, font):
        return round(font.size * 0.2, 2)


def font_of(node):
    family = node.style["font-family"].lower()
    if "mono" in family or "courier" in family:
        family = "monospace"
    elif "serif" in family and "sans" not in family:
        family = "serif"
    else:
        family = "sans-serif"
    weight = node.style["font-weight"]
    bold = weight in ("bold", "bolder") or (weight.isdigit() and int(weight) >= 600)
    italic = node.style["font-style"] in ("italic", "oblique")
    return Font(family, float(node.style["font-size"][:-2]), bold, italic)


def display(node):
    if isinstance(node, Text):
        return "inline"
    return node.style.get("display", "inline").strip().lower()


# ---------------------------------------------------------------- boxes

class DocumentLayout:
    def __init__(self, node, width, metrics):
        self.node = node
        self.width = width
        self.metrics = metrics
        self.x = self.y = 0.0
        self.children = []
        self.height = 0.0

    def layout(self):
        child = BlockLayout([self.node], self, None, self.metrics)
        self.children = [child]
        child.layout()
        self.height = child.margin_box_bottom()


class BlockLayout:
    """A block box. `nodes` is one element, or a run of inline siblings
    wrapped in an anonymous block."""

    def __init__(self, nodes, parent, previous, metrics):
        self.nodes = nodes
        self.node = nodes[0]
        self.anonymous = len(nodes) > 1 or display(nodes[0]) != "block"
        self.parent = parent
        self.previous = previous
        self.metrics = metrics
        self.children = []
        self.x = self.y = self.width = self.height = 0.0
        self.margin = self.padding = (0.0, 0.0, 0.0, 0.0)

    # box edges ------------------------------------------------------
    def margin_box_bottom(self):
        return self.y + self.height + self.padding[2] + self.margin[2]

    def _sides(self, prop):
        if self.anonymous:
            return (0.0, 0.0, 0.0, 0.0)
        font_size = float(self.node.style["font-size"][:-2])
        return tuple(
            length_px(self.node.style.get(f"{prop}-{side}", "0"),
                      font_size, self.parent.width)
            for side in ("top", "right", "bottom", "left")
        )

    def layout(self):
        self.margin = self._sides("margin")
        self.padding = self._sides("padding")
        mt, mr, _, ml = self.margin
        pt, pr, _, pl = self.padding

        available = self.parent.width - ml - mr - pl - pr
        self.width = available
        if not self.anonymous:
            font_size = float(self.node.style["font-size"][:-2])
            for prop in ("width", "max-width"):
                wanted = length_px(self.node.style.get(prop, "auto"),
                                   font_size, self.parent.width)
                if wanted > 0:
                    self.width = min(self.width, wanted)
        self.x = self.parent.x + ml + pl
        if self.width < available and self._auto_margins():
            self.x += (available - self.width) / 2

        if self.previous is not None:
            # adjacent sibling margins collapse to the larger one
            prev_bottom = self.previous.y + self.previous.height \
                + self.previous.padding[2]
            gap = max(self.previous.margin[2], mt)
            self.y = prev_bottom + gap + pt
        else:
            self.y = self.parent.y + mt + pt

        if self._has_block_children():
            self._layout_blocks()
            self.height = 0.0
            if self.children:
                self.height = self.children[-1].margin_box_bottom() - self.y
        else:
            inline = InlineLayout(self.nodes, self, self.metrics)
            inline.layout()
            self.children = inline.lines
            self.height = inline.height

        if not self.anonymous and "height" in self.node.style:
            font_size = float(self.node.style["font-size"][:-2])
            fixed = length_px(self.node.style["height"], font_size)
            if fixed > 0:
                self.height = fixed

    def _auto_margins(self):
        style = self.node.style
        return style.get("margin-left") == "auto" \
            and style.get("margin-right") == "auto"

    def _has_block_children(self):
        if self.anonymous:
            return False
        return any(
            isinstance(c, Element) and display(c) == "block"
            for c in self.node.children
        )

    def _layout_blocks(self):
        previous = None
        run = []

        def flush_run():
            nonlocal previous
            if not any(_visible_inline(n) for n in run):
                run.clear()
                return
            box = BlockLayout(list(run), self, previous, self.metrics)
            self.children.append(box)
            box.layout()
            previous = box
            run.clear()

        for child in self.node.children:
            kind = display(child)
            if kind == "none":
                continue
            if kind == "block":
                flush_run()
                box = BlockLayout([child], self, previous, self.metrics)
                self.children.append(box)
                box.layout()
                previous = box
            else:
                run.append(child)
        flush_run()

    def paint(self, out):
        if self.anonymous:
            for child in self.children:
                child.paint(out)
            return
        bg = parse_color(self.node.style.get("background-color", ""))
        if bg is not None:
            pt, pr, pb, pl = self.padding
            out.append(DrawRect(
                self.x - pl, self.y - pt,
                self.x + self.width + pr, self.y + self.height + pb, bg))
        if self.node.tag == "li":
            self._paint_marker(out)
        for child in self.children:
            child.paint(out)

    def _paint_marker(self, out):
        first_line = _first_line(self)
        if first_line is None:
            return
        font = font_of(self.node)
        color = parse_color(self.node.style["color"]) or "#000000"
        kind = self.node.style.get("list-style-type", "disc")
        if kind == "none":
            return
        if self.node.parent is not None and self.node.parent.tag == "ol":
            siblings = [c for c in self.node.parent.children
                        if isinstance(c, Element) and c.tag == "li"]
            marker = f"{siblings.index(self.node) + 1}."
        else:
            marker = "•"
        width = self.metrics.measure(marker, font)
        out.append(DrawText(self.x - width - BULLET_GAP,
                            first_line.baseline - self.metrics.ascent(font),
                            marker, font, color, None))


def _first_line(box):
    for child in box.children:
        if isinstance(child, LineLayout):
            return child
        found = _first_line(child)
        if found is not None:
            return found
    return None


def _visible_inline(node):
    if isinstance(node, Text):
        return bool(node.text.strip()) or node.style["white-space"] == "pre"
    if display(node) == "none":
        return False
    if node.tag in ("br", "img"):
        return True
    return any(_visible_inline(c) for c in node.children)


# ---------------------------------------------------------------- inline

class Word(NamedTuple):
    x: float
    text: str
    font: object
    color: str
    href: object
    underline: bool
    width: float


class LineLayout:
    def __init__(self, x, y, words, baseline, height):
        self.x = x
        self.y = y
        self.words = words
        self.baseline = baseline
        self.height = height

    def paint(self, out):
        for w in self.words:
            top = self.baseline - w.ascent_px
            out.append(DrawText(w.x, top, w.text, w.font, w.color, w.href))
            if w.underline:
                y = self.baseline + 1
                out.append(DrawLine(w.x, y, w.x + w.width, y, w.color))


class PlacedWord:
    def __init__(self, word, ascent_px):
        self.x = word.x
        self.text = word.text
        self.font = word.font
        self.color = word.color
        self.href = word.href
        self.underline = word.underline
        self.width = word.width
        self.ascent_px = ascent_px


class InlineLayout:
    """Breaks a run of inline nodes into lines (greedy word wrap)."""

    def __init__(self, nodes, block, metrics):
        self.nodes = nodes
        self.block = block
        self.metrics = metrics
        self.lines = []
        self.height = 0.0
        self.cursor_x = 0.0
        self.line = []
        self.cursor_x_space = False
        self.align = "left"

    def layout(self):
        self.y = self.block.y
        style_source = self.block.node if not self.block.anonymous \
            else self.nodes[0].parent
        if style_source is not None:
            self.align = style_source.style.get("text-align", "left")
        for node in self.nodes:
            self._recurse(node, None)
        self._flush()
        self.height = self.y - self.block.y

    def _recurse(self, node, href):
        if isinstance(node, Text):
            self._text(node, href)
            return
        if display(node) == "none":
            return
        if node.tag == "a" and "href" in node.attributes:
            href = node.attributes["href"]
        if node.tag == "br":
            self._flush(force=True, font=font_of(node))
            return
        if node.tag == "img":
            alt = node.attributes.get("alt", "").strip()
            if alt:
                self._word(f"[{alt}]", node, href)
            return
        if display(node) == "block":
            # a block inside inline content: put it on its own line
            self._flush()
        for child in node.children:
            self._recurse(child, href)
        if display(node) == "block":
            self._flush()

    def _text(self, node, href):
        if node.style["white-space"] == "pre":
            lines = node.text.split("\n")
            for i, line in enumerate(lines):
                if i > 0:
                    self._flush(force=True, font=font_of(node))
                if line:
                    self._word(line.expandtabs(8), node, href, pre=True)
            return
        text = node.text
        words = text.split()
        if not words:
            if text:
                self._space(node)
            return
        if text[0].isspace():
            self._space(node)
        for i, word in enumerate(words):
            if i > 0:
                self._space(node)
            self._word(word, node, href)
        if text[-1].isspace():
            self._space(node)

    def _space(self, node):
        if self.line:
            self.cursor_x_space = True

    def _word(self, text, node, href, pre=False):
        font = font_of(node)
        width = self.metrics.measure(text, font)
        space = 0.0
        if self.line and self.cursor_x_space:
            space = self.metrics.measure(" ", font)
        if self.line and self.cursor_x + space + width > self.block.width \
                and not pre:
            self._flush()
            space = 0.0
        color = parse_color(node.style["color"]) or "#000000"
        underline = "underline" in node.style.get("text-decoration", "")
        x = self.cursor_x + space
        self.line.append(Word(x, text, font, color, href, underline, width))
        self.cursor_x = x + width
        self.cursor_x_space = False

    def _flush(self, force=False, font=None):
        if not self.line:
            if force and font is not None:
                # an empty line still takes space (e.g. <br><br>)
                self.y += font.size * LINE_HEIGHT
            self.cursor_x = 0.0
            self.cursor_x_space = False
            return
        max_ascent = max(self.metrics.ascent(w.font) for w in self.line)
        max_descent = max(self.metrics.descent(w.font) for w in self.line)
        max_size = max(w.font.size for w in self.line)
        line_height = max(max_size * LINE_HEIGHT, max_ascent + max_descent)
        extra = (line_height - max_ascent - max_descent) / 2
        baseline = self.y + extra + max_ascent
        shift = 0.0
        used = self.line[-1].x + self.line[-1].width
        if self.align == "center":
            shift = max(0.0, (self.block.width - used) / 2)
        elif self.align == "right":
            shift = max(0.0, self.block.width - used)
        placed = []
        for w in self.line:
            moved = w._replace(x=self.block.x + w.x + shift)
            placed.append(PlacedWord(moved, self.metrics.ascent(w.font)))
        self.lines.append(LineLayout(self.block.x, self.y, placed, baseline,
                                     line_height))
        self.y += line_height
        self.line = []
        self.cursor_x = 0.0
        self.cursor_x_space = False


# ---------------------------------------------------------------- display list

class DrawText(NamedTuple):
    x: float
    y: float  # top of the text
    text: str
    font: Font
    color: str
    href: object


class DrawRect(NamedTuple):
    x1: float
    y1: float
    x2: float
    y2: float
    color: str


class DrawLine(NamedTuple):
    x1: float
    y1: float
    x2: float
    y2: float
    color: str


def build_display_list(document):
    out = []
    for child in document.children:
        child.paint(out)
    return out


def describe(cmd):
    """One stable line of text per command; used by golden tests."""
    if isinstance(cmd, DrawText):
        f = cmd.font
        style = ("b" if f.bold else "") + ("i" if f.italic else "")
        link = f" -> {cmd.href}" if cmd.href else ""
        return (f"text {cmd.x:g},{cmd.y:g} {f.family} {f.size:g}{style} "
                f"{cmd.color} {cmd.text!r}{link}")
    if isinstance(cmd, DrawRect):
        return (f"rect {cmd.x1:g},{cmd.y1:g} {cmd.x2:g},{cmd.y2:g} "
                f"{cmd.color}")
    return f"line {cmd.x1:g},{cmd.y1:g} {cmd.x2:g},{cmd.y2:g} {cmd.color}"
