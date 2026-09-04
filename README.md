# term-clock

A digital clock for the terminal. It shows `hh:mm:ss`, stays on the wall-clock
second, and grows to fill the window. By default it also tracks 15-minute
blocks: amber in the last five minutes, red in the last minute, with a
progress bar under the digits.

Works over SSH the same way it works locally: alternate screen, no flicker,
CTRL+C returns you to the prompt.

## Install

```sh
pip install term-clock-app
```

Already installed:

```sh
pip install -U term-clock-app
```

The PyPI name is `term-clock-app` because `term-clock` / `termclock` is already taken. The command you run is still `term-clock`.

From a clone:

```sh
pip install -e .
```

Python 3.9 or newer. No runtime dependencies.

## Run

```sh
term-clock
# or
python -m term_clock
```

```sh
term-clock --padding 0.125 --spacing 0.2    # layout defaults
term-clock --hour-format 12
term-clock --interval off                   # plain clock, no interval colours
term-clock --interval 15 --interval-bar on
term-clock --clock-color "#88ccff" --background-color "#101018"
```

Press **CTRL+C** to quit.

## Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--padding N` | `0.125` | Margin around the clock, as a fraction of digit size (rounded up; `0` = none) |
| `--spacing N` | `0.2` | Gap between digits, as a fraction of digit width (rounded up; `0` = none) |
| `--hour-format {12,24}` | system clock, or `24` | 12-hour with AM/PM, or 24-hour |
| `--clock-color HEX` | terminal | Digit colour (`#rrggbb`) |
| `--background-color HEX` | terminal | Background colour |
| `--interval MINUTES` | `15` | Interval length; `off` / `none` disables |
| `--interval-start HH:MM` | `0:00` | Anchor for the interval grid |
| `--interval-amber MINUTES` | `5` | Minutes before the end → amber |
| `--interval-red MINUTES` | `1` | Minutes before the end → red |
| `--interval-amber-color HEX` | `#f09000` | Amber colour |
| `--interval-red-color HEX` | `#ff0000` | Red colour |
| `--interval-bar {on,off}` | `on` | Progress bar under the digits |
| `--config-file FILE` | `~/.config/term-clock/term-clock.conf` | Settings file |

The default hour format follows the environment's time locale
(`LC_TIME` / `T_FMT`) when that can be read. If it cannot, the clock uses 24-hour.

## Intervals

Meetings on 15-minute marks: the clock turns amber in the last 5 minutes of
each block, red in the last minute. The optional bar grows under the digits
from left to right — default colour, then amber, then red — so just before
the boundary you see a full-width bar with a band of amber and a sliver of
red at the end.

`--interval-bar off` hides the bar only; the digits still change colour.
`--interval off` turns intervals off entirely (no colour changes, no bar).

Intervals tile forwards and backwards from `--interval-start` (default
`0:00`), so a 27-minute cycle can still start at `09:00`. With the
defaults, blocks end at `:00`, `:15`, `:30`, and `:45`.

```sh
term-clock --interval 15
term-clock --interval-bar off
term-clock --interval 27 --interval-start 9:00 --interval-amber 5 --interval-red 1
term-clock --interval off
```

## Config file

Flags can live in `~/.config/term-clock/term-clock.conf` (`$XDG_CONFIG_HOME`
if set). CLI flags override the file.

```ini
[term-clock]
padding = 0.125
spacing = 0.2
hour-format = 24
clock-color =
background-color =
interval = 15
interval-start = 0:00
interval-amber = 5
interval-red = 1
interval-amber-color = #f09000
interval-red-color = #ff0000
interval-bar = on
```

## Display

- **7 or fewer lines**: a plain text clock, centred.
- **8+ lines**: large seven-segment digits drawn with full blocks `█` for
  horizontal and vertical bars (square ends), and the four triangles
  `◤ ◥ ◣ ◢` for 45° cuts on outer curves (one column per row — never
  sampled, never an off-angle diagonal). They grow to fill the window
  (each axis stretched by at most 1.5× before the rest becomes centring
  margin). If the window is too small for a readable clock, it falls back
  to the text version.
- **Padding / spacing**: fractions of digit size, rounded up to whole
  cells so a large clock keeps the same proportions as a small one. `0`
  means none.
- **Colons**: two small axis-aligned blocks (no diagonals), centred, spanning
  at most one third of the digit height.
- **12-hour**: AM or PM sits to the right of the digits.
- **Timing**: after each paint the process sleeps until the next wall-clock
  second, then keeps waiting until the displayed `hh:mm:ss` actually changes.
  If that second has already arrived, it paints immediately. A resize is
  picked up on the next second. Unchanged cells are not rewritten.

## Develop

```sh
pip install -e ".[dev]"
pytest
```

Pure rendering lives in `term_clock/core.py` (unit-tested). The terminal loop
is in `term_clock/cli.py`.

See `DESIGN.md` for the design and the TDD log.

## License

MIT. See `LICENSE`.
