"""Pure, side-effect-free clock rendering.

Everything here is deterministic and unit-tested. The runtime shell in
``cli.py`` supplies the current time and terminal size and paints the result.

Big digits
----------
Digits are a seven-segment design on a small integer grid. Every grid cell is
one of six states -- empty, full (``█``), or one of the four 45-degree triangles
``◤ ◥ ◣ ◢`` -- and convex corners are chamfered by exactly one cell, which is
what gives the segmented-display look.

To draw, each design cell is expanded to an ``nx`` x ``ny`` block of characters:
empty and full cells tile trivially, and a triangle cell tiles into a clean
right triangle of full blocks with a single row of triangle glyphs on the
hypotenuse. Because the scale factors are integers this never produces ragged
or half-lit edges -- only ``█`` and the four triangles ever appear.
"""

from __future__ import annotations

from functools import lru_cache

BLOCK = "█"
_TRI = {"F": "◤", "J": "◢", "L": "◣", "P": "◥"}  # design char -> glyph

# --- time formatting ----------------------------------------------

def format_time(h: int, m: int, s: int) -> str:
    """Return ``hh:mm:ss`` (zero-padded, 24-hour)."""
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        raise ValueError(f"time out of range: {h}:{m}:{s}")
    return f"{h:02d}:{m:02d}:{s:02d}"


# --- layout decision --------------------------------------------

TEXT_LINE_LIMIT = 7


def choose_mode(rows: int) -> str:
    """``"art"`` when there is real headroom (>= 8 lines), else ``"text"``."""
    return "art" if rows > TEXT_LINE_LIMIT else "text"


# --- seven-segment design grid --------------------------------

_DIGIT_SEGMENTS = {
    0: "ABCDEF", 1: "BC", 2: "ABGED", 3: "ABGCD", 4: "FGBC",
    5: "AFGCD", 6: "AFGCDE", 7: "ABC", 8: "ABCDEFG", 9: "ABCDFG",
}


def _segment_rects(w: int, h: int, t: int):
    hg = (h - t) // 2
    return {
        "A": (0, w, 0, t),
        "D": (0, w, h - t, h),
        "G": (0, w, hg, hg + t),
        "F": (0, t, 0, hg + t),
        "B": (w - t, w, 0, hg + t),
        "E": (0, t, hg, h),
        "C": (w - t, w, hg, h),
    }


def _chamfer(grid, w: int, h: int):
    """Grid of bools -> rows of design chars, convex corners cut by one cell."""

    def on(x, y):
        return 0 <= x < w and 0 <= y < h and grid[y][x]

    out = [["█" if grid[y][x] else " " for x in range(w)] for y in range(h)]
    for y in range(h):
        for x in range(w):
            if not grid[y][x]:
                continue
            up, dn = not on(x, y - 1), not on(x, y + 1)
            lf, rt = not on(x - 1, y), not on(x + 1, y)
            if up and rt and not on(x + 1, y - 1) and on(x, y + 1) and on(x - 1, y):
                out[y][x] = "L"   # cut top-right, keep ◣
            elif up and lf and not on(x - 1, y - 1) and on(x, y + 1) and on(x + 1, y):
                out[y][x] = "J"   # cut top-left, keep ◢
            elif dn and rt and not on(x + 1, y + 1) and on(x, y - 1) and on(x - 1, y):
                out[y][x] = "F"   # cut bottom-right, keep ◤
            elif dn and lf and not on(x - 1, y + 1) and on(x, y - 1) and on(x + 1, y):
                out[y][x] = "P"   # cut bottom-left, keep ◥
    return ["".join(r) for r in out]


def _colon_bitmap(w: int, h: int):
    grid = [[False] * w for _ in range(h)]
    dot_h = 3 if h >= 9 else 2
    for y0 in (1, h - 1 - dot_h):            # two dots with a gap between
        for y in range(y0, y0 + dot_h):
            for x in range(w):
                grid[y][x] = True
    return _chamfer(grid, w, h)


class Font:
    """A digit design at one grid size."""

    def __init__(self, w: int, h: int, t: int):
        self.w, self.h, self.t = w, h, t
        self.colon_w = max(3, round(w * 0.34))
        self.gap = max(1, round(w * 0.12))
        rects = _segment_rects(w, h, t)
        self.digits = {}
        for value, segs in _DIGIT_SEGMENTS.items():
            grid = [[False] * w for _ in range(h)]
            for s in segs:
                x0, x1, y0, y1 = rects[s]
                for yy in range(y0, y1):
                    for xx in range(x0, x1):
                        grid[yy][xx] = True
            self.digits[value] = _chamfer(grid, w, h)
        self.colon = _colon_bitmap(self.colon_w, h)

    def cell_width(self, ch: str) -> int:
        return self.colon_w if ch == ":" else self.w

    def bitmap(self, ch: str):
        return self.colon if ch == ":" else self.digits[int(ch)]


_FONTS = [Font(10, 10, 2), Font(7, 7, 1)]  # try large first, then small


def total_grid_width(font: "Font", time_str: str) -> int:
    w = 0
    for i, ch in enumerate(time_str):
        if i:
            w += font.gap
        w += font.cell_width(ch)
    return w


# --- fitting ----------------------------------------------------

MAX_ASPECT = 1.5


def fit(rows: int, cols: int, time_str: str = "12:34:56"):
    """Pick ``(font, nx, ny)`` -- the largest design that fits ``rows`` x ``cols``.

    ``nx`` / ``ny`` are the integer character size of one design cell. A cell is
    visually square at ``nx == 2*ny`` (character cells are twice as tall as
    wide); we start there and let the roomier axis stretch by up to
    ``MAX_ASPECT`` before stopping (surplus becomes centring margin). ``None``
    if not even the small font fits at 1x.
    """
    for font in _FONTS:
        wtot = total_grid_width(font, time_str)
        s_h = rows // font.h
        s_w = cols // wtot
        s = min(s_h, s_w)
        if s < 1:
            continue
        # use slack on either axis, but stretch each by at most MAX_ASPECT
        cap = int(s * MAX_ASPECT)
        nx = min(s_w, cap)
        ny = min(s_h, cap)
        return font, nx, ny
    return None


# --- rendering -------------------------------------------------

_SUB = 4  # sub-samples per axis when rasterising a triangle cell


def _solid(ch: str, u: float, v: float) -> bool:
    if ch == "F":       # ◤ upper-left
        return u + v <= 1.0
    if ch == "J":       # ◢ lower-right
        return u + v >= 1.0
    if ch == "P":       # ◥ upper-right
        return v <= u
    return v >= u       # ◣ lower-left


@lru_cache(maxsize=512)
def _expand(ch: str, nx: int, ny: int) -> tuple[str, ...]:
    if ch == " ":
        return (" " * nx,) * ny
    if ch == "█":
        return ("█" * nx,) * ny
    glyph = _TRI[ch]
    hi = _SUB * _SUB * 3 // 4
    lo = _SUB * _SUB // 4
    rows = []
    for i in range(ny):
        line = []
        for j in range(nx):
            cover = sum(
                _solid(ch, (j + (sx + 0.5) / _SUB) / nx, (i + (sy + 0.5) / _SUB) / ny)
                for sx in range(_SUB) for sy in range(_SUB)
            )
            line.append("█" if cover >= hi else " " if cover <= lo else glyph)
        rows.append("".join(line))
    return tuple(rows)


def _render_glyph(bitmap, nx: int, ny: int) -> list[str]:
    out = []
    for design_row in bitmap:
        pieces = [_expand(c, nx, ny) for c in design_row]
        for k in range(ny):
            out.append("".join(p[k] for p in pieces))
    return out


def render_art(time_str: str, rows: int, cols: int, font: "Font", nx: int, ny: int) -> list[str]:
    blocks = [_render_glyph(font.bitmap(ch), nx, ny) for ch in time_str]
    gap = " " * (font.gap * nx)
    body = [gap.join(parts) for parts in zip(*blocks)]
    bw = len(body[0]) if body else 0
    left = max(0, (cols - bw) // 2)
    top = max(0, (rows - len(body)) // 2)

    grid = [" " * cols for _ in range(rows)]
    for i, line in enumerate(body):
        if 0 <= top + i < rows:
            grid[top + i] = (" " * left + line)[:cols].ljust(cols)
    return grid


def _render_text(time_str: str, rows: int, cols: int) -> list[str]:
    grid = [" " * cols for _ in range(rows)]
    row = (rows - 1) // 2 if rows else 0
    if 0 <= row < rows:
        grid[row] = time_str.center(cols)[:cols].ljust(cols)
    return grid


def render(time_str: str, rows: int, cols: int) -> list[str]:
    """Return exactly ``rows`` lines of exactly ``cols`` chars."""
    rows, cols = max(rows, 0), max(cols, 0)
    if choose_mode(rows) == "art":
        picked = fit(rows, cols, time_str)
        if picked is not None:
            return render_art(time_str, rows, cols, *picked)
    return _render_text(time_str, rows, cols)
