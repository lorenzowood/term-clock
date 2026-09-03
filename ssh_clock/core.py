"""Pure, side-effect-free clock rendering.

Everything here is deterministic and unit-tested. The runtime shell in
``cli.py`` supplies the current time and terminal size and paints the result.

Big digits
----------
The digits use a *segmented-display* vector model in the spirit of Geascript:
seven thick segments with 45-degree chamfered ends that butt together along
their diagonals, so a digit is one connected shape.

The shapes are then rasterised with a **best-fit glyph match**. Every candidate
glyph -- space, the block/eighth/quadrant elements, the four solid triangles
``◤ ◥ ◣ ◢``, and all 60 sextants (2x3 sub-cell resolution) -- carries a 6x6
coverage bitmap. For each character cell we sample the vector model on a 6x6
grid and emit whichever candidate's bitmap is closest. That lets diagonals be
drawn with real diagonal glyphs and thin strokes snap to eighth-blocks, so the
forms stay legible from a few rows tall up to full-screen.
"""

from __future__ import annotations

from functools import lru_cache

BLOCK = "█"

# --- time formatting ------------------------------------------------

def format_time(h: int, m: int, s: int) -> str:
    """Return ``hh:mm:ss`` (zero-padded, 24-hour)."""
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        raise ValueError(f"time out of range: {h}:{m}:{s}")
    return f"{h:02d}:{m:02d}:{s:02d}"


# --- layout decision ----------------------------------------------

TEXT_LINE_LIMIT = 7  # "less than seven lines" -> text; 7 stays text too


def choose_mode(rows: int) -> str:
    """``"art"`` when there is real headroom (>= 8 lines), else ``"text"``."""
    return "art" if rows > TEXT_LINE_LIMIT else "text"


# --- segmented-display vector model ------------------------------
#
# A digit lives in a DW x DH local box; a colon in a COLON_W x DH box.
# Segments are chamfered hexagons that share edges where they meet.

DW = 100.0
DH = 180.0
COLON_W = 34.0
GAP = 7.0

_T = 11.0          # half-thickness of a segment
_CH = 11.0         # chamfer (== _T -> 45 degrees)
_MARGIN = 8.0

_XL = _MARGIN + _T
_XR = DW - _MARGIN - _T
_YT = _MARGIN + _T
_YB = DH - _MARGIN - _T
_YM = DH / 2.0


def _hseg(yc: float):
    return [
        (_XL, yc), (_XL + _CH, yc - _T), (_XR - _CH, yc - _T),
        (_XR, yc), (_XR - _CH, yc + _T), (_XL + _CH, yc + _T),
    ]


def _vseg(xc: float, ya: float, yb: float):
    return [
        (xc, ya), (xc + _T, ya + _CH), (xc + _T, yb - _CH),
        (xc, yb), (xc - _T, yb - _CH), (xc - _T, ya + _CH),
    ]


def _bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), min(ys), max(xs), max(ys))


_SEG_POLY = {
    "a": _hseg(_YT), "g": _hseg(_YM), "d": _hseg(_YB),
    "f": _vseg(_XL, _YT, _YM), "b": _vseg(_XR, _YT, _YM),
    "e": _vseg(_XL, _YM, _YB), "c": _vseg(_XR, _YM, _YB),
}
_SEG = {k: (v, _bbox(v)) for k, v in _SEG_POLY.items()}

_DIGIT_SEGMENTS = {
    0: "abcdef", 1: "bc", 2: "abdeg", 3: "abcdg", 4: "bcfg",
    5: "acdfg", 6: "acdefg", 7: "abc", 8: "abcdefg", 9: "abcdfg",
}

_COLON_CX = COLON_W / 2.0
_COLON_R = 12.0
_COLON_YS = (DH * 0.34, DH * 0.66)


def _octagon(cx: float, cy: float, r: float):
    s = r * 0.4142
    return [
        (cx - r, cy - s), (cx - s, cy - r), (cx + s, cy - r), (cx + r, cy - s),
        (cx + r, cy + s), (cx + s, cy + r), (cx - s, cy + r), (cx - r, cy + s),
    ]


_COLON_POLYS = [
    (p, _bbox(p)) for p in (_octagon(_COLON_CX, y, _COLON_R) for y in _COLON_YS)
]


def _in_convex(x: float, y: float, poly, bbox) -> bool:
    x0, y0, x1, y1 = bbox
    if x < x0 or x > x1 or y < y0 or y > y1:
        return False
    sign = 0
    n = len(poly)
    for i in range(n):
        ax, ay = poly[i]
        bx, by = poly[(i + 1) % n]
        cross = (bx - ax) * (y - ay) - (by - ay) * (x - ax)
        if cross < -1e-9:
            if sign > 0:
                return False
            sign = -1
        elif cross > 1e-9:
            if sign < 0:
                return False
            sign = 1
    return True


def digit_ink(value: int, x: float, y: float) -> bool:
    """Is local point ``(x, y)`` inside digit ``value``'s lit segments?"""
    for name in _DIGIT_SEGMENTS[value]:
        poly, bbox = _SEG[name]
        if _in_convex(x, y, poly, bbox):
            return True
    return False


def colon_ink(x: float, y: float) -> bool:
    """Is local point ``(x, y)`` inside either colon dot?"""
    for poly, bbox in _COLON_POLYS:
        if _in_convex(x, y, poly, bbox):
            return True
    return False


# --- candidate glyph library ------------------------------------
#
# Each candidate has a 6x6 coverage bitmap (bit = row*6 + col). At render time
# we pick the candidate whose bitmap is the closest match (fewest differing
# cells) to the sampled cell.

_SS = 6


def _mask_from_fn(fn) -> int:
    m = 0
    for j in range(_SS):
        for i in range(_SS):
            if fn((i + 0.5) / _SS, (j + 0.5) / _SS):
                m |= 1 << (j * _SS + i)
    return m


def _sextant_codepoint(v: int) -> str:
    off = v - 1
    if v > 21:
        off -= 1
    if v > 42:
        off -= 1
    return chr(0x1FB00 + off)


def _build_candidates():
    cands: list[tuple[str, int]] = []

    def add(ch, fn):
        cands.append((ch, _mask_from_fn(fn)))

    add(" ", lambda x, y: False)
    add("█", lambda x, y: True)
    add("▀", lambda x, y: y < 0.5)
    add("▄", lambda x, y: y >= 0.5)
    add("▌", lambda x, y: x < 0.5)
    add("▐", lambda x, y: x >= 0.5)
    # eighth blocks -- let thin strokes land precisely
    for k in range(1, 8):
        add(chr(0x2580 + k), lambda x, y, k=k: y >= 1 - k / 8)   # ▁..▇
        add(chr(0x2588 + k), lambda x, y, k=k: x < 1 - k / 8)    # ▉..▏
    add("▔", lambda x, y: y < 1 / 8)
    add("▕", lambda x, y: x >= 7 / 8)
    # quadrants
    add("▘", lambda x, y: x < 0.5 and y < 0.5)
    add("▝", lambda x, y: x >= 0.5 and y < 0.5)
    add("▖", lambda x, y: x < 0.5 and y >= 0.5)
    add("▗", lambda x, y: x >= 0.5 and y >= 0.5)
    add("▚", lambda x, y: (x < 0.5) == (y < 0.5))
    add("▞", lambda x, y: (x < 0.5) != (y < 0.5))
    add("▛", lambda x, y: not (x >= 0.5 and y >= 0.5))
    add("▜", lambda x, y: not (x < 0.5 and y >= 0.5))
    add("▙", lambda x, y: not (x >= 0.5 and y < 0.5))
    add("▟", lambda x, y: not (x < 0.5 and y < 0.5))
    # solid triangles -- real diagonals
    add("◤", lambda x, y: x + y <= 1)
    add("◥", lambda x, y: y <= x)
    add("◣", lambda x, y: y >= x)
    add("◢", lambda x, y: x + y >= 1)
    # sextants (2x3)
    for v in range(1, 63):
        if v in (21, 42):
            continue

        def fn(x, y, v=v):
            col = 0 if x < 0.5 else 1
            row = 0 if y < 1 / 3 else (1 if y < 2 / 3 else 2)
            return bool(v & (1 << (row * 2 + col)))

        add(_sextant_codepoint(v), fn)
    return cands


_CANDIDATES = _build_candidates()
_MATCH_CACHE: dict[int, str] = {}


def _match_char(mask: int) -> str:
    hit = _MATCH_CACHE.get(mask)
    if hit is not None:
        return hit
    best, best_d = " ", 99
    for ch, cm in _CANDIDATES:
        d = (mask ^ cm).bit_count()
        if d < best_d:
            best, best_d = ch, d
            if d == 0:
                break
    _MATCH_CACHE[mask] = best
    return best


# --- sizing --------------------------------------------------

MAX_ASPECT = 1.5
_MIN_VH = 13.0   # rendered digit must be at least this tall (visual units)
_MIN_VW = 8.0


def total_local_width(time_str: str) -> float:
    w = 0.0
    for i, ch in enumerate(time_str):
        if i:
            w += GAP
        w += COLON_W if ch == ":" else DW
    return w


def fit_scale(rows: int, cols: int, time_str: str = "12:34:56") -> tuple[float, float] | None:
    """Scale (local units -> visual units) for x and y.

    A character cell is 1 visual unit wide and 2 tall, so the canvas is ``cols``
    x ``2*rows`` visual units. Take the largest uniform scale that fits, then
    let the roomy axis stretch by at most ``MAX_ASPECT`` before stopping (the
    surplus becomes centring margin). ``None`` if it would be too small to read.
    """
    tw = total_local_width(time_str)
    k = min(cols / tw, (2 * rows) / DH)
    if k * DH < _MIN_VH or k * DW < _MIN_VW:
        return None
    kx = min(cols / tw, MAX_ASPECT * k)
    ky = min((2 * rows) / DH, MAX_ASPECT * k)
    return kx, ky


# --- rendering ----------------------------------------------

def _layout(time_str: str):
    x = 0.0
    cells = []
    for i, ch in enumerate(time_str):
        if i:
            x += GAP
        if ch == ":":
            cells.append((True, 0, x, x + COLON_W))
            x += COLON_W
        else:
            cells.append((False, int(ch), x, x + DW))
            x += DW
    return cells


def _any_hit(polys, x: float, y: float) -> bool:
    for poly, bbox in polys:
        if _in_convex(x, y, poly, bbox):
            return True
    return False


def render_art(time_str: str, rows: int, cols: int, kx: float, ky: float) -> list[str]:
    cells = _layout(time_str)
    tw = total_local_width(time_str)
    ox = (cols - kx * tw) / 2.0
    oy = (2 * rows - ky * DH) / 2.0
    inv_kx, inv_ky = 1.0 / kx, 1.0 / ky
    step = 1.0 / _SS

    sx_off = [(i + 0.5) * step for i in range(_SS)]
    sy_off = [(j + 0.5) * (2.0 * step) for j in range(_SS)]
    probe = (0, _SS // 2, _SS - 1)

    # Resolve each output column to the glyph cell under its centre once, and
    # carry that cell's segment polygons + local x offset.
    col_polys: list = [None] * cols
    col_x0: list[float] = [0.0] * cols
    for c in range(cols):
        lxm = (c + 0.5 - ox) * inv_kx
        for is_colon, value, x0, x1 in cells:
            if x0 <= lxm < x1:
                col_polys[c] = (
                    _COLON_POLYS if is_colon
                    else [_SEG[n] for n in _DIGIT_SEGMENTS[value]]
                )
                col_x0[c] = x0
                break

    out = []
    for r in range(rows):
        chars = []
        top = 2 * r
        ly_row = [(top + dy - oy) * inv_ky for dy in sy_off]
        for c in range(cols):
            polys = col_polys[c]
            if polys is None:
                chars.append(" ")
                continue
            x0 = col_x0[c]
            lx_col = [(c + dx - ox) * inv_kx - x0 for dx in sx_off]
            hits = [
                _any_hit(polys, lx_col[i], ly_row[j])
                for i in probe for j in probe
            ]
            if not any(hits):
                chars.append(" ")
                continue
            if all(hits):
                chars.append("█")
                continue
            mask = 0
            bit = 0
            for ly in ly_row:
                if 0.0 <= ly <= DH:
                    for lx in lx_col:
                        if _any_hit(polys, lx, ly):
                            mask |= 1 << bit
                        bit += 1
                else:
                    bit += _SS
            chars.append(" " if mask == 0 else _match_char(mask))
        out.append("".join(chars))
    return out


def _render_text(time_str: str, rows: int, cols: int) -> list[str]:
    grid = [" " * cols for _ in range(rows)]
    row = (rows - 1) // 2 if rows else 0
    if 0 <= row < rows:
        grid[row] = time_str.center(cols)[:cols].ljust(cols)
    return grid


@lru_cache(maxsize=16)
def _render_cached(time_str: str, rows: int, cols: int) -> tuple[str, ...]:
    if choose_mode(rows) == "art":
        scale = fit_scale(rows, cols, time_str)
        if scale is not None:
            return tuple(render_art(time_str, rows, cols, *scale))
    return tuple(_render_text(time_str, rows, cols))


def render(time_str: str, rows: int, cols: int) -> list[str]:
    """Return exactly ``rows`` lines of exactly ``cols`` chars."""
    return list(_render_cached(time_str, max(rows, 0), max(cols, 0)))
