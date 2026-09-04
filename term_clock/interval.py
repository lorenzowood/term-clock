"""Interval progress: zones, bar fill, and small parsers."""

from __future__ import annotations

from dataclasses import dataclass


def parse_interval_minutes(value: str) -> int:
    """Minutes, or 0 for off. Accepts ``off`` / ``none``."""
    raw = str(value).strip().lower()
    if raw in {"off", "none", "false", "no"}:
        return 0
    n = int(raw)
    if n < 0:
        raise ValueError("interval must be >= 0")
    return n


def parse_hhmm(value: str) -> int:
    """``H:MM`` / ``HH:MM`` / ``HH:MM:SS`` as seconds from midnight."""
    parts = str(value).strip().split(":")
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"bad time: {value}")
    nums = [int(p) for p in parts]
    while len(nums) < 3:
        nums.append(0)
    h, m, s = nums
    if not (0 <= h < 24 and 0 <= m < 60 and 0 <= s < 60):
        raise ValueError(f"time out of range: {value}")
    return h * 3600 + m * 60 + s


def parse_onoff(value: str) -> bool:
    raw = str(value).strip().lower()
    if raw in {"on", "true", "yes", "1"}:
        return True
    if raw in {"off", "false", "no", "0"}:
        return False
    raise ValueError(f"expected on/off, got {value!r}")


def parse_hex_color(value: str) -> str:
    """Return ``#rrggbb`` (lowercase)."""
    raw = str(value).strip()
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) == 3 and all(c in "0123456789abcdefABCDEF" for c in raw):
        raw = "".join(c * 2 for c in raw)
    if len(raw) != 6 or any(c not in "0123456789abcdefABCDEF" for c in raw):
        raise ValueError(f"bad colour: {value}")
    return "#" + raw.lower()


def hex_rgb(color: str) -> tuple[int, int, int]:
    c = parse_hex_color(color)
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def seconds_since_midnight(h: int, m: int, s: int) -> int:
    return h * 3600 + m * 60 + s


@dataclass(frozen=True)
class IntervalState:
    """Where we are in the current interval."""

    zone: str | None  # None, "amber", or "red"
    elapsed_s: int
    length_s: int
    fill_normal: float
    fill_amber: float
    fill_red: float


def interval_state(
    now_s: int,
    length_s: int,
    start_s: int = 0,
    amber_s: int = 300,
    red_s: int = 60,
) -> IntervalState | None:
    """State at ``now_s`` seconds from midnight, or None if intervals are off."""
    if length_s <= 0:
        return None
    elapsed = (now_s - start_s) % length_s
    remaining = length_s - elapsed
    amber_s = min(max(0, amber_s), length_s)
    red_s = min(max(0, red_s), length_s)

    if red_s > 0 and remaining <= red_s:
        zone: str | None = "red"
    elif amber_s > 0 and remaining <= amber_s:
        zone = "amber"
    else:
        zone = None

    normal_dur = max(0, length_s - amber_s)
    amber_dur = max(0, amber_s - red_s)
    n = min(elapsed, normal_dur)
    a = min(max(0, elapsed - normal_dur), amber_dur)
    r = min(max(0, elapsed - normal_dur - amber_dur), red_s)
    L = float(length_s)
    return IntervalState(zone, elapsed, length_s, n / L, a / L, r / L)


def bar_widths(
    fill_normal: float,
    fill_amber: float,
    fill_red: float,
    width: int,
) -> tuple[int, int, int]:
    """Integer segment widths that sum to the filled length of ``width``."""
    if width <= 0:
        return 0, 0, 0
    n = int(fill_normal * width + 1e-9)
    a = int(fill_amber * width + 1e-9)
    r = int(fill_red * width + 1e-9)
    target = int((fill_normal + fill_amber + fill_red) * width + 1e-9)
    leftover = target - (n + a + r)
    if leftover:
        if fill_red > 0 or r:
            r += leftover
        elif fill_amber > 0 or a:
            a += leftover
        else:
            n += leftover
    return n, a, r
