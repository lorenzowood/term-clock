"""Terminal runtime: paints the clock and stays current until CTRL+C."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from typing import Callable, Sequence, TextIO

from . import core

_ALT_ON = "\x1b[?1049h"
_ALT_OFF = "\x1b[?1049l"
_CURSOR_HIDE = "\x1b[?25l"
_CURSOR_SHOW = "\x1b[?25h"
_WRAP_OFF = "\x1b[?7l"
_WRAP_ON = "\x1b[?7h"
# Home, erase the visible screen, erase the scrollback. A full-width last
# line would otherwise wrap and push every frame into the history.
_CLEAR = "\x1b[H\x1b[2J\x1b[3J"


def _nonneg(value: str) -> int:
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return n


_TOLERANCE_MS = 2.0
_LEAD_MAX_MS = 100.0


def next_second_ms(now_ms: float) -> float:
    """Wall-clock millisecond of the next whole second after ``now_ms``."""
    return (int(now_ms) // 1000 + 1) * 1000.0


def sleep_ms(now_ms: float, target_ms: float, lead_ms: float) -> float:
    """How long to sleep now so we arrive at ``target_ms``, given ``lead_ms``.

    ``lead_ms`` is the estimated sleep overshoot, subtracted from the wait.
    It is never allowed to skip past the boundary.
    """
    remain = target_ms - now_ms
    if remain <= 0:
        return 0.0
    wait = remain - lead_ms
    if wait <= 0:
        wait = remain
    return wait


def adjust_lead_ms(lead_ms: float, error_ms: float) -> float:
    """If we missed the second by more than 2 ms, shift the next sleep."""
    if abs(error_ms) <= _TOLERANCE_MS:
        return lead_ms
    return min(_LEAD_MAX_MS, max(0.0, lead_ms + error_ms))


def _wall_ms() -> float:
    return time.time_ns() / 1_000_000.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="term-clock",
        description="A terminal digital clock that scales to fill the window.",
    )
    p.add_argument(
        "--padding",
        type=_nonneg,
        default=1,
        metavar="N",
        help="blank rows and columns around the clock (default: 1)",
    )
    p.add_argument(
        "--spacing",
        type=_nonneg,
        default=2,
        metavar="N",
        help="blank columns between digits (default: 2)",
    )
    p.add_argument(
        "--hour-format",
        choices=("12", "24"),
        default=None,
        dest="hour_format",
        help="12 or 24 (default: follow the system clock, or 24 if unknown)",
    )
    return p.parse_args(argv)


def frame_for(
    t: time.struct_time,
    cols: int,
    rows: int,
    style: core.Style | None = None,
) -> list[str]:
    """Build the screen buffer for time ``t`` at the given terminal size."""
    style = style or core.Style()
    time_str = core.format_time(
        t.tm_hour, t.tm_min, t.tm_sec, hour_format=style.hour_format
    )
    suffix = core.hour_period(t.tm_hour) if style.hour_format == "12" else ""
    return core.render(time_str, rows=rows, cols=cols, style=style, suffix=suffix)


def _write_diff(out: TextIO, old: Sequence[str], new: Sequence[str]) -> None:
    """Emit cursor-addressed runs for cells that differ."""
    for y, (a, b) in enumerate(zip(old, new)):
        if a == b:
            continue
        width = max(len(a), len(b))
        a = a.ljust(width)
        b = b.ljust(width)
        x = 0
        while x < width:
            if a[x] == b[x]:
                x += 1
                continue
            start = x
            while x < width and a[x] != b[x]:
                x += 1
            out.write(f"\x1b[{y + 1};{start + 1}H{b[start:x]}")


class Painter:
    """Off-screen current/next buffers; only changed cells are written."""

    def __init__(self, out: TextIO) -> None:
        self._out = out
        self._last: list[str] | None = None

    def paint(self, frame: Sequence[str]) -> None:
        frame = list(frame)
        if frame == self._last:
            return
        if self._last is None or len(self._last) != len(frame):
            self._out.write(_CLEAR + "\n".join(frame))
        else:
            _write_diff(self._out, self._last, frame)
        self._last = frame
        self._out.flush()

    def invalidate(self) -> None:
        self._last = None


def run(
    out: TextIO | None = None,
    get_size: Callable[[], tuple[int, int]] | None = None,
    get_time: Callable[[], time.struct_time] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    style: core.Style | None = None,
    now_ms: Callable[[], float] | None = None,
) -> int:
    out = out if out is not None else sys.stdout
    get_size = get_size or (lambda: tuple(shutil.get_terminal_size((80, 24))))
    get_time = get_time or time.localtime
    now_ms = now_ms or _wall_ms

    out.write(_ALT_ON + _CURSOR_HIDE + _WRAP_OFF)
    out.flush()
    painter = Painter(out)
    last_size: tuple[int, int] | None = None
    lead_ms = 0.0

    def paint() -> None:
        nonlocal last_size
        cols, rows = get_size()
        if (cols, rows) != last_size:
            painter.invalidate()
            last_size = (cols, rows)
        painter.paint(frame_for(get_time(), cols=cols, rows=rows, style=style))

    try:
        while True:
            paint()
            target = next_second_ms(now_ms())
            now = now_ms()
            wait = sleep_ms(now, target, lead_ms)
            if wait > 0:
                sleep(wait / 1000.0)
            lead_ms = adjust_lead_ms(lead_ms, now_ms() - target)
    except KeyboardInterrupt:
        return 0
    finally:
        out.write(_WRAP_ON + _CURSOR_SHOW + _ALT_OFF)
        out.flush()


def main(argv: list[str] | None = None) -> int:
    ns = parse_args(argv)
    hour_format = ns.hour_format or core.system_hour_format()
    return run(
        style=core.Style(
            padding=ns.padding,
            spacing=ns.spacing,
            hour_format=hour_format,
        ),
    )
