"""Pure, side-effect-free clock rendering.

Everything here is deterministic and unit-tested. The runtime shell in
``cli.py`` supplies the current time and terminal size and paints the result.

Big digits
----------
Seven-segment bars drawn with full blocks ``█``. Horizontal bars run across,
vertical bars run down. Free ends of those bars stay square. Outer L-joint
curves (two segments meeting) are cut with a 1:1 45-degree stair of
``◤ ◥ ◣ ◢`` -- one column per row, no sampling, no off-angle hypotenuses.
"""

from __future__ import annotations

import locale
from dataclasses import dataclass

from . import interval as iv

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
    interval_minutes: int = 0
    interval_start_s: int = 0
    interval_amber_s: int = 5 * 60
    interval_red_s: int = 60
    interval_amber_color: str = "#f09000"
    interval_red_color: str = "#ff0000"
    interval_bar: bool = False
    clock_color: str | None = None
    background_color: str | None = None


@dataclass
class Frame:
    """Character grid plus optional per-cell foreground hex colours."""

    chars: list[str]
    fg: list[list[str | None]]

    @classmethod
    def blank(cls, rows: int, cols: int) -> Frame:
        return cls(
            [" " * cols for _ in range(rows)],
            [[None] * cols for _ in range(rows)],
        )

    @classmethod
    def from_chars(cls, chars: list[str], ink: str | None = None) -> Frame:
        fg = [[ink if c != " " else None for c in line] for line in chars]
        return cls(list(chars), fg)


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


def _bar_end_corners(corners, t: int) -> set:
    """Convex corner pairs that are free ends of a bar, not L-joint curves.

    A termination is two corners spanning stroke thickness ``t``: UL+DL or
    UR+DR on a vertical face, UL+UR or DL+DR on a horizontal face.
    """
    if t < 2:
        return set()
    span = t - 1
    by_kind: dict[str, set[tuple[int, int]]] = {}
    for x, y, k in corners:
        by_kind.setdefault(k, set()).add((x, y))
    skip: set[tuple[int, int, str]] = set()

    def pair(k1: str, k2: str, dx: int, dy: int) -> None:
        for x, y in by_kind.get(k1, ()):
            other = (x + dx, y + dy)
            if other in by_kind.get(k2, ()):
                skip.add((x, y, k1))
                skip.add((other[0], other[1], k2))

    pair("UL", "DL", 0, span)
    pair("UR", "DR", 0, span)
    pair("UL", "UR", span, 0)
    pair("DL", "DR", span, 0)
    return skip


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
    corners = _convex_corners(ink)
    skip = _bar_end_corners(corners, t)
    for cx, cy, kind in corners:
        if (cx, cy, kind) not in skip:
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


def _bar_extra(style: Style, t: int) -> int:
    if style.interval_minutes <= 0 or not style.interval_bar:
        return 0
    return max(0, style.padding) + max(1, t)


def _ink_color(style: Style, state: iv.IntervalState | None) -> str | None:
    if state is None:
        return style.clock_color
    if state.zone == "red":
        return style.interval_red_color
    if state.zone == "amber":
        return style.interval_amber_color
    return style.clock_color


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
        extra = _bar_extra(style, t)
        avail = rows - extra
        if avail < 1 or 5 * t > avail:
            break
        max_h = min(avail, int(5 * t * MAX_ASPECT))
        colon_w = colon_width(max_h)
        lo = Layout(t, 3 * t, t, gap, colon_w)
        if lo.digit_h > avail or _clock_width(lo, time_str) > cols:
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
        if lay.digit_h > avail or _clock_width(lay, time_str) > cols:
            continue
        best = lay
    return best


def _put(frame: Frame, x: int, y: int, ch: str, color: str | None) -> None:
    if y < 0 or y >= len(frame.chars):
        return
    row = frame.chars[y]
    if x < 0 or x >= len(row):
        return
    frame.chars[y] = row[:x] + ch + row[x + 1 :]
    frame.fg[y][x] = color if ch != " " else None


def _blit(frame: Frame, x0: int, y: int, line: str, ink: str | None) -> None:
    for i, ch in enumerate(line):
        _put(frame, x0 + i, y, ch, ink if ch != " " else None)


def render_art(
    time_str: str,
    rows: int,
    cols: int,
    lay: Layout,
    suffix: str = "",
    style: Style | None = None,
    state: iv.IntervalState | None = None,
) -> Frame:
    style = style or Style()
    blocks = [paint(ch, lay) for ch in time_str]
    gap = " " * lay.gap
    digit_body = [gap.join(parts) for parts in zip(*blocks)]
    digit_w = len(digit_body[0]) if digit_body else 0
    display = digit_body
    if suffix and digit_body:
        extra = gap + suffix
        mid = len(digit_body) // 2
        display = [
            line + (extra if i == mid else " " * len(extra))
            for i, line in enumerate(digit_body)
        ]
    disp_w = len(display[0]) if display else 0
    bar_h = lay.t if (state is not None and style.interval_bar) else 0
    bar_gap = max(0, style.padding) if bar_h else 0
    stack_h = len(display) + bar_gap + bar_h
    left = max(0, (cols - disp_w) // 2)
    top = max(0, (rows - stack_h) // 2)
    ink = _ink_color(style, state)
    frame = Frame.blank(rows, cols)
    for i, line in enumerate(display):
        if 0 <= top + i < rows:
            _blit(frame, left, top + i, line[:cols], ink)
    if bar_h and digit_w and state is not None:
        n, a, r = iv.bar_widths(
            state.fill_normal, state.fill_amber, state.fill_red, digit_w
        )
        y0 = top + len(display) + bar_gap
        colors = (
            [style.clock_color] * n
            + [style.interval_amber_color] * a
            + [style.interval_red_color] * r
        )
        for by in range(bar_h):
            y = y0 + by
            for i, color in enumerate(colors):
                _put(frame, left + i, y, "█", color)
    return frame


def _render_text(
    time_str: str,
    rows: int,
    cols: int,
    style: Style | None = None,
    state: iv.IntervalState | None = None,
) -> Frame:
    style = style or Style()
    frame = Frame.blank(rows, cols)
    ink = _ink_color(style, state)
    bar_h = 1 if (state is not None and style.interval_bar and rows >= 3) else 0
    bar_gap = 1 if bar_h and style.padding else 0
    stack_h = 1 + bar_gap + bar_h
    top = max(0, (rows - stack_h) // 2)
    centered = time_str.center(cols)[:cols].ljust(cols) if cols else ""
    if 0 <= top < rows:
        _blit(frame, 0, top, centered, ink)
    if bar_h and state is not None:
        idx = centered.find(time_str) if time_str and time_str in centered else max(
            0, (cols - len(time_str)) // 2
        )
        n, a, r = iv.bar_widths(
            state.fill_normal, state.fill_amber, state.fill_red, len(time_str)
        )
        colors = (
            [style.clock_color] * n
            + [style.interval_amber_color] * a
            + [style.interval_red_color] * r
        )
        y = top + 1 + bar_gap
        for i, color in enumerate(colors):
            _put(frame, idx + i, y, "█", color)
    return frame


def render_frame(
    time_str: str,
    rows: int,
    cols: int,
    style: Style | None = None,
    suffix: str = "",
    now_s: int | None = None,
) -> Frame:
    """Full frame (characters + per-cell colours)."""
    style = style or Style()
    rows, cols = max(rows, 0), max(cols, 0)
    state = None
    if style.interval_minutes > 0 and now_s is not None:
        state = iv.interval_state(
            now_s,
            style.interval_minutes * 60,
            start_s=style.interval_start_s,
            amber_s=style.interval_amber_s,
            red_s=style.interval_red_s,
        )
    if choose_mode(rows) == "art":
        lay = fit(rows, cols, time_str, style=style, suffix=suffix)
        if lay is not None:
            return render_art(
                time_str, rows, cols, lay, suffix=suffix, style=style, state=state
            )
    return _render_text(_label(time_str, suffix), rows, cols, style=style, state=state)


def render(
    time_str: str,
    rows: int,
    cols: int,
    style: Style | None = None,
    suffix: str = "",
    now_s: int | None = None,
) -> list[str]:
    """Return exactly ``rows`` lines of exactly ``cols`` chars."""
    return render_frame(
        time_str, rows, cols, style=style, suffix=suffix, now_s=now_s
    ).chars
