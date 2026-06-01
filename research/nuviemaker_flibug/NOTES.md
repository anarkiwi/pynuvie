# NUVIEmaker flibug (left-24px) — reverse-engineering notes & port plan

Goal: generate the NUFLI "flibug" left-edge plane in pure Python so pynuvie's
encoded frames render the left 24px correctly on the reference player, matching
NUVIEmaker's own output.

## Architecture (fully reverse-engineered)

The VIC-II **FLI bug** corrupts the leftmost 3 char columns (24px): FLI rewrites
`$d018` every raster line, and the leftmost columns can't fetch colour in time.
NUFLI covers this with **sprite 0 in multicolour mode** pinned at x=24 (plus a
hi-res companion), recoloured per line. Solid *horizontal* content is immune (the
misfetched colour equals the band colour) — so a flibug test pattern needs
**vertical detail in the left 24px** to engage the sprites.

Pipeline (verified by driving the real tools via vice-driver):

1. **mufflon** encodes a frame to a `.nuf`. Its **sprite-colour table**
   (`$0400/$0480/$0800/$0880/$0c00/$0c80`, 6 columns × 101 line-pairs) holds the
   per-line sprite colours; the flibug colours are woven in as **switch-codes**
   `colour | switch_val` with `switch_vals = {hires:0x70, m1:0x50, m2:0x60,
   m3:0xe0}` (see mufflon `find_best_colors_flibug` / `set_free_register`). Initial
   (line-0) flibug colours live at `.nuf` `$1ff7/$1ff1/$1ff0/$1ff6`. Flibug sprite
   bitmaps are at `flibug_hires_spram` / `flibug_multi_spram` offsets.
2. **NUVIEmaker** generates the **per-frame displayer** (relocated to C64
   `$1000-$1FFF` in each slot's part 2) by **copying the `.nuf` colour table into
   the displayer's unrolled per-line `LDY #imm; STY $d0xx` operands** (the
   displayer *structure* is a fixed template; only the colour immediates change
   per frame). The pack routine at `$0e00` is **pure REU DMA** (walks the 8-byte
   descriptor table at `$9800`, command `$fc`); it does NOT generate the displayer
   — generation happens at frame-load time, writing `$1000-$1FFF` in C64 RAM.

Evidence: mufflon `lv.nuf` flibug switch-code colours `18d3a4536b71…` ≈ the
generated displayer's flibug colours `18d3a453b7…` (same data, mapped through the
displayer's per-line layout). See `lv.nuf`, `lv_displayer.bin`, `lv_slot.bin`.

Why earlier attempts failed: `build_slot` reused **cmp's** displayer for every
frame, so all frames inherited cmp's flibug colours.

## Port plan (multi-session)

1. **Derive the table→displayer mapping** (keystone). Find/disassemble
   NUVIEmaker's generator (writes `$1000-$1FFF` from the loaded `.nuf` table).
   Generator lives in RAM under ROM (writes traced near `$ed00-$eeac` are the
   serial fast-loader, NOT the generator — keep looking). Cleanest: feed a `.nuf`
   whose colour table cells carry distinct markers, drive NUVIEmaker, capture the
   generated displayer, and read off `immediate-site -> (line-pair, column)`.
2. **Port mufflon's main FLI colour encoder** (`find_best_colors_new` etc.) to
   produce the 6-column sprite-colour table (pynuvie already does hi-res + FLI
   ink/paper; this adds the per-line main sprite colours).
3. **Port mufflon's `find_best_colors_flibug`** (4-colours-per-line search +
   `flibug_*_spram` bitmaps) to produce the flibug switch-codes + sprite bitmaps.
4. **Implement displayer generation in `build_slot`**: bake the colour table into
   the displayer template's immediates per the mapping from step 1.
5. **Validate** each step against captured real outputs (this dir) and the
   emulator (`/tmp/fix/shot.py`).

## NUVIEmaker's displayer generator (fully disassembled — `$3000`)

The generator (C64 `$3000`, runs at frame-load, before pack) builds the displayer
at `$1000` as **100 line-pairs × a 40-byte block**, copied via `STA ($fb),Y`
(`$fb/$fc` starts `$1000`). Source artifacts: `gen_full.bin` ($3000-$3500),
`gen_nuftab.bin` (loaded .nuf colour tables $2400-$2d00).

Per line-pair `X` (0..99):
- FLI phase `Y = X & 3` selects `$d018`/`$d011` values from tables:
  - `$334c[Y]` = `68 58 48 38`  → the `$d018` screen-base sequence
  - `$3344[Y]` = `39 28 2f 34`, `$3348[Y]` = `06 06 06 03`, `$3340[Y]` = `02 00 00 02`
    → patched into the block's `$d011`/setup bytes.
- For each of the 6 colour-table columns, read `.nuf` byte and decode via `$33b0`:
  - col0 `$2401,X`→reg `$28`; col1 `$2481,X`→`$29`; col2 `$2801,X`→`$2a`;
    col3 `$2881,X`→`$2b`; col4 `$2c01,X`→`$2c`; col5 `$2c81,X`→`$2d`.
    (`$24xx/$28xx/$2cxx` = `.nuf` `$04xx/$08xx/$0cxx`, the 6 sprite-colour columns.)

`$33b0(A=value, Y=register)` decoder — returns `(A=immediate, Y=STY-target-reg)`:
```
hi = value >> 4
hi == 0 : return A=value,            Y=register     # normal colour -> STY $d028+col
hi == 1 : return A=$d4, Y=value&$0f                  # (special; pointer/$d011 path)
hi >= 2 : return A=value, Y=(hi|$20)                 # switch -> STY $d0(hi|$20):
                                                     #   $5x->$d025 $6x->$d026
                                                     #   $7x->$d027 $ex->$d02e
```
So a `.nuf` colour-table cell's **high nibble picks the VIC register** (0 = that
column's main sprite `$d028+col`; `$5/$6/$7/$e` = a flibug register) and the **low
nibble is the colour**. The 40-byte block template (`$3300`) is:
`STY $d028; LDY #c1; STY $d029; LDY #c2; STY $d02a; LDY #c3; STY $d02b;
LDY #c4; STY $d02c; LDY #c5; STY $d02d; LDY #c6; STY $d018` (+ a 7-byte header for
`$d011`/`$d018` patched from the phase tables). The decoded `(imm, reg)` pairs are
written into the block's `LDY #` operands and `STY $d0xx` register bytes.

Also: `$3010` copies a 47-byte VIC sprite-setup table (`$3fc0` → `$d000-$d02e`:
sprite X/Y positions x=24,48,96,144,192,240,288,24; enable `$ff`; `$d010=$40`;
multicolour/expand) — captured live earlier as
`18 d4 30 d4 60 d4 90 d4 c0 d4 f0 d4 20 d4 18 d4 / 40 10 21 00 00 ff …`.
Flibug initial (line-0) colours come from `.nuf` `$1ff7/$1ff1/$1ff0/$1ff6`.

### IMPLEMENTED + VALIDATED — `nuvie._displayer.generate()` (task #13 DONE)

The generator is ported and **byte-exact** against the real NUVIEmaker for two
independent inputs (`lv.nuf` and `stripes.nuf`, see `tests/test_displayer.py`).
Key facts nailed down:

* The displayer body is `$1000-$1ee3` = **3812 bytes** (the pack descriptor len).
  Shipped structural template: `src/nuvie/data/displayer_template.bin`.
* Only the six per-line-pair colour/register bytes are per-frame; the
  `$d018`/`$d011` FLI sequence, opcodes and the 4 phase-header variants are
  **content-independent** (proven: lv template + stripes colours == real stripes
  displayer, 0 diffs over $1000-$1ee3).
* Block length = `40 - start`, `start = (2,0,0,2)[lp&3]`; col-0 colour offset =
  `(6,6,6,3)[lp&3]`; cols 1..5 colour offsets `(0x0b,0x10,0x15,0x1a,0x1f)`, reg
  offsets `(0x08,0x0d,0x12,0x17,0x1c,0x21)`; `$33b0` decode as in `_displayer.py`.

### Remaining (task #14): produce the `.nuf` colour table + flibug bitmaps
`from_image` must emit the 6-column sprite-colour table (`COLOUR_COLS`) with main
sprite colours + flibug switch-codes, plus the flibug `flibug_*_spram` sprite
bitmaps, by porting mufflon's `find_best_colors_new` + `find_best_colors_flibug`.
Then `build_slot`: `disp = _displayer.generate(body)`; splice `disp` over the
displayer region of `src` ($1000-$1ee3) before the pack DMA. Validate end-to-end
on the emulator against mufflon->NUVIEmaker references.

## Oracle (how to drive the real NUVIEmaker)

`vd_lv.py` / `vd_stripes.py`: boot `nuviemaker0.1e` in the `nuviemaker:local`
docker with `-binarymonitor`, drive the UI with vice-driver `keymatrix_tap`
(TAP_MODE_FIXED — NUVIEmaker polls the CIA directly, so KERNAL keybuf does NOT
work), load one `.nuf`, call pack `$0e00`, read the REU slot. `vd_dumphi.py`
dumps RAM-under-ROM. Build the disk with `c1541` (format, write
`nuviemaker0.1e.prg` + `aaNNN` frames). Mufflon as makenuvie does:
`mufflon x.bmp --flibug -p --dither --prep_mode yuv`.

## Artifacts in this dir

- `cmp_displayer.bin` — displayer for the cmp fixture frame (C64 $1000-$1FFF).
- `lv.nuf` — mufflon output for a left-vertical-bands test image.
- `lv_displayer.bin` — NUVIEmaker's generated displayer for `lv.nuf` (correct).
- `lv_slot.bin` — NUVIEmaker's packed REU bank 0 for `lv.nuf` (renders correctly).
- `nm_code.bin` ($0800-$2400), `nm_high.bin` ($c000-$ffff) — NUVIEmaker code dumps.
- `dis6502.py` — minimal 6502 disassembler. `vd_*.py` — oracle drivers.
