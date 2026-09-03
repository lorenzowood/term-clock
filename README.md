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
- **8+ lines**: large segmented-display digits built from a seven-segment
  bitmap font with 45-degree chamfered corners. They are drawn using only the
  full block `█` and the four solid triangles `◤ ◥ ◣ ◢` — glyphs every standard
  terminal font renders with matching metrics — so the digits stay crisp at any
  size. They scale by whole steps to fill the window (each axis stretched by at
  most 1.5x before the rest becomes centring margin). If the window is too
  small for a readable clock, it falls back to the text version.
- Resizing the terminal is picked up on the next tick.

## Develop

```sh
pip install pytest
pytest
```

Pure rendering logic lives in `ssh_clock/core.py` (fully unit-tested); the
terminal loop and signal handling are in `ssh_clock/cli.py`.

See `DESIGN.md` for the design and the TDD log.
