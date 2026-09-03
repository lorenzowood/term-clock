# ssh-clock

A digital clock for the terminal / SSH sessions. Shows `hh:mm:ss` and keeps it
current, using as much of the window as it can.

## Run

```sh
python -m ssh_clock
# or, after `pip install -e .`
ssh-clock
```

Press **CTRL+C** to quit back to the shell.

## Behaviour

- **7 or fewer lines**: a plain text clock, centred.
- **8+ lines**: large segmented-display digits (Geascript-style), drawn from a
  vector model and rasterised with Unicode block, triangle and sextant
  characters so the diagonal chamfers render cleanly. They scale to fill the
  window; the digits' aspect ratio is kept within 1.5x before it stops
  stretching and centres in the extra space. If the window is too small for a
  readable clock, it falls back to the text version.

  Best results need a terminal font with the "Symbols for Legacy Computing"
  block (sextants `U+1FB00`+) -- most current ones (Cascadia, JetBrains Mono,
  Iosevka, recent Menlo/SF Mono) have it.
- Resizing the terminal is picked up on the next tick.

## Develop

```sh
pip install pytest
pytest
```

Pure rendering logic lives in `ssh_clock/core.py` (fully unit-tested); the
terminal loop and signal handling are in `ssh_clock/cli.py`.

See `DESIGN.md` for the design and the TDD log.
