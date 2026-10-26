"""Golden tests: whole pages rendered to a text display list and compared
with files in tests/golden/. Run with WREN_UPDATE_GOLDEN=1 to rewrite them."""

import os
from pathlib import Path

import pytest

from wren.engine import render_html
from wren.headless import to_text
from wren.layout import FixedMetrics

HERE = Path(__file__).parent
PAGES = sorted((HERE / "pages").glob("*.html"))


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.stem)
def test_golden(page):
    source = page.read_text(encoding="utf-8")
    result = render_html(source, None, 800, FixedMetrics(), load_external=False)
    actual = to_text(result.display_list) + "\n"
    golden = HERE / "golden" / (page.stem + ".txt")
    if os.environ.get("WREN_UPDATE_GOLDEN") or not golden.exists():
        golden.parent.mkdir(exist_ok=True)
        golden.write_text(actual, encoding="utf-8")
    assert actual == golden.read_text(encoding="utf-8")
