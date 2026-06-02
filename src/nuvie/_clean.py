"""Clean-slate, FLI-structure-aware NUFLI encoder (not a mufflon port).

mufflon dithers to the 16 solid colours first and *then* collapses each 8x2 cell
to its 2-3 realisable colours with no error feedback -- the two stages optimise
different palettes, which is what produces the blocky/noisy look. This encoder
instead **co-designs the dither with the FLI structure**:

* per 8x2 cell it picks ``ink``/``paper`` and per 48px region the shared sprite
  colour, jointly (a couple of coordinate-descent passes), so the chosen colours
  are the ones the hardware can actually show;
* it then dithers at the **2px-sprite-pair** granularity (the real hardware unit:
  each pair is one of the 7 valid INK/PAPER/SPRITE combinations) and **diffuses
  the residual** (Floyd-Steinberg) -- so the quantisation error that mufflon drops
  is spread to neighbours.

Works in YUV with perceptual weights. Output is a standard NUFLI body (hi-res
bitmap + per-8x2 screen RAM + the six main sprite bitmaps and colour table); the
left-24px flibug edge is added separately. Deterministic and mufflon-free.
"""

from __future__ import annotations

import numpy as np

from .nufli import (
    NUFLI_BODY_SIZE,
    NUIFLI_SCRAM,
    _BITMAP_HI,
    _BITMAP_LO,
    _SPRITE_COLOUR_BASE,
    _sprite_addr_map,
)
from .palette import C64_PALETTE

WIDTH, HEIGHT, FLI = 320, 200, 24
INK, PAPER, SPRITE = 0, 1, 2
# the 7 hardware-valid (left,right) source pairs for a 2px sprite-pair.
_COMB = ((INK, INK), (INK, SPRITE), (INK, PAPER), (PAPER, INK),
         (PAPER, PAPER), (SPRITE, SPRITE), (SPRITE, INK))
_WT = np.array([1.0, 0.7, 0.7])  # YUV channel weights (luma-dominant, perceptual)


def _yuv(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return np.stack([y, (b - y) * 0.493, (r - y) * 0.877], axis=-1)


def _sprite_of_col(c):
    """Main-sprite index for char column c (3..38), else -1 (cols 0..2 flibug, 39 none)."""
    return (c - 3) // 6 if 3 <= c <= 38 else -1


def encode_clean(rgb: np.ndarray, iters: int = 3, cohere: float = 600.0) -> bytearray:
    """FLI-aware encode of ``rgb`` (200,320,3) to a NUFLI body. Fills the main
    image (char cols 3..39); cols 0..2 are left for the flibug edge.

    ``cohere`` is the vertical-coherence penalty (cost units) for changing a
    cell's ink/paper or a region's sprite colour from the line-pair above; higher
    keeps colours more stable across a region (less streaking) at some accuracy."""
    COHERE = cohere
    pal = _yuv(np.array(C64_PALETTE, dtype=np.float64))     # (16,3)
    img = _yuv(rgb.astype(np.float64))                      # (200,320,3)

    def dist16(v):  # weighted sq distance of values v(...,3) to the 16 colours
        d = (v[..., None, :] - pal[None, ...]) * _WT
        return (d * d).sum(-1)

    # precompute per-cell pixel distances to the 16 colours: cd[lp][c] = (16px,16col)
    cd = [[None] * 40 for _ in range(100)]
    for lp in range(100):
        for c in range(40):
            px = img[lp * 2:lp * 2 + 2, c * 8:c * 8 + 8].reshape(-1, 3)
            cd[lp][c] = dist16(px)

    ink = np.zeros((100, 40), int)
    paper = np.zeros((100, 40), int)
    spr = np.full((100, 6), -1, int)

    # --- co-design with vertical coherence ---
    # Process line-pairs top to bottom; for each cell's ink/paper and each region's
    # sprite colour, add a penalty for differing from the line-pair above. This keeps
    # colours stable across a region (like mufflon's globally-coherent dither +
    # switch continuity) instead of churning per line-pair, which would streak.
    iv = np.arange(16)
    for lp in range(100):
        for _ in range(iters):
            for c in range(40):
                d = cd[lp][c]                                # (16px,16col)
                s = spr[lp, _sprite_of_col(c)] if 0 <= _sprite_of_col(c) else -1
                base = d[:, s] if s >= 0 else np.full(16, 1e18)
                m = np.minimum(d, base[:, None])             # best of (k, sprite) per px
                cij = np.minimum(m[:, :, None], m[:, None, :]).sum(0)  # (16,16) pair cost
                if lp > 0:                                   # coherence vs cell above
                    pi, pj = int(ink[lp - 1, c]), int(paper[lp - 1, c])
                    new = ((iv != pi) & (iv != pj)).astype(float) * COHERE
                    cij = cij + new[:, None] + new[None, :]
                i, j = np.unravel_index(int(np.argmin(cij)), (16, 16))
                ink[lp, c], paper[lp, c] = i, j
            for s in range(6):
                cols = range(3 + 6 * s, 9 + 6 * s)
                ck = np.zeros(16)                            # cost of sprite colour k
                for c in cols:
                    d = cd[lp][c]
                    bb = np.minimum(d[:, ink[lp, c]], d[:, paper[lp, c]])
                    ck += np.minimum(bb[:, None], d).sum(0)
                if lp > 0:                                   # coherence vs region above
                    ck = ck + (iv != int(spr[lp - 1, s])).astype(float) * COHERE
                spr[lp, s] = int(np.argmin(ck))

    # --- 2px-pair Floyd-Steinberg to each cell's {ink,paper,sprite}, with feedback ---
    # Serpentine scan (alternate row direction) so the residual doesn't bias one way
    # and streak horizontally; diffuse the combo-quantisation residual to neighbours.
    work = img.copy()
    palv = pal
    label = np.zeros((HEIGHT, WIDTH), np.int8)   # 0=PAPER,1=INK,2=SPRITE per pixel
    for y in range(HEIGHT):
        lp = y >> 1
        nxt = work[y + 1] if y + 1 < HEIGHT else None
        l2r = (y & 1) == 0
        pairs = range(0, WIDTH, 2) if l2r else range(WIDTH - 2, -1, -2)
        d = 1 if l2r else -1                       # forward direction
        for x in pairs:
            c = x >> 3
            s = _sprite_of_col(c)
            cols = {INK: ink[lp, c], PAPER: paper[lp, c],
                    SPRITE: (spr[lp, s] if s >= 0 else -1)}
            v0, v1 = work[y, x], work[y, x + 1]
            best, bc = 1e30, (INK, INK)
            for ca, cb in _COMB:
                k0, k1 = cols[ca], cols[cb]
                if k0 < 0 or k1 < 0:
                    continue
                e0 = (v0 - palv[k0]) * _WT
                e1 = (v1 - palv[k1]) * _WT
                cost = (e0 * e0).sum() + (e1 * e1).sum()
                if cost < best:
                    best, bc = cost, (ca, cb)
            label[y, x], label[y, x + 1] = bc
            k0, k1 = cols[bc[0]], cols[bc[1]]
            # diffuse residual (Floyd-Steinberg) in the scan direction
            for xx, kk in ((x, k0), (x + 1, k1)):
                qe = work[y, xx] - palv[kk]
                fx = xx + d
                if 0 <= fx < WIDTH:
                    work[y, fx] += 7 / 16 * qe
                if nxt is not None:
                    if 0 <= xx - d < WIDTH:
                        nxt[xx - d] += 3 / 16 * qe
                    nxt[xx] += 5 / 16 * qe
                    if 0 <= fx < WIDTH:
                        nxt[fx] += 1 / 16 * qe

    # --- assemble the NUFLI body ---
    body = bytearray(NUFLI_BODY_SIZE)
    # screen RAM (ink<<4 | paper)
    for lp in range(100):
        for c in range(40):
            body[NUIFLI_SCRAM[lp] + c] = ((int(ink[lp, c]) & 0xF) << 4) | (int(paper[lp, c]) & 0xF)
    # sprite colour table
    for s in range(6):
        for lp in range(100):
            v = spr[lp, s]
            body[_SPRITE_COLOUR_BASE[s] + lp] = int(v) & 0xF if v >= 0 else 0
    # hi-res bitmap (logical) from INK labels, then split into the two runs
    hires = bytearray(WIDTH // 8 * HEIGHT)
    for y in range(HEIGHT):
        for cx in range(40):
            b = 0
            for px in range(8):
                if label[y, cx * 8 + px] == INK:
                    b |= 1 << (7 - px)
            hires[(y >> 3) * WIDTH + cx * 8 + (y & 7)] = b
    o1, l1 = _BITMAP_HI
    o2, l2 = _BITMAP_LO
    body[o1:o1 + l1] = hires[0:l1]
    body[o2:o2 + l2] = hires[l1:l1 + l2]
    # main sprite bitmaps (SPRITE labels), 2px-wide sprite pixels
    addr = _sprite_addr_map()
    sbm = {}
    for y in range(HEIGHT):
        for x in range(FLI, WIDTH - 8, 2):
            if label[y, x] == SPRITE:
                col = (x - FLI) // 16            # byte index 0..17 (6 sprites x 3)
                bit = ((x - FLI) % 16) // 2      # 0..7 within byte
                sbm[(y, col)] = sbm.get((y, col), 0) | (1 << (7 - bit))
    for (y, col), val in sbm.items():
        if (y, col) in addr:
            body[addr[(y, col)]] = val
    return body
