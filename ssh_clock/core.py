"""Pure, side-effect-free clock rendering.

Everything here is deterministic and unit-tested. The runtime shell in
``cli.py`` supplies the current time and terminal size and paints the result.
"""

from __future__ import annotations

# --- time formatting -------------------------------------------------------

def format_time(h: int, m: int, s: int) -> str:
    """Return ``hh:mm:ss`` (zero-padded, 24-hour)."""
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        raise ValueError(f"time out of range: {h}:{m}:{s}")
    return f"{h:02d}:{m:02d}:{s:02d}"


# --- layout decisions -----------------------------------------------------

TEXT_LINE_LIMIT = 7  # "less than seven lines" -> text; 7 stays text too


def choose_mode(rows: int) -> str:
    """``"art"`` when there is real headroom (>= 8 lines), else ``"text"``."""
    return "art" if rows > TEXT_LINE_LIMIT else "text"


# --- seven-segment geometry ---------------------------------------------
#
# For a given integer ``scale`` (>= 1):
#   horizontal segment width  hw = 2 * scale
#   vertical   segment height vh = 2 * scale   (taller, so digits look like
#                                               digits rather than squares)
#   digit cell : width  = hw + 2 , height = 2 * vh + 3
#   colon cell : width  = COLON_WIDTH , height = same as a digit
# Cells are separated by a single space. The clock string "hh:mm:ss" is
# 6 digits + 2 colons + 7 gaps.

COLON_WIDTH = 2
_GAP = 1
_N_DIGITS = 6
_N_COLONS = 2
_N_GAPS = 7

# segments a,b,c,d,e,f,g  (standard 7-seg layout)
#    aaa
#   f   b
#   f   b
#    ggg
#   e   c
#   e   c
#    ddd
_SEGMENTS = {
    0: "abcdef",
    1: "bc",
    2: "abged",
    3: "abgcd",
    4: "fgbc",
    5: "afgcd",
    6: "afgecd",
    7: "abc",
    8: "abcdefg",
    9: "abcdfg",
}


def digit_width(scale: int) -> int:
    return 2 * scale + 2


def block_height(scale: int) -> int:
    return 4 * scale + 3


def block_width(scale: int) -> int:
    return (
        _N_DIGITS * digit_width(scale)
        + _N_COLONS * COLON_WIDTH
        + _N_GAPS * _GAP
    )


def best_scale(rows: int, cols: int) -> int | None:
    """Largest ``scale`` whose full clock block fits in ``rows`` x ``cols``.

    ``None`` when even ``scale == 1`` does not fit.
    """
    s = 0
    while block_width(s + 1) <= cols and block_height(s + 1) <= rows:
        s += 1
    return s or None


def seven_segment_digit(d: int, scale: int) -> list[str]:
    """Render digit ``d`` as a list of equal-length strings."""
    if d not in _SEGMENTS:
        raise ValueError(f"not a single digit: {d}")
    on = set(_SEGMENTS[d])
    hw, vh = 2 * scale, 2 * scale
    w = digit_width(scale)

    def hbar(seg: str) -> str:
        return " " + (("_" * hw) if seg in on else (" " * hw)) + " "

    def vrow(left: str, right: str) -> str:
        lc = "|" if left in on else " "
        rc = "|" if right in on else " "
        return lc + (" " * hw) + rc

    rows = [hbar("a")]
    rows += [vrow("f", "b") for _ in range(vh)]
    rows.append(hbar("g"))
    rows += [vrow("e", "c") for _ in range(vh)]
    rows.append(hbar("d"))
    assert all(len(r) == w for r in rows)
    assert len(rows) == block_height(scale)
    return rows


def colon_cell(scale: int) -> list[str]:
    """Two dots, at roughly 1/3 and 2/3 of the cell height."""
    h = block_height(scale)
    top = h // 3
    bottom = h - 1 - h // 3
    dot = "o".center(COLON_WIDTH)
    blank = " " * COLON_WIDTH
    return [dot if i in (top, bottom) else blank for i in range(h)]


# --- full-screen render -------------------------------------------------

def _blank_grid(rows: int, cols: int) -> list[list[str]]:
    return [[" "] * cols for _ in range(rows)]


def _place(grid, block: list[str], top: int, left: int) -> None:
    for r, line in enumerate(block):
        gr = top + r
        if 0 <= gr < len(grid):
            for c, ch in enumerate(line):
                gc = left + c
                if 0 <= gc < len(grid[0]):
                    grid[gr][gc] = ch


def _render_text(time_str: str, rows: int, cols: int) -> list[str]:
    grid = [" " * cols for _ in range(rows)]
    row = (rows - 1) // 2 if rows else 0
    if 0 <= row < rows:
        grid[row] = time_str.center(cols)[:cols].ljust(cols)
    return grid


def _render_art(time_str: str, rows: int, cols: int, scale: int) -> list[str]:
    cells: list[list[str]] = []
    for ch in time_str:
        if ch == ":":
            cells.append(colon_cell(scale))
        else:
            cells.append(seven_segment_digit(int(ch), scale))

    bw, bh = block_width(scale), block_height(scale)
    grid = _blank_grid(rows, cols)
    top = (rows - bh) // 2
    left = (cols - bw) // 2

    x = left
    for i, cell in enumerate(cells):
        _place(grid, cell, top, x)
        x += len(cell[0])
        if i != len(cells) - 1:
            x += _GAP
    return ["".join(r) for r in grid]


def render(time_str: str, rows: int, cols: int) -> list[str]:
    """Return exactly ``rows`` lines of exactly ``cols`` chars."""
    rows = max(rows, 0)
    cols = max(cols, 0)
    if choose_mode(rows) == "art":
        scale = best_scale(rows, cols)
        if scale is not None:
            return _render_art(time_str, rows, cols, scale)
    return _render_text(time_str, rows, cols)
