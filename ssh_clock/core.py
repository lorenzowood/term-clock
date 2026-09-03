"""Pure, side-effect-free clock rendering.

Everything here is deterministic and unit-tested. The runtime shell in
``cli.py`` supplies the current time and terminal size and paints the result.

Big digits are drawn from a **vector seven-segment model**: each segment is a
bold rectangle with small gaps at the joins (a `DSEG`-style display), and the
colon is two square dots. The shapes are rasterised at whatever size the
terminal allows, sampled at 2x vertical resolution and emitted with Unicode
half-block characters (``▀ ▄ █``). All edges are axis-aligned, so the strokes
stay crisp and bold at any size instead of turning into a coarse grid of giant
square pixels (too chunky) or thin single-character lines (too faint).
"""

from __future__ import annotations

BLOCK = "█"

# --- time formatting ---------------------------------------------------

def format_time(h: int, m: int, s: int) -> str:
    """Return ``hh:mm:ss`` (zero-padded, 24-hour)."""
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        raise ValueError(f"time out of range: {h}:{m}:{s}")
    return f"{h:02d}:{m:02d}:{s:02d}"


# --- layout decision -------------------------------------------------

TEXT_LINE_LIMIT = 7  # "less than seven lines" -> text; 7 stays text too


def choose_mode(rows: int) -> str:
    """``"art"`` when there is real headroom (>= 8 lines), else ``"text"``."""
    return "art" if rows > TEXT_LINE_LIMIT else "text"


# --- vector glyph model --------------------------------------------
#
# A digit lives in a local box DW wide x DH tall. A colon lives in a box
# COLON_W wide x DH tall. Coordinates are arbitrary units; only ratios matter.

DW = 100.0
DH = 180.0
COLON_W = 30.0
GAP = 8.0             # space between glyph boxes

_M = 6.0             # inset of the segment envelope from the box edge
_HALF = 11.0         # half of a segment's thickness
_JOIN = 4.0          # gap between a horizontal bar and the verticals it meets

_MID = DH / 2.0
_L, _R = _M, DW - _M                       # outer x of the digit envelope
_XL, _XR = _M + _HALF, DW - _M - _HALF     # centre x of the vertical bars
_YT, _YB = _M + _HALF, DH - _M - _HALF     # centre y of the top/bottom bars

# Horizontal bars run the full width; vertical bars sit strictly between the
# horizontals with a _JOIN gap, so the corners are clean (no pokey ends).
_SEGMENTS: dict[str, tuple[float, float, float, float]] = {
    "a": (_L, _YT - _HALF, _R, _YT + _HALF),
    "g": (_L, _MID - _HALF, _R, _MID + _HALF),
    "d": (_L, _YB - _HALF, _R, _YB + _HALF),
    "f": (_XL - _HALF, _YT + _HALF + _JOIN, _XL + _HALF, _MID - _HALF - _JOIN),
    "b": (_XR - _HALF, _YT + _HALF + _JOIN, _XR + _HALF, _MID - _HALF - _JOIN),
    "e": (_XL - _HALF, _MID + _HALF + _JOIN, _XL + _HALF, _YB - _HALF - _JOIN),
    "c": (_XR - _HALF, _MID + _HALF + _JOIN, _XR + _HALF, _YB - _HALF - _JOIN),
}

_DIGIT_SEGMENTS = {
    0: "abcdef",
    1: "bc",
    2: "abged",
    3: "abgcd",
    4: "fgbc",
    5: "afgcd",
    6: "afgcde",
    7: "abc",
    8: "abcdefg",
    9: "abcdfg",
}

_COLON_HALF = 11.0
_COLON_DOTS = [(COLON_W / 2.0, DH * 0.35), (COLON_W / 2.0, DH * 0.65)]


def digit_ink(value: int, x: float, y: float) -> bool:
    """Is local point ``(x, y)`` inside digit ``value``'s lit segments?"""
    for name in _DIGIT_SEGMENTS[value]:
        x0, y0, x1, y1 = _SEGMENTS[name]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return True
    return False


def colon_ink(x: float, y: float) -> bool:
    """Is local point ``(x, y)`` inside either square colon dot?"""
    for cx, cy in _COLON_DOTS:
        if abs(x - cx) <= _COLON_HALF and abs(y - cy) <= _COLON_HALF:
            return True
    return False


# --- sizing -------------------------------------------------------

MAX_ASPECT = 1.5  # a rendered digit's larger side <= 1.5x its smaller side
_MIN_DIGIT_SUBPX_H = 12.0  # below this a seven-segment digit is unreadable -> text
_MIN_DIGIT_SUBPX_W = 8.0


def total_local_width(time_str: str) -> float:
    w = 0.0
    for i, ch in enumerate(time_str):
        if i:
            w += GAP
        w += COLON_W if ch == ":" else DW
    return w


def fit_scale(rows: int, cols: int, time_str: str = "12:34:56") -> tuple[float, float] | None:
    """Horizontal & vertical scale (local units -> subpixels) for the clock.

    The subpixel canvas is ``cols`` wide and ``2*rows`` tall (half-blocks give
    2x vertical resolution, which also makes a subpixel roughly square). We take
    the largest uniform scale that fits, then let the axis with room to spare
    stretch by at most ``MAX_ASPECT`` before we stop and just centre in the
    slack. ``None`` if the result would be too small to read.
    """
    tw = total_local_width(time_str)
    sx_max = cols / tw
    sy_max = (2 * rows) / DH
    s = min(sx_max, sy_max)
    if s * DH < _MIN_DIGIT_SUBPX_H or s * DW < _MIN_DIGIT_SUBPX_W:
        return None
    sx = min(sx_max, MAX_ASPECT * s)
    sy = min(sy_max, MAX_ASPECT * s)
    return sx, sy


# --- rendering --------------------------------------------------

_HALFBLOCKS = {(True, True): "█", (True, False): "▀", (False, True): "▄", (False, False): " "}


def render_art(time_str: str, rows: int, cols: int, sx: float, sy: float) -> list[str]:
    """Rasterise the vector clock and pack it into half-block text lines."""
    pxw, pxh = cols, rows * 2
    grid = [[False] * pxw for _ in range(pxh)]

    content_w = round(sx * total_local_width(time_str))
    content_h = round(sy * DH)
    ox = (pxw - content_w) // 2
    oy = (pxh - content_h) // 2

    lx = 0.0
    for i, ch in enumerate(time_str):
        w = COLON_W if ch == ":" else DW
        x0 = ox + round(sx * lx)
        is_colon = ch == ":"
        value = None if is_colon else int(ch)
        for Y in range(max(0, oy), min(pxh, oy + content_h)):
            cy = (Y - oy + 0.5) / sy
            row = grid[Y]
            for X in range(max(0, x0), min(pxw, x0 + round(sx * w) + 1)):
                cx = (X - x0 + 0.5) / sx
                if colon_ink(cx, cy) if is_colon else digit_ink(value, cx, cy):
                    row[X] = True
        lx += w + GAP

    out = []
    for r in range(rows):
        top, bot = grid[2 * r], grid[2 * r + 1]
        out.append("".join(_HALFBLOCKS[(top[c], bot[c])] for c in range(cols)))
    return out


def _render_text(time_str: str, rows: int, cols: int) -> list[str]:
    grid = [" " * cols for _ in range(rows)]
    row = (rows - 1) // 2 if rows else 0
    if 0 <= row < rows:
        grid[row] = time_str.center(cols)[:cols].ljust(cols)
    return grid


def render(time_str: str, rows: int, cols: int) -> list[str]:
    """Return exactly ``rows`` lines of exactly ``cols`` chars."""
    rows = max(rows, 0)
    cols = max(cols, 0)
    if choose_mode(rows) == "art":
        scale = fit_scale(rows, cols, time_str)
        if scale is not None:
            return render_art(time_str, rows, cols, *scale)
    return _render_text(time_str, rows, cols)
