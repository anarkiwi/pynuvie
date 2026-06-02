# NUFLI / FLI theory (confirmed against the emulator)

Notes built from the NUFLIX write-up (cobbpg), the VIC-II FLI references, and
**emulator experiments** (drive the real `nuvieplayer` in VICE, screenshot).
Goal: a solid model so encoder work isn't blind knob-turning.

## FLI mechanism
* FLI forces a **bad line on every raster line** by writing `$d011` (YSCROLL)
  mid-line so `(raster & 7) == YSCROLL` becomes true *after* the normal
  badline check — so the screen-RAM (colour) is re-fetched every line, but the
  **row counter RC is not reset** (it keeps 0..7), and the **video counter VC**
  advances normally.
* Therefore the **bitmap is a standard, contiguous 8000-byte hi-res bitmap**:
  byte for (char_col c, char_row cr=y>>3, pixel_row r=y&7) =
  `bitmap_base + (cr*40 + c)*8 + r`. (Our `_bitmap_bit` decode uses exactly this,
  and the bitmap is stored split into two runs only for the C64 memory map.)
* The **screen RAM (ink<<4|paper) is re-fetched per line** from a base set by
  `$d018` bits 4-7, which the displayer cycles every line-pair (phase = lp&3 →
  the 4 values `$68 $58 $48 $38` in the .nuf displayer). `NUIFLI_SCRAM[lp]` is
  the resulting address for line-pair `lp`. The displayer's `$d018`/`$d011`
  sequence is **content-independent** (validated byte-exact).

## FLI bug
* The forced bad line costs 3 cycles where the VIC reads `$ff` off the bus
  instead of screen RAM → the **leftmost 3 char columns (24px)** show light grey
  on light grey (colour 15). Unavoidable in the bitmap; NUFLI covers it with two
  sprites at x=24 (one hi-res, one multicolour) recoloured per line = the
  "flibug" plane.

## The third colour and ODD lines (important for the encoder)
* Six double-width hi-res sprites tile x=24..312 (48px each) as an **underlay**:
  where the bitmap bit is 0 and a sprite bit is 1, the sprite's colour shows
  instead of paper → a **third colour per 48px region per line-pair**.
* A 2px sprite pixel is the unit, so each 2px pair is one of **7 valid
  INK/PAPER/SPRITE combinations** (mufflon `combinations_normal`).
* The sprites also **recolour the odd lines** (FLI screen RAM is per line-pair).

## Emulator-verified basics (see test_fli_basics.py)
Through `nuvie._clean` + `nuvie.pack` + the real player:
* **solid colour** → renders solid (clean). Base FLI + sprite/odd-line OK.
* **16 full-width colour bands** → 16 clean bands. Per-line-pair colour OK.
* **vertical grey ramp** → mostly clean, but occasional **spurious colour**
  (e.g. a yellow band in a grey ramp) → the *colour selection* is the weak point,
  not the format.

## Diagnosis of the streaking on photographic content
The base/pack/displayer are correct. The remaining artifact (horizontal
streaking on complex frames) is **colour-selection lacking vertical coherence**:
`_clean` picks ink/paper per cell and the sprite colour per region independently
per line-pair, so colours churn ~2x more than mufflon (≈419 vs ≈205 changes/
frame), producing horizontal bands. mufflon's global dither + switch-budget
continuity keep colours stable across a region. The fix is to add vertical
coherence (prefer keeping a colour across line-pairs unless a change clearly
helps), not to chase a "magic byte" in the format.
