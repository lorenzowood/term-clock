"""Tests for the pure clock core."""

import pytest

from ssh_clock import core

_DESIGN_CHARS = set(" █FJLP")
_GLYPHS = set(" █◤◥◣◢")


class TestFormatTime:
    def test_pads_with_zeros(self):
        assert core.format_time(1, 2, 3) == "01:02:03"

    def test_midnight(self):
        assert core.format_time(0, 0, 0) == "00:00:00"

    def test_end_of_day(self):
        assert core.format_time(23, 59, 59) == "23:59:59"

    def test_rejects_out_of_range(self):
        for bad in [(24, 0, 0), (0, 60, 0), (0, 0, -1)]:
            with pytest.raises(ValueError):
                core.format_time(*bad)


class TestChooseMode:
    @pytest.mark.parametrize("rows", [0, 1, 5, 6, 7])
    def test_text_when_seven_or_fewer(self, rows):
        assert core.choose_mode(rows) == "text"

    @pytest.mark.parametrize("rows", [8, 9, 20, 100])
    def test_art_when_eight_or_more(self, rows):
        assert core.choose_mode(rows) == "art"


class TestFont:
    @pytest.fixture(params=range(len(core._FONTS)))
    def font(self, request):
        return core._FONTS[request.param]

    @pytest.mark.parametrize("value", range(10))
    def test_digit_is_wxh_design_chars(self, font, value):
        bmp = font.digits[value]
        assert len(bmp) == font.h
        assert all(len(row) == font.w for row in bmp)
        assert set("".join(bmp)) <= _DESIGN_CHARS

    def test_one_is_narrow_eight_is_dense(self, font):
        def ink(v):
            return sum(c != " " for c in "".join(font.digits[v]))

        assert ink(8) > 2 * ink(1)

    def test_one_uses_only_right_columns(self, font):
        left = font.w // 2
        assert all(row[:left].strip() == "" for row in font.digits[1])

    def test_eight_has_a_middle_bar_zero_does_not(self, font):
        hg = (font.h - font.t) // 2  # row of the middle segment
        assert font.digits[8][hg].count("█") >= font.w - 2
        assert " " in font.digits[0][hg]  # hollow centre

    def test_colon_has_two_dot_bands(self, font):
        lit = [i for i, row in enumerate(font.colon) if row.strip()]
        assert lit and lit[0] != 0 and lit[-1] != font.h - 1
        # a clear vertical gap between the two dots
        assert any(b - a > 1 for a, b in zip(lit, lit[1:]))

    def test_every_convex_corner_becomes_a_triangle(self, font):
        # "0" has four outer corners, all chamfered
        joined = "".join(font.digits[0])
        assert all(joined.count(c) >= 1 for c in "FJLP")


class TestExpand:
    def test_space_and_block(self):
        assert core._expand(" ", 3, 2) == ("   ", "   ")
        assert core._expand("█", 3, 2) == ("███", "███")

    def test_unit_triangle_is_single_glyph(self):
        assert core._expand("F", 1, 1) == ("◤",)
        assert core._expand("J", 1, 1) == ("◢",)

    def test_scaled_triangle_tiles_cleanly(self):
        block = core._expand("F", 4, 4)  # ◤ upper-left
        assert len(block) == 4 and all(len(r) == 4 for r in block)
        chars = set("".join(block))
        assert chars <= {" ", "█", "◤"}
        assert "█" in chars and " " in chars and "◤" in chars
        # top-left corner solid, bottom-right empty
        assert block[0][0] == "█" and block[-1][-1] == " "

    def test_only_ever_emits_space_block_and_its_own_glyph(self):
        for ch, g in core._TRI.items():
            chars = set("".join(core._expand(ch, 5, 3)))
            assert chars <= {" ", "█", g}


class TestFit:
    def test_none_when_tiny(self):
        assert core.fit(rows=8, cols=10) is None

    def test_returns_font_and_positive_scales(self):
        font, nx, ny = core.fit(rows=40, cols=160)
        assert font in core._FONTS
        assert nx >= 1 and ny >= 1

    @pytest.mark.parametrize(
        "rows,cols",
        [(8, 400), (60, 400), (200, 90), (10, 5000), (500, 300), (24, 120), (40, 160)],
    )
    def test_scale_stretch_within_max_aspect(self, rows, cols):
        got = core.fit(rows, cols)
        if got is None:
            return
        _, nx, ny = got
        assert max(nx, ny) <= min(nx, ny) * core.MAX_ASPECT + 1e-9

    def test_uses_small_font_only_when_big_will_not_fit(self):
        big, small = core._FONTS
        # plenty of room -> big
        assert core.fit(50, 300)[0] is big
        # 8 rows -> big (h=10) can't fit, small (h=7) can
        got = core.fit(8, 120)
        assert got is not None and got[0] is small

    def test_bigger_terminal_is_never_smaller(self):
        _, nx1, ny1 = core.fit(20, 120)
        _, nx2, ny2 = core.fit(45, 260)
        assert nx2 >= nx1 and ny2 >= ny1


class TestRenderArt:
    def test_exact_grid(self):
        g = core.render("12:34:56", rows=24, cols=120)
        assert len(g) == 24 and all(len(line) == 120 for line in g)

    def test_only_clean_glyphs(self):
        blob = set("".join(core.render("12:34:56", rows=24, cols=120)))
        assert blob <= _GLYPHS

    def test_uses_blocks_and_triangles(self):
        blob = "".join(core.render("12:34:56", rows=24, cols=140))
        assert "█" in blob and any(t in blob for t in "◤◥◣◢")

    def test_not_literal_text(self):
        blob = "\n".join(core.render("12:34:56", rows=24, cols=120))
        assert "12:34:56" not in blob

    def test_centred(self):
        g = core.render("00:00:00", rows=34, cols=170)
        used = [i for i, line in enumerate(g) if line.strip()]
        assert abs(used[0] - (len(g) - 1 - used[-1])) <= 2
        left = min(len(l) - len(l.lstrip()) for l in g if l.strip())
        right = min(len(l) - len(l.rstrip()) for l in g if l.strip())
        assert abs(left - right) <= 2


class TestRender:
    def test_returns_exact_grid(self):
        g = core.render("12:34:56", rows=10, cols=80)
        assert len(g) == 10 and all(len(line) == 80 for line in g)

    def test_text_mode_centres_string(self):
        g = core.render("12:34:56", rows=3, cols=20)
        non_blank = [i for i, line in enumerate(g) if line.strip()]
        assert non_blank == [1]
        assert g[1].strip() == "12:34:56"

    def test_text_fallback_when_too_narrow(self):
        g = core.render("12:34:56", rows=12, cols=18)
        assert any("12:34:56" in line for line in g)
        assert "█" not in "".join(g)
