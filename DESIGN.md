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

### Step 6 — refinement: readable digits (feedback)

Feedback: the seven-segment line art (`|` and `_`) rendered too thin to read,
and it wasn't using the horizontal space. Switched approach:

- **5x7 dot-matrix font** for `0`-`9` and `:`, drawn with solid block glyphs
  (`█`, U+2588) instead of lines. Each matrix pixel is blown up to a `pw` x
  `ph` rectangle of blocks.
- `best_pixel_scale(rows, cols, time_str)` now picks `ph` to fill the height
  and `pw` to fill the width *independently*, then applies a legibility clamp:
  `pw <= 4*ph` (bold wide strokes are good) and `ph <= 2*pw` (allow vertical
  stretch so a tall narrow terminal fills its height, but not so far the
  digits go spindly). A terminal cell is ~2:1 tall:wide, so `pw = 2*ph` is
  the visually-square reference point.
- The colon is a real 2x7 glyph (two 2x2 lit blocks), so it scales and stays
  visible like the digits.

Rewrote `test_core.py` around the new API (font shape, geometry, the scale
clamp, scaled-block rendering). Updated the one `test_cli.py` assertion that
checked for `_`. Run: **44 passed**. Visual checks at 24x80, 40x160, 50x200,
16x90, 20x120 — bold and legible, block fills the space, aspect kept sane.

### Step 7 — refinement: vector segments + half-block rasteriser (feedback)

Feedback: the 5x7 block-matrix digits read fine when small, but at large sizes
each "pixel" became a huge square and the digits got hard to read; also asked
to (a) cap the aspect stretch at 1.5x and centre in the slack beyond that, and
(b) render the strokes more finely rather than as giant pixels.

New model in `core.py`:

- **Vector seven-segment glyphs.** Each segment is an axis-aligned rectangle in
  a 100x180 local box: horizontal bars run the full width, vertical bars sit
  between them with a small `_JOIN` gap so the corners come out clean. The
  colon is two square dots. `digit_ink()` / `colon_ink()` are simple
  point-in-rectangle tests — exact, and cheap.
- **Half-block rasteriser.** `render_art` samples the vector shapes on a
  `cols` x `2*rows` grid (2x vertical resolution, which also makes a sample
  cell roughly square) and packs each vertical pair into ` ▀ ▄ █`. Axis-aligned
  edges keep it crisp at any scale. ~8 ms for a 60x240 frame.
- **`fit_scale`** replaces the old integer `best_pixel_scale`: largest uniform
  scale that fits, then the roomy axis may stretch by at most `MAX_ASPECT`
  (1.5) before we stop and centre. Falls back to text if the digits would come
  out below a readability floor (`_MIN_DIGIT_SUBPX_*`).

Rewrote `test_core.py` around the new surface (segment ink by digit, the 1.5
aspect cap across many terminal shapes, uniform-scale case, half-block output,
centring, text fallback). `test_cli.py` unchanged (`core.BLOCK` still appears
in big digits). Run: **44 passed**. Visual checks 12x60 … 50x200 — bold, clean
segments, readable at every size.

### Step 8 — refinement: segmented model + best-fit glyph match (feedback)

Feedback (with references): the rectangular-segment + half-block version read
terribly at large sizes -- the strokes broke into disconnected `▀`/`▄`
fragments. Asked for (a) a tighter aspect cap -- stretch until the larger side
is 1.5x the smaller, then centre, no further; (b) a *Geascript*-style
segmented display; and (c) real use of Unicode diagonal glyphs so diagonals
render as diagonals.

Rebuilt the big-digit path:

- **Chamfered segmented model.** Seven segments, each a hexagon with 45-degree
  ends, positioned so adjacent segments *share an edge* -- a digit is one
  connected shape with the classic notched-corner LCD look. `digit_ink` /
  `colon_ink` test point-in-convex-polygon.
- **Best-fit glyph rasteriser.** A candidate library (`_build_candidates`):
  space, block + eighth-block + quadrant elements, the four solid triangles
  `◤ ◥ ◣ ◢`, and all 60 **sextants** (`U+1FB00`+, 2x3 sub-cell). Each carries a
  6x6 coverage bitmap. Per character cell we sample the model on a 6x6 grid and
  emit the candidate with the smallest bit-difference (`int.bit_count` on the
  XOR). Diagonals pick triangles; thin strokes snap to eighth-blocks.
- A 3x3 coarse probe skips the many all-empty / all-solid cells; results are
  memoised (`_match_char`) and whole frames are `lru_cache`d. ~25 ms at 24x100,
  ~80 ms at 50x200, recomputed once a second.
- `fit_scale` unchanged in spirit (1.5 aspect cap, then centre); tuned the
  readability floor so art still kicks in at 8 rows when width allows.

Tests: added `TestGlyphMatcher` (empty/full/half/diagonal) and updated the
render assertions for the new glyph set. **49 passed.**
Visual checks 8x80 … 60x240: connected, legible segmented digits with real
diagonal chamfers at every size. `cli` tick relaxed to 0.25 s.

### Step 9 — refinement: drop sextants, common glyphs only (feedback)

Feedback: on the test terminal the sextants (`U+1FB00`+) rendered but with
glitchy, misaligned edges. Removed them from the candidate library. The set is
now just space + Block Elements (`U+2580..U+259F`: full/half/eighth blocks and
the ten quadrants) + the four triangles `◤◥◣◢` (`U+25E2..U+25E5`) -- all of
which have consistent metrics in essentially every terminal font. The chamfers
are a little chunkier without the 2x3 resolution but the edges are clean.
`test_only_widely_supported_glyphs` pins the codepoint ranges. **49 passed.**

## 5. Final state

- 49 tests, all passing, ~0.3s.
- `core.py` pure and total (returns exact-size grids for any input, including
  degenerate sizes); `cli.py` is the only module that touches the terminal.
- Big digits: chamfered segmented-display vector model, rasterised by best-fit
  match against a small glyph library (full/half/eighth blocks, the ten
  quadrants, the four triangles `◤◥◣◢`); aspect stretch capped at 1.5x then
  centred; text fallback below a readability floor.
- Every render glyph has consistent metrics in standard terminal fonts (Block
  Elements + four Geometric-Shapes triangles); no exotic codepoints.
- Known simple choices: 6x6 coverage sampling (no sub-cell anti-aliasing beyond
  the glyph set); colon dots are octagons; glyph constants tuned by eye.
