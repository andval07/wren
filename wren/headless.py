"""Rendering without a window: display list as text, or a PNG wireframe.

The PNG has no real glyphs (that would need a font rasterizer). Each word
is drawn as a filled bar of its measured width, which is enough to check
layout by eye."""

import struct
import zlib

from .layout import DrawLine, DrawRect, DrawText, FixedMetrics, describe


def to_text(display_list):
    return "\n".join(describe(cmd) for cmd in display_list)


def _hex_rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def rasterize(display_list, width, height):
    pixels = bytearray(b"\xff" * (width * height * 3))

    def fill(x1, y1, x2, y2, rgb):
        x1, x2 = max(0, int(x1)), min(width, int(round(x2)))
        y1, y2 = max(0, int(y1)), min(height, int(round(y2)))
        row = bytes(rgb) * max(0, x2 - x1)
        for y in range(y1, y2):
            start = (y * width + x1) * 3
            pixels[start:start + len(row)] = row

    for cmd in display_list:
        if isinstance(cmd, DrawRect):
            fill(cmd.x1, cmd.y1, cmd.x2, cmd.y2, _hex_rgb(cmd.color))
        elif isinstance(cmd, DrawLine):
            fill(cmd.x1, cmd.y1, cmd.x2, cmd.y1 + 1, _hex_rgb(cmd.color))
        elif isinstance(cmd, DrawText):
            # a bar from x-height to baseline stands in for the glyphs
            size = cmd.font.size
            top = cmd.y + size * 0.35
            right = cmd.x + FixedMetrics().measure(cmd.text, cmd.font)
            fill(cmd.x, top, right, cmd.y + size * 0.8,
                 _hex_rgb(cmd.color))
    return pixels


def write_png(path, display_list, width, height):
    pixels = rasterize(display_list, width, height)
    raw = bytearray()
    stride = width * 3
    for y in range(height):
        raw.append(0)  # filter type: none
        raw.extend(pixels[y * stride:(y + 1) * stride])

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + \
            struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", header))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))
