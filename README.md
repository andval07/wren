# wren

A toy web browser in Python, built from scratch with only the standard
library. It downloads a page over its own HTTP client, parses the HTML and
CSS, lays out the boxes and draws them in a tkinter window.

```
URL -> net -> html -> css -> layout -> display list -> tkinter / PNG / text
```

- about 1,750 lines of Python, plus a 28-line default stylesheet
- no dependencies: sockets, `ssl`, `zlib` and `tkinter` only
- 84 pytest tests, none of them use the internet

```bash
python -m wren https://example.com
python -m wren --dump https://example.com
python -m wren --png page.png https://example.com
```

`--dump` prints the display list as text and `--png` writes a wireframe
image, where every word is a bar of its measured width.

## How it works

| Stage | File | What it does |
|---|---|---|
| Network | `net.py` | HTTP/1.1 over a raw socket, TLS with `ssl`, up to 5 redirects, chunked bodies, gzip and deflate, charset from `Content-Type`; also `file://` and `data:` URLs |
| HTML | `html.py` | a tolerant tokenizer and a tree builder: implicit `html`/`head`/`body`, `<p>` and `<li>` close themselves, void tags, raw text in `script` and `style`, named and numeric entities |
| CSS | `css.py` | tag, class and id selectors, descendant and child combinators, specificity, cascade, inheritance, inline `style`, shorthands for `margin`, `padding`, `background` and `font`, units px/em/rem/pt/% |
| Layout | `layout.py` | block and inline boxes, greedy word wrap, font size, weight and style, margins and padding, `width`, `max-width`, `margin: auto` centering, `text-align`, list markers, `<pre>` |
| Paint | `layout.py` | a display list of three commands: text, rectangle, line |
| Window | `gui.py` | address bar, back button, scroll with wheel and keys, clickable links, only visible commands are drawn |

Adjacent sibling margins collapse; parent and child margins do not.
A run of inline nodes next to block siblings is wrapped in an anonymous block.

Font metrics are pluggable. The window measures text with real tkinter
fonts. Tests use `FixedMetrics`, where every character has the same width,
so positions are exact and do not change between machines.

## Tests

| File | Tests | What it checks |
|---|---|---|
| `test_html.py` | 15 | tree shape, implicit tags, auto-closing, attributes, entities, raw text |
| `test_css.py` | 34 | parsing, specificity, cascade order, inheritance, units, colors |
| `test_layout.py` | 12 | x and y of words, wrapping, margin collapse, padding, centering, lists |
| `test_net.py` | 21 | a local `http.server` in a thread: gzip, chunked, redirects, redirect loop, 404, charset; `data:`, `file:` and URL resolution |
| `test_golden.py` | 2 | whole pages rendered to a text display list and compared line by line with a saved file |

```bash
python -m pytest
```

All 84 pass in about 3 s.

## Numbers

Measured on my laptop (Windows 11, Python 3.12). Times include the network.

| Page | Load + layout, headless | In the window | Display list | Page height |
|---|---|---|---|---|
| example.com | 0.26 s | 0.36 s | 25 commands | 564 px |
| en.wikipedia.org/wiki/Wren | 1.5 s | 3.4 s | 5,735 commands | 13,196 px |

An 83 KB local page (the basic test page repeated 200 times) is parsed,
styled and laid out in 0.52 s.

On Wikipedia the article text is readable, but the navigation menus are drawn
first, because Wikipedia hides them with CSS that wren does not support.

## Not implemented

- JavaScript
- images (the `alt` text is shown as `[alt]`)
- floats, flexbox, grid, tables (cells are laid out as plain blocks)
- pseudo-classes, attribute selectors, `+` and `~` combinators, `@media`
- `vh`/`vw` units, `calc()`, CSS variables, `light-dark()`
- borders, `position`, `z-index`
- parent/child margin collapsing
- the HTML adoption agency algorithm: in `<b>a <i>b</b> c`, `c` is not italic
- forms and input fields
- cookies, caching, keep-alive connections
- real glyphs in the PNG output (it is a wireframe)
