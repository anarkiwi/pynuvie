# The NUVIE file format

A **NUVIE** is a video for the Commodore 64, played from a 16 MiB
[REU](https://www.c64-wiki.com/wiki/REU) (RAM Expansion Unit) by Crest's
`nuvieplayer`. It is a sequence of [NUFLI](https://www.c64-wiki.com/wiki/NUFLI)
hi-res still images, an optional SID soundtrack, and a *playlist* that scripts
playback (order, speed, loops, holds, blank screens). A NUVIE file is simply a
raw 16,777,216-byte image of the REU's contents.

This document describes the on-REU byte layout. It was established by:

1. Reverse-engineering Crest's reference player `nuvieplayer1.0.prg` — observing
   which bytes it validates, how it assembles the header and playlist, and where
   it DMAs frame data. (`pynuvie` ships the resulting slot→C64 map in
   `src/nuvie/data/slotmap.json`.)
2. Cross-checking the [C64-Wiki Nuvie article](https://www.c64-wiki.de/wiki/Nuvie)
   and the `NUVIEmaker 0.1e` README by DeeKay & Crossbow of Crest.
3. Reading Crest's `mufflon` NUFLI encoder source for the still-image layout.

Everything here is verified by `pynuvie`'s tests and (for the player-facing
parts) by playing generated REUs in the real player under VICE.

## Top-level layout

The REU is **256 banks** of **65,536 bytes** = 16 MiB.

```
bank = REU[b*0x10000 : (b+1)*0x10000]      for b in 0..255
```

Within each bank:

| Bank offset       | Size   | Contents                                            |
|-------------------|--------|-----------------------------------------------------|
| `0x0000..0x004F`  | 80     | image slot 0, **part 1**                            |
| `0x0050..0x009F`  | 80     | image slot 1, **part 1**                            |
| `0x00A0..0x00EF`  | 80     | image slot 2, **part 1**                            |
| `0x00F0..0x00FF`  | 16     | **auxiliary block** (see below)                     |
| `0x0100..0x55FF`  | 21760  | image slot 0, **part 2**                            |
| `0x5600..0xAAFF`  | 21760  | image slot 1, **part 2**                            |
| `0xAB00..0xFFFF`  | 21760  | image slot 2, **part 2**                            |

So each bank stores **3 image slots** plus a 16-byte auxiliary block. A frame's
image is its part 1 (80 bytes) followed by its part 2 (21760 bytes) = **21840
bytes**. The split is purely to let the player DMA the data quickly.

* Frame `f` (0..767) lives in **bank `f // 3`**, **slot `f % 3`**.
* Maximum **768 frames** (≈ 61 s at 12.5 fps) when there is no music.

## The auxiliary block

The 16 bytes at `0x00F0..0x00FF` of **every** bank are reserved and used
collectively:

### Bank 0 — signature

Bank 0's auxiliary block holds a 16-byte signature that the player checks before
playing anything. It is the C64 screen-code string `"nuvie001v1.0    "`:

```
0E 15 16 09 05 30 30 31 16 31 2E 30 20 20 20 20
 n  u  v  i  e  0  0  1  v  1  .  0  ␠  ␠  ␠  ␠
```

If it does not match, the player shows *"no valid nuvie data found!"* and stops.

### Bank 1 — control block

Bank 1's auxiliary block is the per-movie control block:

| Offset | Field                | Meaning                                             |
|--------|----------------------|-----------------------------------------------------|
| `$F0`  | music flag           | `$00` none, `$E8` loop, `$F8` restart               |
| `$F1`–`$F3` | music start     | REU address, little-endian (lo, mid, hi)            |
| `$F4`–`$F6` | music end       | REU address, little-endian (lo, mid, hi)            |
| `$F7`  | custom-code flag     | `$FF` if custom code is present                     |
| `$F8`  | border colour        | left/right                                          |
| `$F9`  | border colour        | top/bottom                                          |
| `$FA`  | infoscreen           | bit 7 = show flag; low nibble = text colour         |
| `$FB`  | infoscreen           | border/background colour                            |
| `$FC`–`$FD` | infoscreen dur. | duration in frames, little-endian                   |
| `$FE`  | character set        | `$A7` small, `$A5` large                            |
| `$FF`  | unused               |                                                     |

### Banks 16..143 — playlist storage

The 2048-byte playlist is **spread across the auxiliary blocks of banks 16..143**
(16 bytes per bank). At start-up the player gathers them into a contiguous block
at C64 `$0800` and interprets it:

```
playlist_byte[j] = REU[(16 + j//16)*0x10000 + 0x00F0 + (j%16)]   for j in 0..2047
```

## The playlist

The playlist is a stream of two-byte tokens `(command, value)`. See
`src/nuvie/playlist.py` for the full, source-grounded token reference; in brief:

| Token      | Meaning                                                          |
|------------|------------------------------------------------------------------|
| `0y xx`    | show image number `y*100 + xx` (**decimal**); sets frame counter |
| `10 xx`    | begin loop, repeated `xx` times                                  |
| `20 ??` / `30 ??` | end loop (reset image / keep image)                       |
| `8f xx` … `80 xx` | play `xx` frames **backward** (skip 1,2,3… for speed)     |
| `90 xx`    | hold current image for `xx` frames                               |
| `91 xx` … `9f xx` | play `xx` frames **forward** (skip 1,2,3… for speed)      |
| `by xx`    | playback speed: `y+1` frames per image (3 ⇒ 4 = normal)          |
| `cy xx` / `dy xx` | blank screen colour `y` for `xx` frames (without/with border) |
| `ey xx`    | end: wrap to playlist address `(y<<8)|xx`, music-free            |
| `fy xx`    | end: wrap to playlist address `(y<<8)|xx`, in sync with music    |

Playback runs at **12.5 fps** (one image every 4 frames at normal speed).

## Music

When present, SID music is recorded as **25 SID register values per 1/50 s
frame** and stored growing **downwards** from the top of the REU (`$FFFFF4`).
The player DMAs 25 bytes per frame into the SID image at the C64. The control
block's music start/end addresses delimit it. Roughly one image's worth of REU
space is consumed per ~17.5 s of music.

## The frame image (NUFLI)

Each 21840-byte frame slot holds one NUFLI image's graphics. NUFLI is a 320×200
hi-res format: FLI on the even raster lines (a fresh ink/paper colour pair per
8×2 block) plus a hi-res sprite underlay that adds a third colour and recolours
the odd lines, giving access to all 16 colours.

The player does **not** display the slot from one contiguous buffer; it issues a
series of REU→C64 DMA transfers that scatter the slot into the layout its FLI
displayer reads (it double-buffers, with the active hi-res **bitmap at C64
`$E000`** and FLI screen RAM around `$9000–$AFFF`). `pynuvie` ships the
empirically-recovered transfer map (`nuvie.slotmap`); `scatter()` reconstructs a
frame's C64 memory image from its slot for analysis.

For the **standalone** NUFLI `.prg` ("`.nuf`") format produced by `mufflon`
(load address `$2000`, 0x5A00 bytes), `pynuvie`'s `nuvie.nufli` decodes the
hi-res bitmap + FLI screen RAM **plus the six main hi-res sprites that provide
NUFLI's third colour** (where the bitmap bit is 0 and a sprite bit is 1, the
sprite's per-line-pair colour shows instead of paper) — validated against
mufflon's own rendering to the dithering-noise floor across `x` in [24, 312).
The left 24px "flibug" edge (a multicolour + hi-res sprite pair with per-line
colour switching applied by the displayer) is not decoded and falls back to the
raw bitmap colours. All byte offsets come from the `mufflon` source.
`NufliImage.from_image`
**encodes** an image back into that layout (per-8×2 two-colour FLI, all 16
colours across the frame) — a pure-Python, mufflon-free NUFLI encoder, verified
to round-trip exactly through the decoder.

### Player display layout and the colour caveat

The reference player relocates a frame into VIC bank 3 and double-buffers it.
Confirmed by tracing its REU→C64 DMA and by playing crafted REUs:

* the hi-res **bitmap** is at C64 `$E000`–`$FF40` (standard hi-res byte order);
* **FLI screen RAM** is spread through `$C000`–`$D5FF`;
* the player adds colour through a **hi-res sprite underlay**, not only the FLI
  screen pair — so the displayed colour of a set bitmap bit is driven by the
  sprite plane.

### Packing a frame into a slot (full colour)

`pynuvie` builds player-ready, full-colour slots in pure Python by reproducing
what Crest's `NUVIEmaker` does when it stashes a loaded NUFLI image into the REU.
Recovered by reverse-engineering NUVIEmaker's pack routine (C64 `$0E00`):

* the routine walks a table of 8-byte DMA descriptors at `$9800` —
  `[c64_lo, c64_hi, reu_lo, reu_mid, bank_index, len_lo, len_hi, terminator]` —
  each a C64→REU "stash" (REU command `$FC`);
* the C64 source is the loaded `.nuf` graphics at `$2000+` plus a fixed
  player-displayer stub at `$1000-$1FFF` that NUVIEmaker supplies;
* a frame is assigned a slot via zero-page base bytes; frame 0 uses base mid
  `$01`, i.e. part 2 at bank offset `$0100` and part 1 (80 bytes) at `$0000`.

`nuvie.pack.build_slot()` applies this table (shipped as `data/pack_table.json`)
to the encoder's graphics over the fixed source template (`data/pack_source.bin`).
The result matches NUVIEmaker's *own* packed slot **99.9%** byte-for-byte and
plays correctly on `nuvieplayer1.0.prg`, so `nuvie.encode` / `build_movie` emit
full per-8×2-colour video. (The pack table and displayer stub are derived from
Crest's NUVIEmaker and bundled, with attribution, purely for format interop. The
left-edge ~24px flibug sprites are taken from the template rather than generated.)

## Sources

* C64-Wiki — Nuvie: <https://www.c64-wiki.de/wiki/Nuvie>
* C64-Wiki — NUFLI: <https://www.c64-wiki.com/wiki/NUFLI>
* NUVIEmaker 0.1e (CSDb): <https://csdb.dk/release/?id=100031> (README by DeeKay/Crossbow)
* mufflon NUFLI encoder: `https://svn.sngs.de/metalvotze/svn/repo/mufflon`
* `nuvieplayer1.0.prg` (reverse-engineered REU layout & DMA map)
