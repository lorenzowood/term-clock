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
- **8+ lines**: large digits drawn in a 5x7 block-matrix font. Each "pixel" is
  scaled up to fill the terminal in both directions (kept within a legible
  aspect band). If the window is too small for even the smallest matrix, it
  falls back to the text clock.
- Resizing the terminal is picked up on the next tick.

## Develop

```sh
pip install pytest
pytest
```

Pure rendering logic lives in `ssh_clock/core.py` (fully unit-tested); the
terminal loop and signal handling are in `ssh_clock/cli.py`.

See `DESIGN.md` for the design and the TDD log.
