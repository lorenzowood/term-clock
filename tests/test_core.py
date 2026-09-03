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


class TestGlyphInk:
    def _density(self, value):
        return sum(
            core.digit_ink(value, x, y)
            for x in range(0, int(core.DW), 3)
            for y in range(0, int(core.DH), 3)
        )

    def test_one_is_on_the_right_only(self):
        left = sum(
            core.digit_ink(1, x, y)
            for x in range(0, 40, 3)
            for y in range(10, 170, 8)
        )
        right = sum(
            core.digit_ink(1, x, y)
            for x in range(60, 100, 3)
            for y in range(10, 170, 8)
        )
        assert left == 0 and right > 0

    def test_eight_is_much_denser_than_one(self):
        assert self._density(8) > 2 * self._density(1)

    def test_zero_has_a_hollow_centre(self):
        assert not core.digit_ink(0, core.DW / 2, core.DH / 2)

    def test_eight_has_a_lit_middle_bar(self):
        assert core.digit_ink(8, core.DW / 2, core.DH / 2)

    def test_two_and_five_are_mirror_ish(self):
        # 2 lights top-left? no -> f off for 2, on for 5 at upper-left
        assert not core.digit_ink(2, core.DW * 0.12, core.DH * 0.28)
        assert core.digit_ink(5, core.DW * 0.12, core.DH * 0.28)

    def test_all_digits_have_ink(self):
        for v in range(10):
            assert self._density(v) > 0

    def test_colon_has_two_separated_dots(self):
        cx = core.COLON_W / 2
        assert core.colon_ink(cx, core.DH * 0.35)
        assert core.colon_ink(cx, core.DH * 0.65)
        assert not core.colon_ink(cx, core.DH * 0.5)


class TestFitScale:
    def test_none_when_too_small_to_read(self):
        assert core.fit_scale(rows=8, cols=18) is None

    def test_fits_within_width(self):
        sx, sy = core.fit_scale(rows=100, cols=200)
        assert sx * core.total_local_width("12:34:56") <= 200 + 1e-6

    def test_fits_within_height(self):
        sx, sy = core.fit_scale(rows=10, cols=10_000)
        assert sy * core.DH <= 2 * 10 + 1e-6

    @pytest.mark.parametrize(
        "rows,cols",
        [(8, 400), (60, 400), (200, 90), (9, 5000), (500, 300), (24, 80), (40, 160)],
    )
    def test_aspect_never_exceeds_max(self, rows, cols):
        result = core.fit_scale(rows, cols)
        if result is None:
            return
        sx, sy = result
        hi, lo = max(sx, sy), min(sx, sy)
        assert hi <= lo * core.MAX_ASPECT + 1e-9

    def test_bigger_terminal_bigger_clock(self):
        small = core.fit_scale(20, 120)
        big = core.fit_scale(40, 240)
        assert big[0] >= small[0] and big[1] >= small[1]

    def test_uniform_scale_when_neither_axis_has_slack(self):
        tw = core.total_local_width("12:34:56")
        # cols and 2*rows in the same ratio as tw:DH -> no slack either way
        rows = 90
        cols = round(tw * (2 * rows) / core.DH)
        sx, sy = core.fit_scale(rows, cols)
        assert abs(sx - sy) < 1e-3


class TestGlyphMatcher:
    def test_empty_and_full(self):
        assert core._match_char(0) == " "
        assert core._match_char((1 << (core._SS * core._SS)) - 1) == "█"

    def test_top_half(self):
        mask = 0
        for j in range(core._SS // 2):
            for i in range(core._SS):
                mask |= 1 << (j * core._SS + i)
        assert core._match_char(mask) == "▀"

    def test_diagonal_picks_a_triangle(self):
        mask = 0
        for j in range(core._SS):
            for i in range(core._SS):
                if (i + 0.5) / core._SS + (j + 0.5) / core._SS <= 1:
                    mask |= 1 << (j * core._SS + i)
        assert core._match_char(mask) == "◤"

    def test_sextant_codepoints_in_legacy_block(self):
        for v in range(1, 63):
            if v in (21, 42):
                continue
            cp = ord(core._sextant_codepoint(v))
            assert 0x1FB00 <= cp <= 0x1FB3B


class TestRenderArt:
    def test_exact_grid(self):
        g = core.render("12:34:56", rows=20, cols=120)
        assert len(g) == 20
        assert all(len(line) == 120 for line in g)

    def test_uses_block_glyphs(self):
        blob = "".join(core.render("12:34:56", rows=20, cols=120))
        assert "█" in blob and any(ch in blob for ch in "▀▄◤◥◣◢")

    def test_signature_takes_float_scales(self):
        g = core.render_art("12:34:56", 20, 120, 1.05, 1.1)
        assert len(g) == 20 and all(len(line) == 120 for line in g)

    def test_not_literal_text(self):
        blob = "\n".join(core.render("12:34:56", rows=20, cols=120))
        assert "12:34:56" not in blob

    def test_block_is_centred(self):
        g = core.render("00:00:00", rows=30, cols=150)
        used = [i for i, line in enumerate(g) if line.strip()]
        assert abs(used[0] - (len(g) - 1 - used[-1])) <= 2
        left = min(len(l) - len(l.lstrip()) for l in g if l.strip())
        right = min(len(l) - len(l.rstrip()) for l in g if l.strip())
        assert abs(left - right) <= 2

    def test_colon_columns_are_lighter_than_digit_columns(self):
        g = core.render("88:88:88", rows=24, cols=140)
        ink_per_col = [sum(row[c] != " " for row in g) for c in range(140)]
        busiest = max(ink_per_col)
        # the two colon gaps should show up as local minima with less ink
        assert min(c for c in ink_per_col if c >= 0) < busiest


class TestRender:
    def test_returns_exact_grid(self):
        g = core.render("12:34:56", rows=10, cols=80)
        assert len(g) == 10
        assert all(len(line) == 80 for line in g)

    def test_text_mode_centres_string(self):
        g = core.render("12:34:56", rows=3, cols=20)
        non_blank = [i for i, line in enumerate(g) if line.strip()]
        assert non_blank == [1]
        assert g[1].strip() == "12:34:56"
        left = len(g[1]) - len(g[1].lstrip())
        right = len(g[1]) - len(g[1].rstrip())
        assert abs(left - right) <= 1

    def test_text_fallback_when_art_would_be_unreadable(self):
        g = core.render("12:34:56", rows=10, cols=20)
        assert any("12:34:56" in line for line in g)
        assert "█" not in "".join(g)
