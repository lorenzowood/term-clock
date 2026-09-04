"""Terminal runtime: paints the clock and stays current until CTRL+C."""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from typing import Callable, Sequence, TextIO

from . import config as cfg
from . import core
from . import interval as iv

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


def _nonneg_float(value: str) -> float:
    n = float(value)
    if n < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return n


def _interval(value: str) -> int:
    try:
        return iv.parse_interval_minutes(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def _hhmm(value: str) -> int:
    try:
        return iv.parse_hhmm(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def _onoff(value: str) -> bool:
    try:
        return iv.parse_onoff(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def _hex_color(value: str) -> str:
    try:
        return iv.parse_hex_color(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def _sgr(fg: str | None, bg: str | None) -> str:
    parts: list[str] = []
    if bg:
        r, g, b = iv.hex_rgb(bg)
        parts.append(f"48;2;{r};{g};{b}")
    else:
        parts.append("49")
    if fg:
        r, g, b = iv.hex_rgb(fg)
        parts.append(f"38;2;{r};{g};{b}")
    else:
        parts.append("39")
    return "\x1b[" + ";".join(parts) + "m"


def next_second_ms(now_ms: float) -> float:
    """Wall-clock millisecond of the next whole second after ``now_ms``."""
    return (int(now_ms) // 1000 + 1) * 1000.0


def wait_ms(now_ms: float, target_ms: float) -> float:
    """How long to sleep while waiting for the displayed second to change.

    Remainder until ``target_ms``, or 1 ms if we are already past it so the
    loop cannot busy-spin.
    """
    remain = target_ms - now_ms
    return remain if remain > 0 else 1.0


def _hms(t: time.struct_time) -> tuple[int, int, int]:
    return (t.tm_hour, t.tm_min, t.tm_sec)


def _wall_ms() -> float:
    return time.time_ns() / 1_000_000.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = sys.argv[1:] if argv is None else argv
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--config-file", default=None)
    pre_ns, _ = pre.parse_known_args(argv)
    file_cfg = cfg.load_config(pre_ns.config_file)

    p = argparse.ArgumentParser(
        prog="term-clock",
        description="A terminal digital clock that scales to fill the window.",
    )
    p.add_argument(
        "--config-file",
        default=None,
        metavar="FILE",
        help="settings file (default: ~/.config/term-clock/term-clock.conf)",
    )
    p.add_argument(
        "--padding",
        type=_nonneg_float,
        default=file_cfg.get("padding", 0.125),
        metavar="N",
        help="margin around the clock as a fraction of digit size (default: 0.125; 0 = none)",
    )
    p.add_argument(
        "--spacing",
        type=_nonneg_float,
        default=file_cfg.get("spacing", 0.2),
        metavar="N",
        help="gap between digits as a fraction of digit width (default: 0.2; 0 = none)",
    )
    p.add_argument(
        "--hour-format",
        choices=("12", "24"),
        default=file_cfg.get("hour_format"),
        dest="hour_format",
        help="12 or 24 (default: follow the system clock, or 24 if unknown)",
    )
    p.add_argument(
        "--clock-color",
        type=_hex_color,
        default=file_cfg.get("clock_color"),
        dest="clock_color",
        metavar="HEX",
        help="digit colour as #rrggbb (default: terminal foreground)",
    )
    p.add_argument(
        "--background-color",
        type=_hex_color,
        default=file_cfg.get("background_color"),
        dest="background_color",
        metavar="HEX",
        help="background colour as #rrggbb (default: terminal background)",
    )
    p.add_argument(
        "--interval",
        type=_interval,
        default=file_cfg.get("interval", 15),
        metavar="MINUTES",
        help="interval length in minutes, or off/none to disable (default: 15)",
    )
    p.add_argument(
        "--interval-start",
        type=_hhmm,
        default=file_cfg.get("interval_start", 0),
        dest="interval_start",
        metavar="HH:MM",
        help="time of day intervals are anchored to (default: 0:00)",
    )
    p.add_argument(
        "--interval-amber",
        type=_nonneg,
        default=file_cfg.get("interval_amber", 5),
        dest="interval_amber",
        metavar="MINUTES",
        help="minutes before interval end that count as amber (default: 5)",
    )
    p.add_argument(
        "--interval-red",
        type=_nonneg,
        default=file_cfg.get("interval_red", 1),
        dest="interval_red",
        metavar="MINUTES",
        help="minutes before interval end that count as red (default: 1)",
    )
    p.add_argument(
        "--interval-amber-color",
        type=_hex_color,
        default=file_cfg.get("interval_amber_color", "#f09000"),
        dest="interval_amber_color",
        metavar="HEX",
        help="amber-mode colour (default: #f09000)",
    )
    p.add_argument(
        "--interval-red-color",
        type=_hex_color,
        default=file_cfg.get("interval_red_color", "#ff0000"),
        dest="interval_red_color",
        metavar="HEX",
        help="red-mode colour (default: #ff0000)",
    )
    p.add_argument(
        "--interval-bar",
        type=_onoff,
        default=file_cfg.get("interval_bar", True),
        dest="interval_bar",
        metavar="on/off",
        help="progress bar under the digits (default: on)",
    )
    return p.parse_args(argv)


def style_from_args(ns: argparse.Namespace) -> core.Style:
    hour_format = ns.hour_format or core.system_hour_format()
    return core.Style(
        padding=ns.padding,
        spacing=ns.spacing,
        hour_format=hour_format,
        interval_minutes=ns.interval,
        interval_start_s=ns.interval_start,
        interval_amber_s=ns.interval_amber * 60,
        interval_red_s=ns.interval_red * 60,
        interval_amber_color=ns.interval_amber_color,
        interval_red_color=ns.interval_red_color,
        interval_bar=bool(ns.interval_bar) and ns.interval > 0,
        clock_color=ns.clock_color,
        background_color=ns.background_color,
    )


def frame_for(
    t: time.struct_time,
    cols: int,
    rows: int,
    style: core.Style | None = None,
) -> core.Frame:
    """Build the screen buffer for time ``t`` at the given terminal size."""
    style = style or core.Style()
    time_str = core.format_time(
        t.tm_hour, t.tm_min, t.tm_sec, hour_format=style.hour_format
    )
    suffix = core.hour_period(t.tm_hour) if style.hour_format == "12" else ""
    now_s = iv.seconds_since_midnight(t.tm_hour, t.tm_min, t.tm_sec)
    return core.render_frame(
        time_str,
        rows=rows,
        cols=cols,
        style=style,
        suffix=suffix,
        now_s=now_s,
    )


def _as_frame(frame: core.Frame | Sequence[str]) -> core.Frame:
    if isinstance(frame, core.Frame):
        return frame
    return core.Frame.from_chars(list(frame))


def _has_color(frame: core.Frame) -> bool:
    return any(c is not None for row in frame.fg for c in row)


def _write_diff(
    out: TextIO,
    old: core.Frame,
    new: core.Frame,
    bg: str | None,
) -> None:
    """Emit cursor-addressed runs for cells that differ in glyph or colour."""
    rows = min(len(old.chars), len(new.chars))
    for y in range(rows):
        a, b = old.chars[y], new.chars[y]
        fa, fb = old.fg[y], new.fg[y]
        width = max(len(a), len(b), len(fa), len(fb))
        a = a.ljust(width)
        b = b.ljust(width)
        fa = fa + [None] * (width - len(fa))
        fb = fb + [None] * (width - len(fb))
        x = 0
        while x < width:
            if a[x] == b[x] and fa[x] == fb[x]:
                x += 1
                continue
            start = x
            color = fb[x]
            while (
                x < width
                and not (a[x] == b[x] and fa[x] == fb[x])
                and fb[x] == color
            ):
                x += 1
            out.write(
                f"\x1b[{y + 1};{start + 1}H{_sgr(color, bg)}{b[start:x]}"
            )


def _write_full(out: TextIO, frame: core.Frame, bg: str | None) -> None:
    out.write(_sgr(None, bg) + _CLEAR)
    if not _has_color(frame):
        out.write("\n".join(frame.chars))
        return
    last: str | None = object()  # type: ignore[assignment]
    for y, line in enumerate(frame.chars):
        if y:
            out.write("\n")
        for x, ch in enumerate(line):
            color = frame.fg[y][x] if x < len(frame.fg[y]) else None
            if color != last:
                out.write(_sgr(color, bg))
                last = color
            out.write(ch)


class Painter:
    """Off-screen current/next buffers; only changed cells are written."""

    def __init__(self, out: TextIO, background: str | None = None) -> None:
        self._out = out
        self._bg = background
        self._last: core.Frame | None = None

    def paint(self, frame: core.Frame | Sequence[str]) -> None:
        frame = _as_frame(frame)
        if (
            self._last is not None
            and frame.chars == self._last.chars
            and frame.fg == self._last.fg
        ):
            return
        if (
            self._last is None
            or len(self._last.chars) != len(frame.chars)
        ):
            _write_full(self._out, frame, self._bg)
        else:
            _write_diff(self._out, self._last, frame, self._bg)
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
    painter = Painter(out, background=style.background_color if style else None)
    last_size: tuple[int, int] | None = None
    last_hms: tuple[int, int, int] | None = None

    def paint() -> None:
        nonlocal last_size, last_hms
        cols, rows = get_size()
        if (cols, rows) != last_size:
            painter.invalidate()
            last_size = (cols, rows)
        t = get_time()
        last_hms = _hms(t)
        painter.paint(frame_for(t, cols=cols, rows=rows, style=style))

    try:
        paint()
        while True:
            target = next_second_ms(now_ms())
            while last_hms is not None and _hms(get_time()) == last_hms:
                sleep(wait_ms(now_ms(), target) / 1000.0)
            paint()
    except KeyboardInterrupt:
        return 0
    finally:
        out.write("\x1b[0m" + _WRAP_ON + _CURSOR_SHOW + _ALT_OFF)
        out.flush()


def main(argv: list[str] | None = None) -> int:
    ns = parse_args(argv)
    return run(style=style_from_args(ns))
