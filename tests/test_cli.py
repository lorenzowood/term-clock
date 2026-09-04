"""Tests for the runtime shell seams (no real terminal needed)."""

import io
import time as _time

import pytest

from term_clock import cli, core


class TestFrameFor:
    def test_uses_current_time_and_size(self):
        t = _time.struct_time((2026, 9, 3, 12, 34, 56, 0, 0, -1))
        frame = cli.frame_for(t, cols=80, rows=3)
        assert len(frame) == 3
        assert any("12:34:56" in line for line in frame)

    def test_art_for_tall_terminal(self):
        t = _time.struct_time((2026, 9, 3, 1, 2, 3, 0, 0, -1))
        frame = cli.frame_for(t, cols=120, rows=20)
        assert core.BLOCK in "\n".join(frame)

    def test_twelve_hour_text_includes_ampm(self):
        t = _time.struct_time((2026, 9, 3, 0, 0, 0, 0, 0, -1))
        frame = cli.frame_for(
            t, cols=80, rows=3, style=core.Style(hour_format="12")
        )
        assert any("12:00:00 AM" in line for line in frame)

    def test_twelve_hour_afternoon(self):
        t = _time.struct_time((2026, 9, 3, 13, 5, 6, 0, 0, -1))
        frame = cli.frame_for(
            t, cols=80, rows=3, style=core.Style(hour_format="12")
        )
        assert any("01:05:06 PM" in line for line in frame)


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

    def test_first_paint_clears_then_draws(self):
        out = io.StringIO()
        painter = cli.Painter(out)
        painter.paint(["aaa", "bbb"])
        assert out.getvalue().startswith("\x1b[H\x1b[2J\x1b[3J")
        assert out.getvalue().endswith("aaa\nbbb")

    def test_later_paint_only_writes_changed_cells(self):
        out = io.StringIO()
        painter = cli.Painter(out)
        painter.paint(["aaa", "bbb"])
        n = len(out.getvalue())
        painter.paint(["aaa", "bbc"])
        delta = out.getvalue()[n:]
        assert "\x1b[2J" not in delta
        assert "\x1b[3J" not in delta
        assert "aaa" not in delta
        # row 2, column 3 (1-based) is the only change: b -> c
        assert "\x1b[2;3H" in delta
        assert delta.endswith("c")

    def test_changed_run_is_written_as_one_span(self):
        out = io.StringIO()
        painter = cli.Painter(out)
        painter.paint(["xxxx"])
        n = len(out.getvalue())
        painter.paint(["xABx"])
        delta = out.getvalue()[n:]
        assert delta.count("\x1b[") == 1
        assert "\x1b[1;2HAB" in delta


class TestArgs:
    def test_defaults(self):
        ns = cli.parse_args([])
        assert ns.padding == 1
        assert ns.spacing == 2
        assert ns.hour_format is None

    def test_flags(self):
        ns = cli.parse_args(
            ["--padding", "3", "--spacing", "5", "--hour-format", "12"]
        )
        assert ns.padding == 3
        assert ns.spacing == 5
        assert ns.hour_format == "12"

    def test_hour_format_24(self):
        ns = cli.parse_args(["--hour-format", "24"])
        assert ns.hour_format == "24"

    def test_rejects_unknown_hour_format(self):
        with pytest.raises(SystemExit):
            cli.parse_args(["--hour-format", "36"])

    def test_no_hz_flag(self):
        with pytest.raises(SystemExit):
            cli.parse_args(["--hz", "25"])


class TestSecondAlign:
    def test_next_second_ms(self):
        assert cli.next_second_ms(0.0) == 1000.0
        assert cli.next_second_ms(1000.0) == 2000.0
        assert cli.next_second_ms(1999.0) == 2000.0

    def test_sleep_is_remainder_minus_lead(self):
        assert cli.sleep_ms(1500.0, target_ms=2000.0, lead_ms=0.0) == 500.0
        assert cli.sleep_ms(1500.0, target_ms=2000.0, lead_ms=12.0) == 488.0

    def test_sleep_does_not_skip_the_boundary(self):
        # 3 ms left, but lead is 10 ms — still wait out those 3 ms
        assert cli.sleep_ms(1997.0, target_ms=2000.0, lead_ms=10.0) == 3.0

    def test_sleep_zero_when_already_there(self):
        assert cli.sleep_ms(2000.0, target_ms=2000.0, lead_ms=0.0) == 0.0
        assert cli.sleep_ms(2005.0, target_ms=2000.0, lead_ms=0.0) == 0.0

    def test_lead_unchanged_within_two_ms(self):
        assert cli.adjust_lead_ms(8.0, error_ms=1.5) == 8.0
        assert cli.adjust_lead_ms(8.0, error_ms=-2.0) == 8.0

    def test_lead_grows_when_late(self):
        assert cli.adjust_lead_ms(8.0, error_ms=5.0) == 13.0

    def test_lead_shrinks_when_early(self):
        assert cli.adjust_lead_ms(8.0, error_ms=-3.0) == 5.0

    def test_lead_is_clamped(self):
        assert cli.adjust_lead_ms(0.0, error_ms=-10.0) == 0.0
        assert cli.adjust_lead_ms(95.0, error_ms=20.0) == 100.0


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
        assert "\x1b[?7l" in out.getvalue()  # wrap off so a full last line cannot scroll
        assert "\x1b[?7h" in out.getvalue()

    def test_run_sleeps_toward_the_next_second(self):
        seen = []

        def fake_sleep(dt):
            seen.append(dt)
            raise KeyboardInterrupt

        cli.run(
            out=io.StringIO(),
            get_size=lambda: (80, 24),
            get_time=lambda: _time.localtime(),
            sleep=fake_sleep,
            now_ms=lambda: 1500.0,
        )
        # 500 ms to the next wall-clock second; resize waits until then
        assert seen == [0.5]
