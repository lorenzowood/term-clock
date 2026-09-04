# Term Clock — Design & Development Log

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

### Step 10 — refinement: integer-scaled bitmap font, no raggedness (feedback)

Feedback: the best-fit coverage match still produced ragged, glitchy edges and
stray non-45-degree runs. Asked to simplify: numbers made only from blocks and
45-degree triangles, at scales that stay exact.

Reworked into a two-level bitmap approach:

- **Design grid.** Each digit is a seven-segment shape on a small integer grid
  (`Font(10,10,2)` normally, `Font(7,7,1)` when that won't fit). `_chamfer`
  walks the filled grid and replaces every *convex* corner cell with one of the
  design markers `F/J/L/P` (the four triangle orientations). That single-cell
  cut is what reads as a segmented-display bevel.
- **Integer expansion.** `_expand` blows one design cell up to an `nx` x `ny`
  block: empty and solid cells tile trivially; a triangle cell is rasterised
  (4x4 supersample, coverage thresholds) into full blocks + a clean run of the
  *one* triangle glyph on its hypotenuse. Output is only ever `space`, `█`,
  `◤◥◣◢` -- nothing else can appear, so there are no half-lit or ragged cells.
  `_expand` is `lru_cache`d per `(marker, nx, ny)`; a whole 50x200 frame
  renders in ~0.2 ms (no frame cache needed).
- **`fit`** picks the largest font that fits, then an integer cell size: base
  `s = min(rows//h, cols//wtot)`, with each axis allowed to grow to `1.5*s`
  (`MAX_ASPECT`) to use slack before the rest becomes centring margin.

`test_core.py` rewritten around the bitmap font (design-char alphabet, chamfer
of every convex corner, `_expand` output alphabet, `fit` aspect bound, font
selection). **70 passed.** Visual checks 8x70 … 50x200: crisp segmented digits,
no ragged edges, only blocks and triangles.

## 5. Final state

- 70 tests, all passing, ~0.05s.
- `core.py` pure and total (returns exact-size grids for any input, including
  degenerate sizes); `cli.py` is the only module that touches the terminal.
- Big digits: seven-segment bitmap font on an integer design grid with
  one-cell chamfered corners, expanded by integer `nx` x `ny` scale factors.
  Output alphabet is exactly `{space, █, ◤, ◥, ◣, ◢}` -- all common glyphs,
  all consistent metrics -- so the result never looks ragged.
- Aspect: each axis stretches at most 1.5x past the uniform integer scale to
  use slack, then the rest is centring margin. Text fallback when even the
  small font doesn't fit.
- Known simple choices: two hand-tuned font sizes; colon dots are chamfered
  rectangles; the triangle staircase at large non-square scales is stepped but
  clean.

### Step 11 — drop sampling; draw only H, V, and 1:1 45° (feedback)

The integer expansion of triangle cells still produced off-angle stairs when
`nx != ny`. The font is now drawn directly at the output size: horizontal and
vertical bars are rectangles of `█`; convex corners are a 1:1 stair of size
`max(1, t//2)` using `◤ ◥ ◣ ◢`. No coverage sampling.

`Layout(t, hw, vh, gap, colon_w)`: a digit is `2t+hw` × `3t+2vh`. Default
cell is 5t×5t; each axis may stretch ≤ 1.5× (`MAX_ASPECT`).

### Step 12 — style knobs (feedback)

`--padding N` (default 1) and `--spacing N` (default 2). Padding is a blank
frame so the clock never sits on the window edge.

### Step 13 — colon dots (feedback)

Colons are two axis-aligned `█` rectangles (no 45° cuts), centred, whose
combined span is at most `digit_h / 3` (3 rows on a tiny digit so the two
dots still have a hole). 1-row dots are 2 wide; larger dots are square.

### Step 14 — stop filling the scrollback (feedback)

Each paint already went home + `2J`, but a full-width last line wraps and
every tick landed in the scroll buffer. Clear is now home + `2J` + `3J`
(visible screen *and* saved lines), and wraparound is switched off for the
run so the last cell cannot scroll.

### Step 15 — diff the frame instead of clearing (feedback)

Full-screen clear every tick flickered. `Painter` now keeps the last frame as
an off-screen buffer. First paint (or a resize) still clears and draws; after
that only runs of changed cells are written, each prefixed with a CUP
(`row;col` H). Unchanged cells are left alone.

### Step 16 — poll rate, then sleep to the second (feedback)

Fixed-rate polling jittered under load. The loop now paints, sleeps until the
next wall-clock second minus a learned `lead_ms`, and if the wake error is
more than 2 ms, shifts `lead_ms` (clamped 0–100 ms).

### Step 17 — drop `--hz`, add `--hour-format`, rename (feedback)

`--hz` is gone. Resize waits until the next second.

`--hour-format {12,24}`: default is the system clock via
`locale.setlocale(LC_TIME, "")` + `nl_langinfo(T_FMT)` (`%I` / `%p` / `%r`
→ 12, otherwise 24). 12-hour: 0→12 AM, 12→12 PM, 13→1 PM. Art mode places
ASCII `AM`/`PM` to the right of the digits.

The project is renamed from `ssh-clock` / `ssh_clock` to `term-clock` /
`term_clock`.

### Step 18 — wait for the displayed second to change (feedback)

`lead_ms` woke us *before* the second. `paint()` sampled `localtime` still
on second S, then `next_second_ms(now)` saw S+1 and slept until S+2, so a
second was skipped. `lead_ms` is gone. After each paint we sleep the
remainder until the next whole second, and keep sleeping (1 ms once past
the boundary) until `localtime`'s (h, m, s) actually differs from the
frame we last showed. If the second has already moved on, the wait loop
is empty and we paint immediately.

### Step 19 — square bar ends, keep curve chamfers (feedback)

Free ends of horizontal and vertical bars were getting the same 45° cut as
outer elbows, so a 2's top-left and a 4's vertical tips looked pointed.
A termination is now detected as a pair of convex corners spanning stroke
thickness ``t``; those stay square. Unpaired convex corners (L-joints of
two segments) still get the 1:1 triangle stair.

### Step 20 — interval colours, bar, config, clock/background colour (feedback)

`--interval` (default 15, or `off`) tiles a grid from `--interval-start`.
Amber/red windows colour the digits; the bar under the digits (gap =
padding, height = stroke `t`) fills in default then amber then red.
`~/.config/term-clock/term-clock.conf` plus `--config-file`. Optional
`--clock-color` / `--background-color` hex.

### Step 21 — brighter default amber (feedback)

Default `--interval-amber-color` is `#f09000` (was `#d07000`).

### Step 22 — reset SGR when leaving red/amber (feedback)

Diff paints omitted SGR when the ink was the terminal default, so after red
the next interval's digits and bar stayed red. Every run now emits an
explicit foreground (including `39` for default).

### Step 23 — padding and spacing as size fractions (feedback)

Fixed cell counts made large clocks look squashed: `--padding` / `--spacing`
stayed at 1 and 2 while digits grew. They are now multipliers of digit size
(padding) and digit width (spacing), rounded up so a positive fraction never
collapses to 0. Explicit `0` still means none. Defaults: `0.125` and `0.2`.

## 5. Final state

- 118 tests, all passing. Intervals default on (15 minutes from `0:00`).
- `core.py` pure and total (returns exact-size grids for any input, including
  degenerate sizes); `cli.py` is the only module that touches the terminal.
- Big digits: seven-segment rectangles of `█`. Free bar ends are square;
  outer L-joint curves get 1:1 45° stairs of `◤ ◥ ◣ ◢`. Colons are small
  block pairs, no diagonals.
- `--padding` (default 0.125 of digit size), `--spacing` (default 0.2 of
  digit width), `--hour-format` 12 or 24 (default: system, else 24).
- Aspect: default cell is 5t×5t characters; each axis may stretch by at most
  1.5× (longer bars, same stroke thickness) before leftover space is centred.
  Text fallback when even t=1 does not fit.
