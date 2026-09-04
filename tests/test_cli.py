"""Tests for the runtime shell seams (no real terminal needed)."""

import io
import time as _time

import pytest

from term_clock import cli, config as cfg, core


@pytest.fixture(autouse=True)
def _no_user_config(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg, "default_config_path", lambda: tmp_path / "missing.conf")


class TestFrameFor:
    def test_uses_current_time_and_size(self):
        t = _time.struct_time((2026, 9, 3, 12, 34, 56, 0, 0, -1))
        frame = cli.frame_for(t, cols=80, rows=3)
        assert len(frame.chars) == 3
        assert any("12:34:56" in line for line in frame.chars)

    def test_art_for_tall_terminal(self):
        t = _time.struct_time((2026, 9, 3, 1, 2, 3, 0, 0, -1))
        frame = cli.frame_for(t, cols=120, rows=20)
        assert core.BLOCK in "\n".join(frame.chars)

    def test_twelve_hour_text_includes_ampm(self):
        t = _time.struct_time((2026, 9, 3, 0, 0, 0, 0, 0, -1))
        frame = cli.frame_for(
            t, cols=80, rows=3, style=core.Style(hour_format="12")
        )
        assert any("12:00:00 AM" in line for line in frame.chars)

    def test_twelve_hour_afternoon(self):
        t = _time.struct_time((2026, 9, 3, 13, 5, 6, 0, 0, -1))
        frame = cli.frame_for(
            t, cols=80, rows=3, style=core.Style(hour_format="12")
        )
        assert any("01:05:06 PM" in line for line in frame.chars)


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
        raw = out.getvalue()
        assert "\x1b[H\x1b[2J\x1b[3J" in raw
        assert raw.endswith("aaa\nbbb")

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
        assert "\x1b[1;2H" in delta
        assert "AB" in delta
        assert delta.count("\x1b[1;") == 1

    def test_default_color_resets_after_red(self):
        out = io.StringIO()
        painter = cli.Painter(out)
        painter.paint(core.Frame.from_chars(["██"], ink="#ff0000"))
        n = len(out.getvalue())
        painter.paint(core.Frame.from_chars(["██"]))
        delta = out.getvalue()[n:]
        assert "39" in delta

    def test_color_change_without_glyph_change_is_written(self):
        out = io.StringIO()
        painter = cli.Painter(out)
        a = core.Frame.from_chars(["██"], ink="#ffffff")
        painter.paint(a)
        n = len(out.getvalue())
        b = core.Frame.from_chars(["██"], ink="#ff0000")
        painter.paint(b)
        delta = out.getvalue()[n:]
        assert "\x1b[" in delta
        assert "255;0;0" in delta


class TestArgs:
    def test_defaults(self):
        ns = cli.parse_args([])
        assert ns.padding == 0.125
        assert ns.spacing == 0.2
        assert ns.hour_format is None
        assert ns.interval == 15
        assert ns.interval_start == 0
        assert ns.interval_amber == 5
        assert ns.interval_red == 1
        assert ns.interval_amber_color == "#f09000"
        assert ns.interval_red_color == "#ff0000"
        assert ns.interval_bar is True
        assert ns.clock_color is None

    def test_flags(self):
        ns = cli.parse_args(
            ["--padding", "0.25", "--spacing", "0.5", "--hour-format", "12"]
        )
        assert ns.padding == 0.25
        assert ns.spacing == 0.5
        assert ns.hour_format == "12"

    def test_padding_zero(self):
        ns = cli.parse_args(["--padding", "0", "--spacing", "0"])
        assert ns.padding == 0
        assert ns.spacing == 0

    def test_hour_format_24(self):
        ns = cli.parse_args(["--hour-format", "24"])
        assert ns.hour_format == "24"

    def test_rejects_unknown_hour_format(self):
        with pytest.raises(SystemExit):
            cli.parse_args(["--hour-format", "36"])

    def test_interval_off(self):
        ns = cli.parse_args(["--interval", "off"])
        assert ns.interval == 0
        st = cli.style_from_args(ns)
        assert st.interval_minutes == 0
        assert st.interval_bar is False

    def test_interval_bar_off(self):
        ns = cli.parse_args(["--interval-bar", "off"])
        assert ns.interval_bar is False

    def test_config_file(self, tmp_path):
        p = tmp_path / "term-clock.conf"
        p.write_text(
            "[term-clock]\n"
            "interval = 27\n"
            "interval-start = 9:00\n"
            "interval-bar = off\n"
            "clock-color = #abc123\n",
            encoding="utf-8",
        )
        ns = cli.parse_args(["--config-file", str(p)])
        assert ns.interval == 27
        assert ns.interval_start == 9 * 3600
        assert ns.interval_bar is False
        assert ns.clock_color == "#abc123"

    def test_cli_overrides_config(self, tmp_path):
        p = tmp_path / "term-clock.conf"
        p.write_text("[term-clock]\ninterval = 27\n", encoding="utf-8")
        ns = cli.parse_args(["--config-file", str(p), "--interval", "10"])
        assert ns.interval == 10


class TestSecondAlign:
    def test_next_second_ms(self):
        assert cli.next_second_ms(0.0) == 1000.0
        assert cli.next_second_ms(1000.0) == 2000.0
        assert cli.next_second_ms(1999.0) == 2000.0

    def test_wait_is_remainder_until_the_boundary(self):
        assert cli.wait_ms(1500.0, target_ms=2000.0) == 500.0
        assert cli.wait_ms(1997.0, target_ms=2000.0) == 3.0

    def test_wait_is_one_ms_when_already_past_target(self):
        # still on the old displayed second, so do not busy-spin
        assert cli.wait_ms(2000.0, target_ms=2000.0) == 1.0
        assert cli.wait_ms(2005.0, target_ms=2000.0) == 1.0


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
        # 500 ms to the next wall-clock second
        assert seen == [0.5]

    def test_paints_the_new_second_instead_of_sleeping_past_it(self):
        # First paint sampled second 5; by the wait check we are already in 6.
        secs = [5, 6, 6, 6]
        seen = []

        def get_time():
            s = secs.pop(0) if secs else 6
            return _time.struct_time((2026, 9, 4, 12, 0, s, 0, 0, -1))

        def fake_sleep(dt):
            seen.append(dt)
            raise KeyboardInterrupt

        cli.run(
            out=io.StringIO(),
            get_size=lambda: (80, 24),
            get_time=get_time,
            sleep=fake_sleep,
            now_ms=lambda: 6100.0,
        )
        # Caught up to second 6 immediately; then wait for 7 (900 ms).
        assert seen == [0.9]

    def test_sleeps_one_ms_if_past_the_boundary_but_second_unchanged(self):
        t = _time.struct_time((2026, 9, 4, 12, 0, 5, 0, 0, -1))
        nows = [1500.0, 2100.0]
        seen = []

        def now_ms():
            return nows.pop(0) if nows else 2100.0

        def fake_sleep(dt):
            seen.append(dt)
            raise KeyboardInterrupt

        cli.run(
            out=io.StringIO(),
            get_size=lambda: (80, 24),
            get_time=lambda: t,
            sleep=fake_sleep,
            now_ms=now_ms,
        )
        assert seen == [0.001]
