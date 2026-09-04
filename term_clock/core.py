"""Pure, side-effect-free clock rendering.

Everything here is deterministic and unit-tested. The runtime shell in
``cli.py`` supplies the current time and terminal size and paints the result.

Big digits
----------
Seven-segment bars drawn with full blocks ``█``. Horizontal bars run across,
vertical bars run down. Convex corners are cut with a 1:1 45-degree stair of
``◤ ◥ ◣ ◢`` -- one column per row, no sampling, no off-angle hypotenuses.
"""

from __future__ import annotations

import locale
from dataclasses import dataclass

BLOCK = "█"

_DIGIT_SEGMENTS = {
    0: "ABCDEF", 1: "BC", 2: "ABGED", 3: "ABGCD", 4: "FGBC",
    5: "AFGCD", 6: "AFGCDE", 7: "ABC", 8: "ABCDEFG", 9: "ABCDFG",
}

# 45° cut: (step-x, step-y, glyph on the diagonal)
_CUT = {
    "UL": (1, 1, "◢"),
    "UR": (-1, 1, "◣"),
    "DL": (1, -1, "◥"),
    "DR": (-1, -1, "◤"),
}


def format_time(h: int, m: int, s: int, hour_format: str = "24") -> str:
    """Return ``hh:mm:ss`` (zero-padded). ``hour_format`` is ``"24"`` or ``"12"``."""
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        raise ValueError(f"time out of range: {h}:{m}:{s}")
    if hour_format == "12":
        h = h % 12 or 12
    elif hour_format != "24":
        raise ValueError(f"unknown hour format: {hour_format}")
    return f"{h:02d}:{m:02d}:{s:02d}"


def hour_period(h: int) -> str:
    """``AM`` before noon, ``PM`` from noon inclusive."""
    if not (0 <= h < 24):
        raise ValueError(f"hour out of range: {h}")
    return "AM" if h < 12 else "PM"


def system_hour_format(t_fmt: str | None = None) -> str:
    """``12`` or ``24`` from the environment's time format; ``24`` if unknown."""
    if t_fmt is None:
        t_fmt = _locale_t_fmt()
    if not t_fmt:
        return "24"
    if "%I" in t_fmt or "%p" in t_fmt or "%r" in t_fmt:
        return "12"
    return "24"


def _locale_t_fmt() -> str | None:
    try:
        locale.setlocale(locale.LC_TIME, "")
    except locale.Error:
        pass
    try:
        return locale.nl_langinfo(locale.T_FMT)
    except (AttributeError, ValueError, locale.Error):
        return None


TEXT_LINE_LIMIT = 7


def choose_mode(rows: int) -> str:
    """``"art"`` when there is real headroom (>= 8 lines), else ``"text"``."""
    return "art" if rows > TEXT_LINE_LIMIT else "text"


@dataclass(frozen=True)
class Style:
    """User-facing layout knobs."""

    padding: int = 1
    spacing: int = 2
    hour_format: str = "24"


@dataclass(frozen=True)
class Layout:
    """Stroke thickness and the two inner spans of a seven-segment cell."""

    t: int
    hw: int
    vh: int
    gap: int
    colon_w: int

    @property
    def digit_w(self) -> int:
        return 2 * self.t + self.hw

    @property
    def digit_h(self) -> int:
        return 3 * self.t + 2 * self.vh


def colon_metrics(digit_h: int) -> tuple[int, int, int]:
    """``(dot_w, dot_h, gap)`` for two axis-aligned colon dots.

    The pair spans at most one third of ``digit_h`` (floored at 3 rows so a
    tiny digit still gets two dots with a hole between them).
    """
    cap = digit_h // 3
    span = cap if cap >= 3 else min(3, max(digit_h, 0))
    if span < 3:
        return max(1, span), max(1, span), 0
    gap = 1 if span < 6 else max(1, span // 4)
    dot_h = max(1, (span - gap) // 2)
    gap = span - 2 * dot_h
    if gap < 1:
        dot_h = max(1, (span - 1) // 2)
        gap = span - 2 * dot_h
    # 1-row dots are two cells wide so they stay visible; larger dots stay square.
    dot_w = 2 if dot_h == 1 else dot_h
    return dot_w, dot_h, gap


def colon_width(digit_h: int) -> int:
    return colon_metrics(digit_h)[0]


def _segment_rects(lay: Layout):
    t, w, h = lay.t, lay.digit_w, lay.digit_h
    hg = t + lay.vh
    return {
        "A": (0, w, 0, t),
        "D": (0, w, h - t, h),
        "G": (0, w, hg, hg + t),
        "F": (0, t, 0, hg + t),
        "B": (w - t, w, 0, hg + t),
        "E": (0, t, hg, h),
        "C": (w - t, w, hg, h),
    }


def _fill_rects(ink, rects, names):
    for name in names:
        x0, x1, y0, y1 = rects[name]
        for y in range(y0, y1):
            for x in range(x0, x1):
                ink[y][x] = True


def _convex_corners(ink):
    h, w = len(ink), len(ink[0])

    def on(x, y):
        return 0 <= x < w and 0 <= y < h and ink[y][x]

    out = []
    for y in range(h):
        for x in range(w):
            if not ink[y][x]:
                continue
            up, dn = not on(x, y - 1), not on(x, y + 1)
            lf, rt = not on(x - 1, y), not on(x + 1, y)
            if up and rt and not on(x + 1, y - 1) and on(x, y + 1) and on(x - 1, y):
                out.append((x, y, "UR"))
            elif up and lf and not on(x - 1, y - 1) and on(x, y + 1) and on(x + 1, y):
                out.append((x, y, "UL"))
            elif dn and rt and not on(x + 1, y + 1) and on(x, y - 1) and on(x - 1, y):
                out.append((x, y, "DR"))
            elif dn and lf and not on(x - 1, y + 1) and on(x, y - 1) and on(x + 1, y):
                out.append((x, y, "DL"))
    return out


def _cut_corner(grid, cx, cy, n, kind):
    """1:1 45° stair of size ``n``: put the triangle on the diagonal, clear outside."""
    sx, sy, glyph = _CUT[kind]
    h, w = len(grid), len(grid[0])
    for k in range(n):
        x_diag, y = cx + sx * (n - 1 - k), cy + sy * k
        if 0 <= x_diag < w and 0 <= y < h:
            grid[y][x_diag] = glyph
        for j in range(n - 1 - k):
            x = cx + sx * j
            if 0 <= x < w and 0 <= y < h:
                grid[y][x] = " "


def _raster(ink, t: int) -> list[str]:
    grid = [["█" if cell else " " for cell in row] for row in ink]
    n = max(1, t // 2)
    for cx, cy, kind in _convex_corners(ink):
        _cut_corner(grid, cx, cy, n, kind)
    return ["".join(row) for row in grid]


def paint(ch: str, lay: Layout) -> list[str]:
    """One glyph (``0``–``9`` or ``:``) as ``digit_h`` rows of ``digit_w`` / ``colon_w``."""
    h = lay.digit_h
    if ch == ":":
        w = max(1, lay.colon_w)
        ink = [[" "] * w for _ in range(h)]
        dw, dh, dgap = colon_metrics(h)
        dw = min(dw, w)
        span = 2 * dh + dgap
        y0 = max(0, (h - span) // 2)
        x0 = max(0, (w - dw) // 2)
        for y in range(y0, y0 + dh):
            for x in range(x0, x0 + dw):
                ink[y][x] = "█"
        y1 = y0 + dh + dgap
        for y in range(y1, y1 + dh):
            for x in range(x0, x0 + dw):
                if 0 <= y < h:
                    ink[y][x] = "█"
        return ["".join(row) for row in ink]

    w = lay.digit_w
    ink = [[False] * w for _ in range(h)]
    _fill_rects(ink, _segment_rects(lay), _DIGIT_SEGMENTS[int(ch)])
    return _raster(ink, lay.t)


def _clock_width(lay: Layout, time_str: str) -> int:
    w = 0
    for i, ch in enumerate(time_str):
        if i:
            w += lay.gap
        w += lay.colon_w if ch == ":" else lay.digit_w
    return w


def _suffix_span(suffix: str, gap: int) -> int:
    return (gap + len(suffix)) if suffix else 0


def _label(time_str: str, suffix: str) -> str:
    return f"{time_str} {suffix}" if suffix else time_str


MAX_ASPECT = 1.5


def fit(
    rows: int,
    cols: int,
    time_str: str = "12:34:56",
    style: Style | None = None,
    suffix: str = "",
) -> Layout | None:
    """Largest layout that fits the inner (padded) frame.

    Default cell is 5t×5t; each axis may stretch by at most ``MAX_ASPECT``.
    """
    style = style or Style()
    pad = max(0, style.padding)
    gap = max(0, style.spacing)
    rows = max(0, rows - 2 * pad)
    cols = max(0, cols - 2 * pad - _suffix_span(suffix, gap))
    n_d = sum(c != ":" for c in time_str) or 1
    n_c = time_str.count(":")
    n_g = max(0, len(time_str) - 1)
    best: Layout | None = None
    for t in range(1, rows + 1):
        if 5 * t > rows:
            break
        max_h = min(rows, int(5 * t * MAX_ASPECT))
        colon_w = colon_width(max_h)
        lo = Layout(t, 3 * t, t, gap, colon_w)
        if lo.digit_h > rows or _clock_width(lo, time_str) > cols:
            continue
        vh = (max_h - 3 * t) // 2
        if vh < t:
            continue
        max_w = min(
            (cols - n_c * colon_w - n_g * gap) // n_d,
            int(5 * t * MAX_ASPECT),
        )
        hw = max_w - 2 * t
        if hw < 3 * t:
            hw = 3 * t
        lay = Layout(t, hw, vh, gap, colon_width(3 * t + 2 * vh))
        if lay.digit_h > rows or _clock_width(lay, time_str) > cols:
            continue
        best = lay
    return best


def render_art(
    time_str: str,
    rows: int,
    cols: int,
    lay: Layout,
    suffix: str = "",
) -> list[str]:
    blocks = [paint(ch, lay) for ch in time_str]
    gap = " " * lay.gap
    body = [gap.join(parts) for parts in zip(*blocks)]
    if suffix and body:
        extra = gap + suffix
        mid = len(body) // 2
        body = [
            line + (extra if i == mid else " " * len(extra))
            for i, line in enumerate(body)
        ]
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


def render(
    time_str: str,
    rows: int,
    cols: int,
    style: Style | None = None,
    suffix: str = "",
) -> list[str]:
    """Return exactly ``rows`` lines of exactly ``cols`` chars."""
    style = style or Style()
    rows, cols = max(rows, 0), max(cols, 0)
    if choose_mode(rows) == "art":
        lay = fit(rows, cols, time_str, style=style, suffix=suffix)
        if lay is not None:
            return render_art(time_str, rows, cols, lay, suffix=suffix)
    return _render_text(_label(time_str, suffix), rows, cols)
