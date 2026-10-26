"""CSS parser, selector matching, cascade and inheritance."""

import os

from .html import Element, Text

INHERITED = {
    "color": "black",
    "font-size": "16px",
    "font-weight": "normal",
    "font-style": "normal",
    "font-family": "sans-serif",
    "text-align": "left",
    "white-space": "normal",
    "text-decoration": "none",
    "list-style-type": "disc",
}
BOX_SIDES = ("top", "right", "bottom", "left")
FONT_KEYWORDS = {
    "xx-small": 9, "x-small": 10, "small": 13, "medium": 16,
    "large": 18, "x-large": 24, "xx-large": 32,
}


# ---------------------------------------------------------------- selectors

class TagSelector:
    """A compound selector like `a`, `.note`, `#top` or `p.note.big`."""

    def __init__(self, tag, classes, ident):
        self.tag = tag
        self.classes = classes
        self.ident = ident
        self.specificity = (
            (100 if ident else 0) + 10 * len(classes) + (1 if tag else 0)
        )

    def matches(self, node):
        if not isinstance(node, Element):
            return False
        if self.tag and node.tag != self.tag:
            return False
        if self.ident and node.attributes.get("id") != self.ident:
            return False
        if self.classes:
            have = node.attributes.get("class", "").split()
            if not all(c in have for c in self.classes):
                return False
        return True


class DescendantSelector:
    def __init__(self, ancestor, descendant):
        self.ancestor = ancestor
        self.descendant = descendant
        self.specificity = ancestor.specificity + descendant.specificity

    def matches(self, node):
        if not self.descendant.matches(node):
            return False
        node = node.parent
        while node is not None:
            if self.ancestor.matches(node):
                return True
            node = node.parent
        return False


class ChildSelector:
    def __init__(self, parent, child):
        self.parent = parent
        self.child = child
        self.specificity = parent.specificity + child.specificity

    def matches(self, node):
        return self.child.matches(node) and node.parent is not None \
            and self.parent.matches(node.parent)


# ---------------------------------------------------------------- parser

class CSSParser:
    def __init__(self, text):
        self.s = _strip_comments(text)
        self.i = 0

    def whitespace(self):
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def word(self):
        start = self.i
        while self.i < len(self.s) and (
            self.s[self.i].isalnum() or self.s[self.i] in "#-.%_*!"
        ):
            self.i += 1
        if self.i == start:
            raise ValueError(f"parse error at {self.i}")
        return self.s[start:self.i]

    def literal(self, ch):
        if self.i >= len(self.s) or self.s[self.i] != ch:
            raise ValueError(f"expected {ch!r} at {self.i}")
        self.i += 1

    def skip_until(self, chars):
        while self.i < len(self.s):
            if self.s[self.i] in chars:
                return self.s[self.i]
            self.i += 1
        return None

    def body(self):
        """Parse `prop: value; ...` up to a `}` or the end."""
        pairs = {}
        while self.i < len(self.s) and self.s[self.i] != "}":
            start = self.i
            stop = self.skip_until(";}")
            decl = self.s[start:self.i]
            if stop == ";":
                self.i += 1
            prop, sep, value = decl.partition(":")
            if not sep:
                continue
            prop = prop.strip().lower()
            value = value.strip()
            important = value.lower().endswith("!important")
            if important:
                value = value[: -len("!important")].strip()
            if prop and value:
                for p, v in expand_shorthand(prop, value):
                    pairs[p] = v
        return pairs

    def selector(self):
        """Parse a selector list. Unsupported selectors raise ValueError."""
        start = self.i
        self.skip_until("{")
        text = self.s[start:self.i].strip()
        return [_parse_one_selector(part) for part in text.split(",")]

    def parse(self):
        rules = []
        while True:
            self.whitespace()
            if self.i >= len(self.s):
                return rules
            if self.s[self.i] == "@":
                self._skip_at_rule()
                continue
            start = self.i
            try:
                selectors = self.selector()
            except ValueError:
                selectors = None
            if self.i >= len(self.s):
                return rules
            self.i += 1  # the "{"
            decls = self.body()
            if self.i < len(self.s):
                self.i += 1  # the "}"
            if selectors is None or self.i == start:
                continue
            for sel in selectors:
                rules.append((sel, decls))

    def _skip_at_rule(self):
        stop = self.skip_until(";{")
        self.i += 1
        if stop == "{":
            depth = 1
            while self.i < len(self.s) and depth:
                if self.s[self.i] == "{":
                    depth += 1
                elif self.s[self.i] == "}":
                    depth -= 1
                self.i += 1


def _strip_comments(text):
    out = []
    i = 0
    while True:
        start = text.find("/*", i)
        if start == -1:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:start])
        end = text.find("*/", start + 2)
        if end == -1:
            return "".join(out)
        i = end + 2


def _parse_compound(text):
    if not text or any(c in text for c in "[]:+~()"):
        raise ValueError(f"unsupported selector: {text!r}")
    tag = ""
    classes = []
    ident = None
    token = ""
    kind = "tag"
    for c in text + "\0":
        if c in ".#\0":
            if kind == "tag":
                tag = token.lower() if token != "*" else ""
            elif kind == "class":
                classes.append(token)
            else:
                ident = token
            kind = "class" if c == "." else "id"
            token = ""
        else:
            token += c
    return TagSelector(tag, classes, ident)


def _parse_one_selector(text):
    text = text.replace(">", " > ")
    parts = text.split()
    if not parts:
        raise ValueError("empty selector")
    result = _parse_compound(parts[0])
    i = 1
    while i < len(parts):
        if parts[i] == ">":
            result = ChildSelector(result, _parse_compound(parts[i + 1]))
            i += 2
        else:
            result = DescendantSelector(result, _parse_compound(parts[i]))
            i += 1
    return result


def expand_shorthand(prop, value):
    if prop in ("margin", "padding"):
        vals = value.split()
        if not 1 <= len(vals) <= 4:
            return []
        top = vals[0]
        right = vals[1] if len(vals) > 1 else top
        bottom = vals[2] if len(vals) > 2 else top
        left = vals[3] if len(vals) > 3 else right
        return [(f"{prop}-{s}", v)
                for s, v in zip(BOX_SIDES, (top, right, bottom, left))]
    if prop == "background":
        # keep only a color, if the shorthand starts with one
        first = value.split()[0]
        if parse_color(first) is not None:
            return [("background-color", first)]
        return []
    if prop == "font":
        return _expand_font(value)
    return [(prop, value)]


def _expand_font(value):
    out = []
    for part in value.split():
        if part in ("bold", "bolder") or part.isdigit():
            out.append(("font-weight", part))
        elif part == "italic":
            out.append(("font-style", "italic"))
        elif part[0].isdigit() or part in FONT_KEYWORDS:
            out.append(("font-size", part.split("/")[0]))
            break
    return out


# ---------------------------------------------------------------- values

NAMED_COLORS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000",
    "green": "#008000", "blue": "#0000ff", "yellow": "#ffff00",
    "gray": "#808080", "grey": "#808080", "silver": "#c0c0c0",
    "maroon": "#800000", "navy": "#000080", "purple": "#800080",
    "teal": "#008080", "olive": "#808000", "orange": "#ffa500",
    "lightgray": "#d3d3d3", "lightgrey": "#d3d3d3",
    "darkgray": "#a9a9a9", "whitesmoke": "#f5f5f5",
    "lightblue": "#add8e6", "lime": "#00ff00", "aqua": "#00ffff",
    "fuchsia": "#ff00ff", "transparent": None,
}


def parse_color(value):
    """Return '#rrggbb', None for transparent, or None if unknown."""
    value = value.strip().lower()
    if value in NAMED_COLORS:
        return NAMED_COLORS[value]
    if value.startswith("#"):
        h = value[1:]
        if len(h) in (3, 4) and _is_hex(h):
            return "#" + "".join(c * 2 for c in h[:3])
        if len(h) in (6, 8) and _is_hex(h):
            return "#" + h[:6]
        return None
    if value.startswith(("rgb(", "rgba(")) and value.endswith(")"):
        inner = value[value.index("(") + 1:-1].replace("/", ",")
        parts = [p.strip() for p in inner.replace(",", " ").split()]
        if len(parts) < 3:
            return None
        if len(parts) == 4 and parts[3] in ("0", "0%"):
            return None
        try:
            rgb = [_channel(p) for p in parts[:3]]
        except ValueError:
            return None
        return "#" + "".join(f"{c:02x}" for c in rgb)
    return None


def _is_hex(text):
    return all(c in "0123456789abcdef" for c in text)


def _channel(text):
    if text.endswith("%"):
        return max(0, min(255, round(float(text[:-1]) * 2.55)))
    return max(0, min(255, round(float(text))))


def length_px(value, font_size, percent_of=0.0):
    """Convert a CSS length to pixels. Unknown units count as 0."""
    value = value.strip().lower()
    if value in ("0", "auto", ""):
        return 0.0
    try:
        if value.endswith("px"):
            return float(value[:-2])
        if value.endswith("rem"):
            return float(value[:-3]) * 16
        if value.endswith("em"):
            return float(value[:-2]) * font_size
        if value.endswith("pt"):
            return float(value[:-2]) * 4 / 3
        if value.endswith("%"):
            return float(value[:-1]) / 100 * percent_of
        return float(value)
    except ValueError:
        return 0.0


def font_size_px(value, parent_px):
    value = value.strip().lower()
    if value in FONT_KEYWORDS:
        return float(FONT_KEYWORDS[value])
    if value == "smaller":
        return parent_px / 1.2
    if value == "larger":
        return parent_px * 1.2
    if value.endswith("%"):
        return length_px(value, parent_px, parent_px)
    px = length_px(value, parent_px)
    return px if px > 0 else parent_px


# ---------------------------------------------------------------- cascade

def parse(text):
    return CSSParser(text).parse()


def parse_inline(text):
    return CSSParser(text).body()


def style(node, rules):
    """Compute node.style for the whole tree. Rules must come from
    sort_rules, so later rules win."""
    node.style = {}
    for prop, default in INHERITED.items():
        if node.parent is not None:
            node.style[prop] = node.parent.style[prop]
        else:
            node.style[prop] = default
    if isinstance(node, Element):
        for selector, decls in rules:
            if selector.matches(node):
                node.style.update(decls)
        if "style" in node.attributes:
            node.style.update(parse_inline(node.attributes["style"]))
    _resolve_font_size(node)
    for child in node.children:
        style(child, rules)


def _resolve_font_size(node):
    parent_px = 16.0
    if node.parent is not None:
        parent_px = float(node.parent.style["font-size"][:-2])
    px = font_size_px(node.style["font-size"], parent_px)
    node.style["font-size"] = f"{px:g}px"


def sort_rules(browser_rules, author_rules):
    """Cascade order: browser sheet first, then the page's own rules, each
    by specificity. sorted() is stable, so ties keep source order."""
    tagged = [(0, sel, decls) for sel, decls in browser_rules]
    tagged += [(1, sel, decls) for sel, decls in author_rules]
    tagged.sort(key=lambda r: (r[0], r[1].specificity))
    return [(sel, decls) for _, sel, decls in tagged]


_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "browser.css")


def default_rules():
    with open(_DEFAULT_PATH, encoding="utf-8") as f:
        return parse(f.read())


def iter_tree(node):
    yield node
    for child in node.children:
        yield from iter_tree(child)


def is_text(node):
    return isinstance(node, Text)
