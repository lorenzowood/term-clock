"""Tests for interval progress maths."""

import pytest

from term_clock import interval as iv


class TestParsers:
    def test_interval_minutes_off(self):
        assert iv.parse_interval_minutes("off") == 0
        assert iv.parse_interval_minutes("none") == 0

    def test_interval_minutes_number(self):
        assert iv.parse_interval_minutes("15") == 15
        assert iv.parse_interval_minutes("27") == 27

    def test_hhmm(self):
        assert iv.parse_hhmm("0:00") == 0
        assert iv.parse_hhmm("09:00") == 9 * 3600
        assert iv.parse_hhmm("9:00") == 9 * 3600

    def test_onoff(self):
        assert iv.parse_onoff("on") is True
        assert iv.parse_onoff("off") is False

    def test_hex_color(self):
        assert iv.parse_hex_color("#d07000") == "#d07000"
        assert iv.parse_hex_color("FF0000") == "#ff0000"
        assert iv.parse_hex_color("#f00") == "#ff0000"

    def test_hex_rejects_garbage(self):
        with pytest.raises(ValueError):
            iv.parse_hex_color("blue")


class TestIntervalState:
    def test_off(self):
        assert iv.interval_state(100, length_s=0) is None

    def test_quarter_hour_boundary_is_a_fresh_block(self):
        L = 15 * 60
        end = iv.interval_state(8 * 3600 + 14 * 60 + 59, length_s=L, amber_s=5 * 60, red_s=60)
        start = iv.interval_state(8 * 3600 + 15 * 60, length_s=L, amber_s=5 * 60, red_s=60)
        assert end.zone == "red"
        assert start.zone is None
        assert start.elapsed_s == 0
        assert start.fill_normal == 0
        assert start.fill_red == 0

    def test_just_before_amber(self):
        # 15-min block, amber at 5 min remaining → elapsed 10 min
        st = iv.interval_state(10 * 60 - 1, length_s=15 * 60, amber_s=5 * 60, red_s=60)
        assert st.zone is None

    def test_amber_zone(self):
        st = iv.interval_state(10 * 60, length_s=15 * 60, amber_s=5 * 60, red_s=60)
        assert st.zone == "amber"

    def test_red_zone(self):
        st = iv.interval_state(14 * 60, length_s=15 * 60, amber_s=5 * 60, red_s=60)
        assert st.zone == "red"

    def test_red_overrides_amber(self):
        st = iv.interval_state(14 * 60 + 30, length_s=15 * 60, amber_s=5 * 60, red_s=60)
        assert st.zone == "red"

    def test_offset_start(self):
        # 27-min blocks from 09:00; 09:26 is 1 min before the end
        start = 9 * 3600
        now = 9 * 3600 + 26 * 60
        st = iv.interval_state(now, length_s=27 * 60, start_s=start, amber_s=5 * 60, red_s=60)
        assert st.elapsed_s == 26 * 60
        assert st.zone == "red"

    def test_wraps_backwards_from_start(self):
        # 15-min from 09:00; 08:50 is 5 min into the 08:45 block
        start = 9 * 3600
        now = 8 * 3600 + 50 * 60
        st = iv.interval_state(now, length_s=15 * 60, start_s=start, amber_s=5 * 60, red_s=60)
        assert st.elapsed_s == 5 * 60
        assert st.zone is None

    def test_bar_fills_normal_then_amber_then_red(self):
        L = 15 * 60
        # 12 min in: 10 min normal + 2 min amber
        st = iv.interval_state(12 * 60, length_s=L, amber_s=5 * 60, red_s=60)
        assert st.fill_normal == pytest.approx(10 / 15)
        assert st.fill_amber == pytest.approx(2 / 15)
        assert st.fill_red == 0
        # 14.5 min in
        st = iv.interval_state(14 * 60 + 30, length_s=L, amber_s=5 * 60, red_s=60)
        assert st.fill_normal == pytest.approx(10 / 15)
        assert st.fill_amber == pytest.approx(4 / 15)
        assert st.fill_red == pytest.approx(0.5 / 15)


class TestBarWidths:
    def test_empty(self):
        assert iv.bar_widths(0, 0, 0, 100) == (0, 0, 0)

    def test_full_three_tone(self):
        # 10/15 + 4/15 + 1/15 of 90
        n, a, r = iv.bar_widths(10 / 15, 4 / 15, 1 / 15, 90)
        assert n + a + r == 90
        assert n == 60 and a == 24 and r == 6
