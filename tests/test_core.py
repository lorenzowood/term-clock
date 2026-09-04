"""Tests for the pure clock core."""

import pytest

from term_clock import core

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

    def test_twelve_hour_rolls_midnight_and_noon(self):
        assert core.format_time(0, 0, 0, hour_format="12") == "12:00:00"
        assert core.format_time(12, 0, 0, hour_format="12") == "12:00:00"

    def test_twelve_hour_afternoon(self):
        assert core.format_time(13, 5, 6, hour_format="12") == "01:05:06"
        assert core.format_time(23, 59, 59, hour_format="12") == "11:59:59"

    def test_rejects_unknown_hour_format(self):
        with pytest.raises(ValueError):
            core.format_time(1, 2, 3, hour_format="36")


class TestHourPeriod:
    def test_am_before_noon(self):
        assert core.hour_period(0) == "AM"
        assert core.hour_period(11) == "AM"

    def test_pm_from_noon(self):
        assert core.hour_period(12) == "PM"
        assert core.hour_period(23) == "PM"


class TestSystemHourFormat:
    def test_locale_12(self):
        assert core.system_hour_format(t_fmt="%I:%M:%S %p") == "12"
        assert core.system_hour_format(t_fmt="%r") == "12"

    def test_locale_24(self):
        assert core.system_hour_format(t_fmt="%H:%M:%S") == "24"
        assert core.system_hour_format(t_fmt="%T") == "24"

    def test_empty_or_missing_is_24(self):
        assert core.system_hour_format(t_fmt="") == "24"

    def test_environment_is_12_or_24(self):
        assert core.system_hour_format() in {"12", "24"}


class TestChooseMode:
    @pytest.mark.parametrize("rows", [0, 1, 5, 6, 7])
    def test_text_when_seven_or_fewer(self, rows):
        assert core.choose_mode(rows) == "text"

    @pytest.mark.parametrize("rows", [8, 9, 20, 100])
    def test_art_when_eight_or_more(self, rows):
        assert core.choose_mode(rows) == "art"


class TestGlyph:
    def test_only_clean_glyphs(self):
        for t, hw, vh in [(1, 5, 2), (2, 6, 2), (4, 12, 4)]:
            lay = core.Layout(t=t, hw=hw, vh=vh, gap=1, colon_w=max(2, t))
            for ch in "0123456789:":
                blob = set("".join(core.paint(ch, lay)))
                assert blob <= _GLYPHS

    def test_one_is_narrow_eight_is_dense(self):
        lay = core.Layout(t=2, hw=6, vh=2, gap=1, colon_w=2)

        def ink(ch):
            return sum(c != " " for c in "".join(core.paint(ch, lay)))

        assert ink("8") > 2 * ink("1")

    def test_one_uses_only_right_columns(self):
        lay = core.Layout(t=2, hw=6, vh=2, gap=1, colon_w=2)
        rows = core.paint("1", lay)
        left = len(rows[0]) // 2
        assert all(row[:left].strip() == "" for row in rows)

    def test_eight_has_a_middle_bar_zero_does_not(self):
        lay = core.Layout(t=2, hw=6, vh=2, gap=1, colon_w=2)
        hg = lay.t + lay.vh
        eight = core.paint("8", lay)
        zero = core.paint("0", lay)
        assert eight[hg].count("█") >= lay.digit_w - 2
        assert " " in zero[hg]

    def test_zero_outer_corners_are_triangles(self):
        lay = core.Layout(t=2, hw=6, vh=2, gap=1, colon_w=2)
        joined = "".join(core.paint("0", lay))
        assert all(joined.count(c) >= 1 for c in "◢◣◥◤")

    def test_colon_has_two_dot_bands(self):
        lay = core.Layout(t=2, hw=6, vh=2, gap=2, colon_w=2)
        rows = core.paint(":", lay)
        lit = [i for i, row in enumerate(rows) if row.strip()]
        assert lit and lit[0] != 0 and lit[-1] != lay.digit_h - 1
        assert any(b - a > 1 for a, b in zip(lit, lit[1:]))

    def test_colon_is_blocks_only_no_diagonals(self):
        for t, hw, vh in [(1, 5, 2), (2, 6, 2), (4, 12, 4), (5, 15, 6)]:
            lay = core.Layout(t=t, hw=hw, vh=vh, gap=2, colon_w=core.colon_width(3 * t + 2 * vh))
            blob = set("".join(core.paint(":", lay)))
            assert blob <= {" ", "█"}
            assert "█" in blob

    def test_colon_span_at_most_one_third(self):
        for t, hw, vh in [(2, 6, 2), (4, 12, 4), (5, 15, 6)]:
            h = 3 * t + 2 * vh
            lay = core.Layout(t=t, hw=hw, vh=vh, gap=2, colon_w=core.colon_width(h))
            rows = core.paint(":", lay)
            lit = [i for i, row in enumerate(rows) if row.strip()]
            span = lit[-1] - lit[0] + 1
            cap = max(3, h // 3)
            assert span <= cap

    def test_fortyfive_cut_is_square_stair(self):
        # t=4, cut=2: top-left of "0" is a 1:1 ◢ stair (one col per row).
        lay = core.Layout(t=4, hw=12, vh=4, gap=2, colon_w=4)
        rows = core.paint("0", lay)
        assert rows[0][0] == " " and rows[0][1] == "◢"
        assert rows[1][0] == "◢"

    def test_two_has_square_horizontal_ends_but_keeps_curves(self):
        lay = core.Layout(t=4, hw=12, vh=4, gap=2, colon_w=4)
        rows = core.paint("2", lay)
        # left end of A (F off) is a termination — square
        assert rows[0][0] == "█"
        assert rows[3][0] == "█"
        # right end of D (C off) is a termination — square
        assert rows[-1][-1] == "█"
        # A–B top-right and D–E bottom-left stay as external curves
        assert "◣" in "".join(rows[:3])
        assert "◥" in "".join(rows[-3:])

    def test_four_has_square_vertical_ends(self):
        lay = core.Layout(t=4, hw=12, vh=4, gap=2, colon_w=4)
        rows = core.paint("4", lay)
        w = lay.digit_w
        assert rows[0] == "█" * lay.t + " " * (w - 2 * lay.t) + "█" * lay.t
        assert rows[-1] == " " * (w - lay.t) + "█" * lay.t
        # F–G left elbow is still an external curve
        blob = "".join(rows)
        assert "◥" in blob

    def test_one_has_square_ends(self):
        lay = core.Layout(t=4, hw=12, vh=4, gap=2, colon_w=4)
        rows = core.paint("1", lay)
        assert rows[0].strip() == "█" * lay.t
        assert rows[-1].strip() == "█" * lay.t
        assert set("".join(rows)) <= {" ", "█"}

    def test_no_adjacent_same_triangles(self):
        lay = core.Layout(t=4, hw=12, vh=4, gap=2, colon_w=4)
        for ch in "0123456789":
            for row in core.paint(ch, lay):
                for t in "◤◥◣◢":
                    assert t + t not in row


class TestStyle:
    def test_defaults(self):
        s = core.Style()
        assert s.padding == 1
        assert s.spacing == 2
        assert s.hour_format == "24"

    def test_fit_uses_default_spacing(self):
        lay = core.fit(rows=24, cols=120)
        assert lay is not None
        assert lay.gap == 2

    def test_fit_honours_custom_spacing(self):
        lay = core.fit(rows=24, cols=160, style=core.Style(spacing=4))
        assert lay is not None
        assert lay.gap == 4

    def test_padding_leaves_a_blank_frame(self):
        g = core.render("12:34:56", rows=24, cols=120, style=core.Style(padding=2))
        assert all(line.strip() == "" for line in g[:2])
        assert all(line.strip() == "" for line in g[-2:])
        assert all(line[:2].strip() == "" and line[-2:].strip() == "" for line in g)


class TestFit:
    def test_none_when_tiny(self):
        assert core.fit(rows=8, cols=10) is None

    def test_returns_positive_thickness(self):
        lay = core.fit(rows=40, cols=160)
        assert lay is not None
        assert lay.t >= 1 and lay.hw >= 1 and lay.vh >= 1

    @pytest.mark.parametrize(
        "rows,cols",
        [(8, 400), (60, 400), (200, 90), (10, 5000), (500, 300), (24, 120), (40, 160)],
    )
    def test_scale_stretch_within_max_aspect(self, rows, cols):
        lay = core.fit(rows, cols)
        if lay is None:
            return
        box = 5 * lay.t
        assert lay.digit_w <= box * core.MAX_ASPECT + 1e-9
        assert lay.digit_h <= box * core.MAX_ASPECT + 1e-9

    def test_eight_rows_gets_art(self):
        lay = core.fit(8, 120)
        assert lay is not None
        assert lay.digit_h <= 8

    def test_bigger_terminal_is_never_smaller(self):
        a = core.fit(20, 120)
        b = core.fit(45, 260)
        assert a and b
        assert b.t >= a.t
        assert b.digit_w >= a.digit_w and b.digit_h >= a.digit_h


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

    def test_twelve_hour_places_ampm_to_the_right(self):
        g = core.render("01:02:03", rows=24, cols=140, suffix="AM")
        used = [line for line in g if line.strip()]
        assert any("AM" in line for line in used)
        row = next(line for line in used if "AM" in line)
        ink = row.rstrip()
        assert ink.endswith("AM")
        assert "█" in ink[: ink.index("AM")]

    def test_centred(self):
        g = core.render("00:00:00", rows=34, cols=170)
        used = [i for i, line in enumerate(g) if line.strip()]
        assert abs(used[0] - (len(g) - 1 - used[-1])) <= 2
        left = min(len(l) - len(l.lstrip()) for l in g if l.strip())
        right = min(len(l) - len(l.rstrip()) for l in g if l.strip())
        assert abs(left - right) <= 2
        # default padding is one cell on every side
        assert used[0] >= 1 and used[-1] <= 32
        assert left >= 1 and right >= 1

    @pytest.mark.parametrize(
        "rows,cols",
        [(24, 80), (24, 160), (40, 160), (50, 200), (60, 240), (20, 300)],
    )
    def test_no_doubled_triangles_in_frame(self, rows, cols):
        for line in core.render("12:34:56", rows=rows, cols=cols):
            for t in "◤◥◣◢":
                assert t + t not in line


class TestRender:
    def test_returns_exact_grid(self):
        g = core.render("12:34:56", rows=10, cols=80)
        assert len(g) == 10 and all(len(line) == 80 for line in g)

    def test_text_mode_centres_string(self):
        g = core.render("12:34:56", rows=3, cols=20)
        non_blank = [i for i, line in enumerate(g) if line.strip()]
        assert non_blank == [1]
        assert g[1].strip() == "12:34:56"

    def test_text_mode_includes_ampm(self):
        g = core.render("01:02:03", rows=3, cols=20, suffix="AM")
        assert g[1].strip() == "01:02:03 AM"

    def test_text_fallback_when_too_narrow(self):
        g = core.render("12:34:56", rows=12, cols=18)
        assert any("12:34:56" in line for line in g)
        assert "█" not in "".join(g)


class TestIntervalBar:
    def _style(self, **kw):
        return core.Style(
            interval_minutes=15,
            interval_bar=True,
            interval_amber_s=5 * 60,
            interval_red_s=60,
            **kw,
        )

    def test_bar_sits_below_digits(self):
        # 14 min into a 15-min block: almost full bar, in red zone
        g = core.render(
            "12:14:00",
            rows=24,
            cols=140,
            style=self._style(),
            now_s=12 * 3600 + 14 * 60,
        )
        used = [i for i, line in enumerate(g) if line.strip()]
        assert used
        # last used row is the bar, not a digit (digits have mixed gaps)
        bar = g[used[-1]]
        assert "█" in bar
        # bar is narrower than the full frame and inset from the edges
        assert bar.strip() != bar
        assert len(bar.strip()) < 140

    def test_bar_grows_with_elapsed_time(self):
        early = "".join(
            core.render(
                "12:01:00",
                rows=24,
                cols=140,
                style=self._style(),
                now_s=12 * 3600 + 60,
            )
        ).count("█")
        late = "".join(
            core.render(
                "12:14:00",
                rows=24,
                cols=140,
                style=self._style(),
                now_s=12 * 3600 + 14 * 60,
            )
        ).count("█")
        assert late > early

    def test_no_bar_when_interval_off(self):
        coloured = core.render_frame(
            "12:14:00",
            rows=24,
            cols=140,
            style=self._style(),
            now_s=12 * 3600 + 14 * 60,
        )
        assert any(c == "#ff0000" for row in coloured.fg for c in row)
        plain = core.render_frame("12:14:00", rows=24, cols=140, now_s=12 * 3600 + 14 * 60)
        assert all(c is None for row in plain.fg for c in row)
