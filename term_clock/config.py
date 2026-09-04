"""Load ``term-clock.conf`` (XDG config or ``--config-file``)."""

from __future__ import annotations

import os
from configparser import ConfigParser
from pathlib import Path

from . import interval as iv

_SECTION = "term-clock"


def default_config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    root = Path(xdg) if xdg else Path.home() / ".config"
    return root / "term-clock" / "term-clock.conf"


def load_config(path: str | Path | None = None) -> dict:
    """Return typed settings from an INI file. Missing file → empty dict."""
    p = Path(path) if path is not None else default_config_path()
    if not p.is_file():
        return {}
    cp = ConfigParser()
    cp.read(p, encoding="utf-8")
    if _SECTION not in cp:
        return {}
    src = cp[_SECTION]
    out: dict = {}
    _put_float(src, out, "padding", "padding")
    _put_float(src, out, "spacing", "spacing")
    if "hour-format" in src:
        v = src["hour-format"].strip().lower()
        if v in {"12", "24"}:
            out["hour_format"] = v
        elif v in {"system", "auto", ""}:
            out["hour_format"] = None
    if "interval" in src:
        out["interval"] = iv.parse_interval_minutes(src["interval"])
    if "interval-start" in src:
        out["interval_start"] = iv.parse_hhmm(src["interval-start"])
    _put_int(src, out, "interval-amber", "interval_amber")
    _put_int(src, out, "interval-red", "interval_red")
    if "interval-amber-color" in src:
        out["interval_amber_color"] = iv.parse_hex_color(src["interval-amber-color"])
    if "interval-red-color" in src:
        out["interval_red_color"] = iv.parse_hex_color(src["interval-red-color"])
    if "interval-bar" in src:
        out["interval_bar"] = iv.parse_onoff(src["interval-bar"])
    if "clock-color" in src and src["clock-color"].strip():
        out["clock_color"] = iv.parse_hex_color(src["clock-color"])
    if "background-color" in src and src["background-color"].strip():
        out["background_color"] = iv.parse_hex_color(src["background-color"])
    return out


def _put_int(src, out: dict, key: str, dest: str) -> None:
    if key in src:
        n = int(src[key])
        if n < 0:
            raise ValueError(f"{key} must be >= 0")
        out[dest] = n


def _put_float(src, out: dict, key: str, dest: str) -> None:
    if key in src:
        n = float(src[key])
        if n < 0:
            raise ValueError(f"{key} must be >= 0")
        out[dest] = n
