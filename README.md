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
- **8+ lines**: large seven-segment digits, scaled to the largest size that
  fits width and height while keeping the digit aspect ratio. If the window is
  too narrow for even the smallest art, it falls back to the text clock.
- Resizing the terminal is picked up on the next tick.

## Develop

```sh
pip install pytest
pytest
```

Pure rendering logic lives in `ssh_clock/core.py` (fully unit-tested); the
terminal loop and signal handling are in `ssh_clock/cli.py`.

See `DESIGN.md` for the design and the TDD log.
