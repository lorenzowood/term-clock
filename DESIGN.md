# SSH Clock — Design & Development Log

A running record of the design process, kept as work proceeds (per the brief's
requirement to document the process and to use strict TDD).

## 1. Goal

A terminal clock, usable over SSH, showing `hh:mm:ss` and staying current.

- Uses the available terminal space, as big as possible.
- < 7 lines available → plain text clock, centred vertically and horizontally.
- > 7 lines available → large digits drawn as ASCII art.
- Digits should fill the available area as far as possible while keeping their
  aspect ratio.
- CTRL+C exits cleanly back to the shell prompt.

## 2. Language & tools

- Python 3.11 (available on the target machine), standard library only for the
  runtime (`os`, `time`, `sys`, `signal`, `shutil`).
- `pytest` for tests.
- Rationale: zero-dependency install is the friendliest thing for "run it over
  SSH on some box".

## 3. Architecture

Split into a **pure core** (easy to unit-test) and a **thin runtime shell**.

```
ssh_clock/
  core.py     # pure functions: formatting, layout maths, art rendering
  cli.py      # terminal loop, signal handling, screen control
  __main__.py # entry point -> cli.main()
tests/
  test_core.py
```

### Pure core pieces

1. `format_time(h, m, s) -> "hh:mm:ss"` — zero-padded, 24-hour.
2. `choose_mode(rows) -> "text" | "art"` — the 7-line rule.
   - Decision: "less than seven" = `rows < 7` → text; "more than seven" =
     `rows > 7` → art. Exactly 7 is not covered by the brief; we treat 7 as
     text (safer — art needs headroom). So: `art` iff `rows >= 8`.
3. Seven-segment art. Each digit is drawn from the 7 segments (a–g) at a given
   scale `s` (s >= 1):
   - horizontal segment width `hw = 2s`, vertical segment height `vh = s`
   - digit cell: width `2s + 2`, height `2s + 3`
   - colon cell: width `2`, height `2s + 3` (two dots at 1/3 and 2/3)
   - one space gap between cells
   - Chosen style: 7-segment (`_` and `|`).
4. `best_scale(rows, cols) -> int | None` — largest `s` such that the whole
   `hh:mm:ss` block fits in `rows x cols`. `None` if even `s = 1` doesn't fit
   (caller then falls back to text mode).
   - block width  `W(s) = 6*(2s+2) + 2*2 + 7 = 12s + 23`
   - block height `H(s) = 2s + 3`
   - This discrete scaling is how we "fill as far as possible while retaining
     aspect ratio": the cell geometry fixes the ratio, `s` is the only knob.
5. `render(time_str, rows, cols) -> list[str]` — returns exactly `rows` lines,
   each exactly `cols` chars, with the clock centred. Uses art if `choose_mode`
   says so *and* a scale fits; otherwise centred text.

### Runtime shell (`cli.py`)

- Alternate screen buffer (`\x1b[?1049h` / `\x1b[?1049l`), hide/show cursor.
- Loop: read `shutil.get_terminal_size()` each tick (handles resize), render,
  repaint if the frame changed. Sleep ~0.1s.
- `KeyboardInterrupt` (CTRL+C) → restore screen + cursor, `return 0`.

## 4. TDD log

Entries appended as each red/green step happens.

### Step 1 — core: formatting, layout, art (RED)

Wrote `tests/test_core.py` covering `format_time`, `choose_mode`, `best_scale` +
geometry helpers, `seven_segment_digit`, `colon_cell`, and `render`.
Run: **collection ImportError** (`ssh_clock.core` does not exist) — red as
expected.

### Step 2 — core implementation (GREEN)

Implemented `ssh_clock/core.py`: segment table for 0–9, scalable digit/colon
cells, `best_scale` by growing `s` while the block fits, `render` that builds a
`rows x cols` char grid (art when the mode + a scale allow, else centred text).
Run: **38 passed**.

### Step 3 — runtime shell (RED → GREEN)

Wrote `tests/test_cli.py` for the testable seams: `frame_for(struct_time, cols,
rows)`, a `Painter` that suppresses unchanged repaints, and `run(...)` with
injectable `out` / `get_size` / `get_time` / `sleep` so CTRL+C can be simulated.
Run with no `cli.py`: **collection ImportError** — red.
Implemented `ssh_clock/cli.py` (alt-screen, cursor hide/show, resize detection,
`KeyboardInterrupt` → restore + `return 0`) and `__main__.py`.
Run: **42 passed**.

### Step 4 — refactor: digit aspect ratio

Visual check at 24×80 showed digits looked square (segments too squat). Changed
vertical segment height from `1*scale` to `2*scale` (cell height `4s+3`), so
digits read as digits. Updated the three tests that pinned the old height
constants. Run: **42 passed**. Re-checked the render visually — good.

### Step 5 — end-to-end smoke test

Ran `python -m ssh_clock` as a subprocess, sent `SIGINT` after 1s:
return code `0`, alt-screen entered *and* exited, cursor restored. 

### Packaging

Added `pyproject.toml` (`ssh-clock` console script, pytest `pythonpath`/
`testpaths`) and `README.md`.

## 5. Final state

- 42 tests, all passing, ~0.1s.
- `core.py` pure and total (returns exact-size grids for any input, including
  degenerate sizes); `cli.py` is the only module that touches the terminal.
- Known simple choices: gap between cells is a constant 1 char (not scaled);
  colon uses `o` glyphs; scaling is discrete (integer `s`).
