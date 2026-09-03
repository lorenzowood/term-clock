"""Tests for the runtime shell seams (no real terminal needed)."""

import io
import time as _time

from ssh_clock import cli


class TestFrameFor:
    def test_uses_current_time_and_size(self):
        t = _time.struct_time((2026, 9, 3, 12, 34, 56, 0, 0, -1))
        frame = cli.frame_for(t, cols=80, rows=3)
        assert len(frame) == 3
        assert any("12:34:56" in line for line in frame)

    def test_art_for_tall_terminal(self):
        t = _time.struct_time((2026, 9, 3, 1, 2, 3, 0, 0, -1))
        frame = cli.frame_for(t, cols=120, rows=20)
        assert "_" in "\n".join(frame)


class TestPaint:
    def test_only_repaints_on_change(self):
        out = io.StringIO()
        painter = cli.Painter(out)
        painter.paint(["aaa", "bbb"])
        first = out.getvalue()
        assert first  # something was written
        painter.paint(["aaa", "bbb"])
        assert out.getvalue() == first  # unchanged frame -> no new output
        painter.paint(["aaa", "ccc"])
        assert len(out.getvalue()) > len(first)


class TestRunLoop:
    def test_stops_on_keyboard_interrupt_and_restores(self):
        out = io.StringIO()

        def fake_sleep(_):
            raise KeyboardInterrupt

        rc = cli.run(
            out=out,
            get_size=lambda: (80, 24),
            get_time=lambda: _time.localtime(),
            sleep=fake_sleep,
        )
        assert rc == 0
        # alternate screen entered and left, cursor restored
        assert "\x1b[?1049h" in out.getvalue()
        assert "\x1b[?1049l" in out.getvalue()
        assert "\x1b[?25h" in out.getvalue()
