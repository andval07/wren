"""Glue: URL -> bytes -> DOM -> styled DOM -> layout -> display list."""

from . import css
from .html import Element, Text, parse
from .layout import DocumentLayout, build_display_list
from .net import NetError, URL, fetch


class Page:
    def __init__(self, url, title, dom, document, display_list):
        self.url = url
        self.title = title
        self.dom = dom
        self.document = document
        self.display_list = display_list
        self.height = document.height


def collect_stylesheets(dom, base_url, load_external=True):
    """Return author rules from <style> and <link rel=stylesheet>, in order."""
    rules = []
    for node in css.iter_tree(dom):
        if not isinstance(node, Element):
            continue
        if node.tag == "style":
            text = "".join(c.text for c in node.children if isinstance(c, Text))
            rules.extend(css.parse(text))
        elif node.tag == "link" and load_external \
                and "stylesheet" in node.attributes.get("rel", "").lower() \
                and "href" in node.attributes:
            try:
                sheet = fetch(base_url.resolve(node.attributes["href"]))
            except (NetError, ValueError):
                continue  # a broken stylesheet must not break the page
            rules.extend(css.parse(sheet.text()))
    return rules


def find_title(dom):
    for node in css.iter_tree(dom):
        if isinstance(node, Element) and node.tag == "title":
            return "".join(c.text for c in node.children).strip()
    return ""


def render_html(source, url, width, metrics, load_external=True):
    dom = parse(source)
    author = collect_stylesheets(dom, url, load_external)
    rules = css.sort_rules(css.default_rules(), author)
    css.style(dom, rules)
    document = DocumentLayout(dom, width, metrics)
    document.layout()
    return Page(url, find_title(dom), dom, document,
                build_display_list(document))


def load(url, width, metrics):
    if isinstance(url, str):
        url = URL(url)
    response = fetch(url)
    return render_html(response.text(), response.url, width, metrics)
