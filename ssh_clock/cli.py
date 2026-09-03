"""Terminal runtime: paints the clock and stays current until CTRL+C."""

from __future__ import annotations

import shutil
import sys
import time
from typing import Callable, Sequence, TextIO

from . import core

_ALT_ON = "\x1b[?1049h"
_ALT_OFF = "\x1b[?1049l"
_CURSOR_HIDE = "\x1b[?25l"
_CURSOR_SHOW = "\x1b[?25h"
_HOME = "\x1b[H"
_CLEAR = "\x1b[2J"


def frame_for(t: time.struct_time, cols: int, rows: int) -> list[str]:
    """Build the screen buffer for time ``t`` at the given terminal size."""
    time_str = core.format_time(t.tm_hour, t.tm_min, t.tm_sec)
    return core.render(time_str, rows=rows, cols=cols)


class Painter:
    """Writes frames to a stream, skipping unchanged repaints."""

    def __init__(self, out: TextIO) -> None:
        self._out = out
        self._last: list[str] | None = None

    def paint(self, frame: Sequence[str]) -> None:
        frame = list(frame)
        if frame == self._last:
            return
        self._last = frame
        self._out.write(_HOME + _CLEAR + "\n".join(frame))
        self._out.flush()

    def invalidate(self) -> None:
        self._last = None


def run(
    out: TextIO | None = None,
    get_size: Callable[[], tuple[int, int]] | None = None,
    get_time: Callable[[], time.struct_time] | None = None,
    sleep: Callable[[float], None] = time.sleep,
    tick: float = 0.1,
) -> int:
    out = out if out is not None else sys.stdout
    get_size = get_size or (lambda: tuple(shutil.get_terminal_size((80, 24))))
    get_time = get_time or time.localtime

    out.write(_ALT_ON + _CURSOR_HIDE)
    out.flush()
    painter = Painter(out)
    last_size: tuple[int, int] | None = None
    try:
        while True:
            cols, rows = get_size()
            if (cols, rows) != last_size:
                painter.invalidate()
                last_size = (cols, rows)
            painter.paint(frame_for(get_time(), cols=cols, rows=rows))
            sleep(tick)
    except KeyboardInterrupt:
        return 0
    finally:
        out.write(_CURSOR_SHOW + _ALT_OFF)
        out.flush()


def main(argv: list[str] | None = None) -> int:
    return run()
