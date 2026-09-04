# term-clock

A digital clock for the terminal. It shows `hh:mm:ss`, stays on the wall-clock
second, and grows to fill the window.

Works over SSH the same way it works locally: alternate screen, no flicker,
CTRL+C returns you to the prompt.

## Install

```sh
pip install term-clock-app
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
term-clock --padding 1 --spacing 2          # defaults
term-clock --padding 2 --spacing 4
term-clock --hour-format 12
term-clock --hour-format 24
```

Press **CTRL+C** to quit.

## Options

| Flag | Default | Meaning |
| --- | --- | --- |
| `--padding N` | `1` | Blank rows and columns on every side |
| `--spacing N` | `2` | Blank columns between digits |
| `--hour-format {12,24}` | system clock, or `24` | 12-hour with AM/PM, or 24-hour |

The default hour format follows the environment's time locale
(`LC_TIME` / `T_FMT`) when that can be read. If it cannot, the clock uses 24-hour.

## Display

- **7 or fewer lines**: a plain text clock, centred.
- **8+ lines**: large seven-segment digits drawn with full blocks `█` for
  horizontal and vertical bars, and the four triangles `◤ ◥ ◣ ◢` for 45°
  corner cuts (one column per row — never sampled, never an off-angle
  diagonal). They grow to fill the window (each axis stretched by at most
  1.5× before the rest becomes centring margin). If the window is too small
  for a readable clock, it falls back to the text version.
- **Colons**: two small axis-aligned blocks (no diagonals), centred, spanning
  at most one third of the digit height.
- **12-hour**: AM or PM sits to the right of the digits.
- **Timing**: after each flip the process sleeps until the next wall-clock
  second, then measures how late or early it woke (target: within 2 ms) and
  shortens or lengthens the following sleep. A resize is picked up on the
  next second. Unchanged cells are not rewritten.

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
