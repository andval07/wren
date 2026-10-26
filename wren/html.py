"""Tolerant HTML tokenizer and tree builder."""

from html.entities import html5 as ENTITY_TABLE  # only the name -> char table

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}
HEAD_TAGS = {"base", "basefont", "bgsound", "noscript", "link", "meta",
             "title", "style", "script"}
RAW_TEXT_TAGS = {"script", "style", "textarea", "title"}
# opening one of these closes an open element of the same group
AUTO_CLOSE = {
    "p": {"p"}, "li": {"li"}, "dt": {"dt", "dd"}, "dd": {"dt", "dd"},
    "tr": {"tr", "td", "th"}, "td": {"td", "th"}, "th": {"td", "th"},
    "option": {"option"},
}
# a <p> is closed by any of these block starts
CLOSES_P = {"address", "article", "aside", "blockquote", "div", "dl",
            "fieldset", "footer", "form", "h1", "h2", "h3", "h4", "h5",
            "h6", "header", "hr", "main", "nav", "ol", "p", "pre",
            "section", "table", "ul"}


class Text:
    def __init__(self, text, parent):
        self.text = text
        self.parent = parent
        self.children = []
        self.style = {}

    def __repr__(self):
        return repr(self.text)


class Element:
    def __init__(self, tag, attributes, parent):
        self.tag = tag
        self.attributes = attributes
        self.parent = parent
        self.children = []
        self.style = {}

    def __repr__(self):
        return f"<{self.tag}>"


def decode_entities(text):
    if "&" not in text:
        return text
    out = []
    i = 0
    while i < len(text):
        c = text[i]
        if c != "&":
            out.append(c)
            i += 1
            continue
        end = text.find(";", i, i + 40)
        name = text[i + 1:end] if end != -1 else ""
        if name.startswith("#"):
            try:
                if name[1:2] in ("x", "X"):
                    code = int(name[2:], 16)
                else:
                    code = int(name[1:])
                out.append(chr(code) if 0 < code < 0x110000 else "�")
                i = end + 1
                continue
            except ValueError:
                pass
        elif name and name + ";" in ENTITY_TABLE:
            out.append(ENTITY_TABLE[name + ";"])
            i = end + 1
            continue
        out.append("&")
        i += 1
    return "".join(out)


def tokenize(source):
    """Yield ("text", str), ("start", tag, attrs, self_closing),
    ("end", tag). Comments and doctypes are dropped."""
    i = 0
    n = len(source)
    while i < n:
        lt = source.find("<", i)
        if lt == -1:
            yield ("text", decode_entities(source[i:]))
            return
        if lt > i:
            yield ("text", decode_entities(source[i:lt]))
        i = lt
        if source.startswith("<!--", i):
            end = source.find("-->", i + 4)
            i = n if end == -1 else end + 3
            continue
        if source.startswith("<!", i) or source.startswith("<?", i):
            end = source.find(">", i)
            i = n if end == -1 else end + 1
            continue
        nxt = source[i + 1:i + 2]
        if not (nxt.isalpha() or nxt == "/"):
            yield ("text", "<")
            i += 1
            continue
        tag_token, i = _read_tag(source, i + 1)
        yield tag_token
        if tag_token[0] == "start" and tag_token[1] in RAW_TEXT_TAGS:
            close = source.lower().find("</" + tag_token[1], i)
            close = n if close == -1 else close
            raw = source[i:close]
            if raw:
                if tag_token[1] in ("title", "textarea"):
                    raw = decode_entities(raw)
                yield ("text", raw)
            i = close


def _read_tag(source, i):
    n = len(source)
    closing = source[i] == "/"
    if closing:
        i += 1
    start = i
    while i < n and not source[i].isspace() and source[i] not in "/>":
        i += 1
    tag = source[start:i].lower()
    attrs = {}
    self_closing = False
    while i < n:
        c = source[i]
        if c == ">":
            i += 1
            break
        if c.isspace():
            i += 1
            continue
        if c == "/":
            self_closing = True
            i += 1
            continue
        start = i
        while i < n and not source[i].isspace() and source[i] not in "=/>":
            i += 1
        name = source[start:i].lower()
        while i < n and source[i].isspace():
            i += 1
        value = ""
        if i < n and source[i] == "=":
            i += 1
            while i < n and source[i].isspace():
                i += 1
            if i < n and source[i] in "\"'":
                quote = source[i]
                end = source.find(quote, i + 1)
                end = n if end == -1 else end
                value = source[i + 1:end]
                i = end + 1
            else:
                start = i
                while i < n and not source[i].isspace() and source[i] != ">":
                    i += 1
                value = source[start:i]
        if name and name not in attrs:
            attrs[name] = decode_entities(value)
    if closing:
        return ("end", tag), i
    return ("start", tag, attrs, self_closing), i


class Parser:
    """Builds a tree with an implicit html/head/body skeleton."""

    def __init__(self, source):
        self.source = source
        self.stack = []

    def parse(self):
        for token in tokenize(self.source):
            if token[0] == "text":
                self._text(token[1])
            elif token[0] == "start":
                # like real browsers, <div/> is just <div>: the slash is ignored
                self._start(token[1], token[2])
            else:
                self._end(token[1])
        self._implicit(None)
        while len(self.stack) > 1:
            self.stack.pop()
        return self.stack.pop()

    def _implicit(self, tag):
        """Insert html/head/body when the page leaves them out."""
        while True:
            open_tags = [node.tag for node in self.stack]
            if not open_tags and tag != "html":
                self._push("html", {})
            elif open_tags == ["html"] and tag not in ("head", "body", "/html"):
                if tag in HEAD_TAGS:
                    self._push("head", {})
                else:
                    self._push("body", {})
            elif open_tags == ["html", "head"] and \
                    tag not in ["/head"] + list(HEAD_TAGS):
                self.stack.pop()
            else:
                break

    def _push(self, tag, attrs):
        parent = self.stack[-1] if self.stack else None
        node = Element(tag, attrs, parent)
        if parent is not None:
            parent.children.append(node)
        self.stack.append(node)
        return node

    def _text(self, text):
        if text.isspace() and len(self.stack) < 2:
            return
        if text.isspace() and [n.tag for n in self.stack] == ["html", "head"]:
            return
        self._implicit(None)
        parent = self.stack[-1]
        if parent.children and isinstance(parent.children[-1], Text):
            parent.children[-1].text += text
        else:
            parent.children.append(Text(text, parent))

    def _start(self, tag, attrs):
        if tag in ("html", "head", "body"):
            existing = [n for n in self.stack if n.tag == tag]
            if existing:
                for k, v in attrs.items():
                    existing[0].attributes.setdefault(k, v)
                return
        self._implicit(tag)
        if tag in CLOSES_P:
            self._close_in_scope("p")
        if tag in AUTO_CLOSE:
            for i in range(len(self.stack) - 1, 0, -1):
                open_tag = self.stack[i].tag
                if open_tag in AUTO_CLOSE[tag]:
                    del self.stack[i:]
                    break
                if open_tag in ("ul", "ol", "dl", "table", "select", "div"):
                    break
        self._push(tag, attrs)
        if tag in VOID_TAGS:
            self.stack.pop()

    def _close_in_scope(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return
            if self.stack[i].tag in ("div", "td", "th", "li", "body"):
                return

    def _end(self, tag):
        if tag in ("html", "body"):
            return
        if tag == "p" and not any(n.tag == "p" for n in self.stack):
            self._start("p", {})  # browsers turn a stray </p> into <p></p>
        if tag == "br":
            self._start("br", {})
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return
        # unmatched end tag: ignore it


def parse(source):
    return Parser(source).parse()


def tree_to_lines(node, indent=0):
    """Debug dump of the tree, one node per line."""
    if isinstance(node, Text):
        lines = [" " * indent + repr(node.text)]
    else:
        lines = [" " * indent + f"<{node.tag}>"]
    for child in node.children:
        lines.extend(tree_to_lines(child, indent + 2))
    return lines
