"""Tests for the pure clock core. Written before the implementation (TDD)."""

import pytest

from ssh_clock import core


class TestFormatTime:
    def test_pads_with_zeros(self):
        assert core.format_time(1, 2, 3) == "01:02:03"

    def test_midnight(self):
        assert core.format_time(0, 0, 0) == "00:00:00"

    def test_end_of_day(self):
        assert core.format_time(23, 59, 59) == "23:59:59"

    def test_rejects_out_of_range(self):
        with pytest.raises(ValueError):
            core.format_time(24, 0, 0)
        with pytest.raises(ValueError):
            core.format_time(0, 60, 0)
        with pytest.raises(ValueError):
            core.format_time(0, 0, -1)


class TestChooseMode:
    @pytest.mark.parametrize("rows", [0, 1, 5, 6, 7])
    def test_text_when_seven_or_fewer(self, rows):
        assert core.choose_mode(rows) == "text"

    @pytest.mark.parametrize("rows", [8, 9, 20, 100])
    def test_art_when_eight_or_more(self, rows):
        assert core.choose_mode(rows) == "art"


class TestBestScale:
    def test_none_when_too_small(self):
        # s=1 needs width 12*1+23 = 35 and height 5
        assert core.best_scale(rows=5, cols=34) is None
        assert core.best_scale(rows=4, cols=200) is None

    def test_scale_one_just_fits(self):
        # s=1 -> width 35, height 7
        assert core.best_scale(rows=7, cols=35) == 1

    def test_picks_largest_that_fits(self):
        # width limit: 12s+23 <= 119  -> s <= 8 ; height 4s+3 <= 100 -> s <= 24
        assert core.best_scale(rows=100, cols=119) == 8
        # height limited: 4s+3 <= 23 -> s <= 5
        assert core.best_scale(rows=23, cols=10_000) == 5

    def test_monotonic_geometry(self):
        s = core.best_scale(rows=40, cols=200)
        assert core.block_width(s) <= 200
        assert core.block_height(s) <= 40
        assert core.block_width(s + 1) > 200 or core.block_height(s + 1) > 40


class TestSevenSegmentDigit:
    @pytest.mark.parametrize("d", list(range(10)))
    def test_shape_is_rectangular(self, d):
        rows = core.seven_segment_digit(d, scale=1)
        assert len(rows) == core.block_height(1)
        assert all(len(r) == core.digit_width(1) for r in rows)

    def test_one_has_no_top_segment(self):
        rows = core.seven_segment_digit(1, scale=1)
        assert rows[0].strip() == ""  # segment 'a' absent for '1'

    def test_eight_uses_all_segments(self):
        rows = core.seven_segment_digit(8, scale=2)
        joined = "\n".join(rows)
        assert "_" in joined and "|" in joined
        # every segment lit -> both side columns have verticals somewhere
        assert any(r.startswith("|") for r in rows)
        assert any(r.rstrip().endswith("|") for r in rows)

    def test_zero_has_no_middle_segment(self):
        rows = core.seven_segment_digit(0, scale=1)
        mid = rows[core.block_height(1) // 2]
        assert "_" not in mid

    def test_rejects_bad_digit(self):
        with pytest.raises(ValueError):
            core.seven_segment_digit(10, scale=1)


class TestColon:
    def test_shape(self):
        rows = core.colon_cell(scale=1)
        assert len(rows) == core.block_height(1)
        assert all(len(r) == core.COLON_WIDTH for r in rows)

    def test_has_two_dots(self):
        rows = core.colon_cell(scale=2)
        dot_rows = [i for i, r in enumerate(rows) if r.strip()]
        assert len(dot_rows) == 2
        # roughly at 1/3 and 2/3
        h = len(rows)
        assert dot_rows[0] < h // 2 < dot_rows[1]


class TestRender:
    def test_returns_exact_grid(self):
        grid = core.render("12:34:56", rows=10, cols=80)
        assert len(grid) == 10
        assert all(len(line) == 80 for line in grid)

    def test_text_mode_centres_string(self):
        grid = core.render("12:34:56", rows=3, cols=20)
        non_blank = [i for i, line in enumerate(grid) if line.strip()]
        assert non_blank == [1]  # middle of 3
        assert grid[1].strip() == "12:34:56"
        # horizontally centred: equal-ish padding
        left = len(grid[1]) - len(grid[1].lstrip())
        right = len(grid[1]) - len(grid[1].rstrip())
        assert abs(left - right) <= 1

    def test_text_mode_when_art_would_not_fit(self):
        # 10 rows -> art mode, but only 20 cols -> no scale fits -> text
        grid = core.render("12:34:56", rows=10, cols=20)
        assert "".join(grid).count("_") == 0
        assert any("12:34:56" in line for line in grid)

    def test_art_mode_draws_big_digits(self):
        grid = core.render("12:34:56", rows=20, cols=120)
        blob = "\n".join(grid)
        assert "_" in blob and "|" in blob
        assert "12:34:56" not in blob  # it's art, not literal text

    def test_art_block_is_centred(self):
        grid = core.render("00:00:00", rows=30, cols=150)
        content_rows = [i for i, line in enumerate(grid) if line.strip()]
        top = content_rows[0]
        bottom = len(grid) - 1 - content_rows[-1]
        assert abs(top - bottom) <= 1
