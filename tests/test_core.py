"""Tests for the pure clock core."""

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


class TestFont:
    @pytest.mark.parametrize("ch", list("0123456789"))
    def test_digit_is_5x7(self, ch):
        g = core.glyph_pixels(ch)
        assert len(g) == 7
        assert all(len(row) == 5 for row in g)
        assert set("".join(g)) <= {"0", "1"}

    def test_colon_is_2x7(self):
        g = core.glyph_pixels(":")
        assert len(g) == 7
        assert all(len(row) == 2 for row in g)

    def test_colon_has_two_lit_bands(self):
        g = core.glyph_pixels(":")
        lit = [i for i, row in enumerate(g) if "1" in row]
        # two separated groups
        assert lit and 0 not in lit and 6 not in lit
        gaps = [b - a for a, b in zip(lit, lit[1:])]
        assert 2 in gaps or any(x > 1 for x in gaps)

    def test_glyphs_are_not_blank_or_full(self):
        for ch in "0123456789":
            joined = "".join(core.glyph_pixels(ch))
            assert "1" in joined and "0" in joined

    def test_unknown_char_raises(self):
        with pytest.raises(ValueError):
            core.glyph_pixels("A")


class TestGeometry:
    def test_block_pixel_size(self):
        # "12:34:56" = 6 digits*5 + 2 colons*2 + 7 gaps = 30 + 4 + 7 = 41
        assert core.block_pixel_size("12:34:56") == (41, 7)


class TestBestPixelScale:
    def test_none_when_too_small(self):
        assert core.best_pixel_scale(rows=6, cols=200, time_str="12:34:56") is None
        assert core.best_pixel_scale(rows=200, cols=40, time_str="12:34:56") is None

    def test_one_by_one_just_fits(self):
        # needs 41 cols and 7 rows minimum
        assert core.best_pixel_scale(rows=7, cols=41, time_str="12:34:56") == (1, 1)

    def test_fills_height(self):
        pw, ph = core.best_pixel_scale(rows=21, cols=10_000, time_str="12:34:56")
        assert ph == 3  # 21 // 7
        assert 7 * ph <= 21

    def test_fills_width(self):
        pw, ph = core.best_pixel_scale(rows=10_000, cols=82, time_str="12:34:56")
        assert pw == 2  # 82 // 41

    def test_legibility_clamp_keeps_pixels_from_being_tall_and_thin(self):
        # very tall, just wide enough for pw=1 -> ph clamped to 2*pw, no more
        pw, ph = core.best_pixel_scale(rows=700, cols=41, time_str="12:34:56")
        assert pw == 1
        assert ph == 2

    def test_wide_pixels_allowed_up_to_4x(self):
        pw, ph = core.best_pixel_scale(rows=7, cols=100_000, time_str="12:34:56")
        assert ph == 1
        assert pw == 4  # clamped to 4 * ph, not cols // 41


class TestRenderMatrix:
    def test_exact_grid_and_centred(self):
        grid = core.render_matrix("00:00:00", rows=30, cols=150, pw=2, ph=3)
        assert len(grid) == 30
        assert all(len(line) == 150 for line in grid)
        content = [i for i, line in enumerate(grid) if line.strip()]
        top, bottom = content[0], len(grid) - 1 - content[-1]
        assert abs(top - bottom) <= 1
        left = min(len(l) - len(l.lstrip()) for l in grid if l.strip())
        right = min(len(l) - len(l.rstrip()) for l in grid if l.strip())
        assert abs(left - right) <= 2

    def test_pixels_are_scaled_blocks(self):
        # a lit pixel becomes a pw x ph rectangle of block chars
        grid = core.render_matrix("11:11:11", rows=14, cols=200, pw=3, ph=2)
        rows_with_ink = [l for l in grid if core.BLOCK in l]
        # every run of blocks is a multiple of pw wide
        line = next(l for l in rows_with_ink)
        runs = [seg for seg in line.split(" ") if seg]
        assert all(len(r) % 3 == 0 for r in runs)
        # vertical: block rows come in pairs (ph=2)
        assert len(rows_with_ink) % 2 == 0


class TestRender:
    def test_returns_exact_grid(self):
        grid = core.render("12:34:56", rows=10, cols=80)
        assert len(grid) == 10
        assert all(len(line) == 80 for line in grid)

    def test_text_mode_centres_string(self):
        grid = core.render("12:34:56", rows=3, cols=20)
        non_blank = [i for i, line in enumerate(grid) if line.strip()]
        assert non_blank == [1]
        assert grid[1].strip() == "12:34:56"
        left = len(grid[1]) - len(grid[1].lstrip())
        right = len(grid[1]) - len(grid[1].rstrip())
        assert abs(left - right) <= 1

    def test_text_mode_when_art_would_not_fit(self):
        grid = core.render("12:34:56", rows=10, cols=20)
        assert core.BLOCK not in "".join(grid)
        assert any("12:34:56" in line for line in grid)

    def test_art_mode_draws_block_digits(self):
        grid = core.render("12:34:56", rows=20, cols=120)
        blob = "\n".join(grid)
        assert core.BLOCK in blob
        assert "12:34:56" not in blob
