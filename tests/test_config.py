"""Tests for config-file loading."""

from term_clock import config as cfg


def test_missing_file_is_empty(tmp_path):
    assert cfg.load_config(tmp_path / "nope.conf") == {}


def test_reads_section(tmp_path):
    p = tmp_path / "term-clock.conf"
    p.write_text(
        "[term-clock]\n"
        "padding = 3\n"
        "interval = off\n"
        "interval-start = 9:00\n"
        "interval-amber-color = #d07000\n"
        "interval-bar = on\n",
        encoding="utf-8",
    )
    got = cfg.load_config(p)
    assert got["padding"] == 3
    assert got["interval"] == 0
    assert got["interval_start"] == 9 * 3600
    assert got["interval_amber_color"] == "#d07000"
    assert got["interval_bar"] is True
