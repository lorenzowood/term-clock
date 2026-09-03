"""Pure, side-effect-free clock rendering.

Everything here is deterministic and unit-tested. The runtime shell in
``cli.py`` supplies the current time and terminal size and paints the result.

Big digits use a **5x7 dot-matrix font** drawn with solid block characters.
Each matrix "pixel" is blown up to a ``pw`` x ``ph`` rectangle of blocks, and
``pw`` / ``ph`` are chosen to fill the terminal in both directions (see
``best_pixel_scale``). This reads far more clearly than thin line art.
"""

from __future__ import annotations

BLOCK = "█"  # full block

# --- time formatting -------------------------------------------------------

def format_time(h: int, m: int, s: int) -> str:
    """Return ``hh:mm:ss`` (zero-padded, 24-hour)."""
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        raise ValueError(f"time out of range: {h}:{m}:{s}")
    return f"{h:02d}:{m:02d}:{s:02d}"


# --- layout decisions ----------------------------------------------------

TEXT_LINE_LIMIT = 7  # "less than seven lines" -> text; 7 stays text too


def choose_mode(rows: int) -> str:
    """``"art"`` when there is real headroom (>= 8 lines), else ``"text"``."""
    return "art" if rows > TEXT_LINE_LIMIT else "text"


# --- 5x7 dot-matrix font ----------------------------------------------
#
# Each glyph is a list of rows of "0"/"1". Digits are 5 wide, the colon 2 wide;
# all glyphs are 7 tall. A single blank pixel column separates adjacent glyphs.

GLYPH_H = 7
DIGIT_W = 5
COLON_W = 2
GAP_W = 1

_FONT: dict[str, list[str]] = {
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    ":": ["00", "11", "11", "00", "11", "11", "00"],
}


def glyph_pixels(ch: str) -> list[str]:
    """The raw 0/1 matrix for a single character (``0``-``9`` or ``:``)."""
    try:
        return _FONT[ch]
    except KeyError:
        raise ValueError(f"no glyph for {ch!r}") from None


def _glyph_width(ch: str) -> int:
    return COLON_W if ch == ":" else DIGIT_W


# --- geometry ----------------------------------------------------------

def block_pixel_size(time_str: str) -> tuple[int, int]:
    """Size of the whole clock, measured in matrix pixels: ``(width, height)``."""
    width = sum(_glyph_width(c) for c in time_str)
    width += GAP_W * (len(time_str) - 1)
    return width, GLYPH_H


def best_pixel_scale(rows: int, cols: int, time_str: str) -> tuple[int, int] | None:
    """Pixel dimensions ``(pw, ph)`` for the biggest legible clock that fits.

    ``ph`` fills the available height, ``pw`` fills the available width, so the
    digits use the whole terminal. A legibility clamp then keeps the pixels in
    a sane aspect band: a terminal cell is roughly twice as tall as it is wide,
    so ``pw == 2*ph`` looks visually square. We allow bold, wide pixels (up to
    ``pw == 4*ph``) because fatter strokes read better, and let a pixel stretch
    up to ``ph == 2*pw`` vertically so a tall, narrow terminal still fills its
    height — but no further, or the digits get spindly. Returns ``None`` if not
    even 1x1 pixels fit.
    """
    wp, hp = block_pixel_size(time_str)
    ph = rows // hp
    pw = cols // wp
    if ph < 1 or pw < 1:
        return None
    pw = min(pw, 4 * ph)
    ph = min(ph, 2 * pw)
    return pw, ph


# --- rendering -------------------------------------------------------

def _blank_grid(rows: int, cols: int) -> list[list[str]]:
    return [[" "] * cols for _ in range(rows)]


def _place(grid, block: list[str], top: int, left: int) -> None:
    for r, line in enumerate(block):
        gr = top + r
        if 0 <= gr < len(grid):
            row = grid[gr]
            for c, ch in enumerate(line):
                gc = left + c
                if 0 <= gc < len(row):
                    row[gc] = ch


def _pixel_grid(time_str: str) -> list[str]:
    """Compose the glyphs into one 0/1 pixel grid, ``GLYPH_H`` rows tall."""
    rows = ["" for _ in range(GLYPH_H)]
    for i, ch in enumerate(time_str):
        if i:
            for r in range(GLYPH_H):
                rows[r] += "0" * GAP_W
        g = glyph_pixels(ch)
        for r in range(GLYPH_H):
            rows[r] += g[r]
    return rows


def render_matrix(time_str: str, rows: int, cols: int, pw: int, ph: int) -> list[str]:
    """Draw ``time_str`` as block digits with ``pw`` x ``ph`` pixels, centred."""
    pixels = _pixel_grid(time_str)
    block = [
        "".join((BLOCK if bit == "1" else " ") * pw for bit in prow)
        for prow in pixels
        for _ in range(ph)
    ]
    bw = len(block[0]) if block else 0
    bh = len(block)
    grid = _blank_grid(rows, cols)
    _place(grid, block, (rows - bh) // 2, (cols - bw) // 2)
    return ["".join(r) for r in grid]


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
        scale = best_pixel_scale(rows, cols, time_str)
        if scale is not None:
            return render_matrix(time_str, rows, cols, *scale)
    return _render_text(time_str, rows, cols)
