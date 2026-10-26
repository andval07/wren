"""Command line entry point.

    python -m wren URL                 open a window
    python -m wren --dump URL          print the display list
    python -m wren --png out.png URL   write a wireframe PNG
"""

import argparse
import sys

from .engine import load
from .headless import to_text, write_png
from .layout import FixedMetrics
from .net import NetError

HEADLESS_WIDTH = 800
MAX_PNG_HEIGHT = 20000


def main(argv=None):
    ap = argparse.ArgumentParser(prog="wren")
    ap.add_argument("url", nargs="?", default="https://example.com/")
    ap.add_argument("--dump", action="store_true",
                    help="print the display list instead of opening a window")
    ap.add_argument("--png", metavar="FILE", help="write a wireframe PNG")
    args = ap.parse_args(argv)

    if not (args.dump or args.png):
        from .gui import Browser  # import tkinter only when needed
        Browser().run(args.url)
        return 0

    try:
        page = load(args.url, HEADLESS_WIDTH, FixedMetrics())
    except NetError as e:
        print(f"wren: {e}", file=sys.stderr)
        return 1
    if args.dump:
        sys.stdout.reconfigure(encoding="utf-8")
        print(to_text(page.display_list))
    if args.png:
        height = max(1, min(int(page.height) + 1, MAX_PNG_HEIGHT))
        write_png(args.png, page.display_list, HEADLESS_WIDTH, height)
    return 0


if __name__ == "__main__":
    sys.exit(main())
