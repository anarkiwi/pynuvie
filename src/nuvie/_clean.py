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

try:  # numba is an optional accelerator; the kernels run pure-Python without it.
    from numba import njit
except ImportError:  # pragma: no cover

    def njit(*args, **_kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda f: f


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
_COMB = (
    (INK, INK),
    (INK, SPRITE),
    (INK, PAPER),
    (PAPER, INK),
    (PAPER, PAPER),
    (SPRITE, SPRITE),
    (SPRITE, INK),
)
_COMB_ARR = np.array(_COMB, np.int64)  # numba-friendly view of _COMB
_WT = np.array([1.0, 0.7, 0.7])  # YUV channel weights (luma-dominant, perceptual)


@njit(cache=True)
def _dither_kernel(work, palv, wt, comb, ink, paper, spr):
    """Serpentine 2px-pair Floyd-Steinberg over ``work`` (H,W,3, mutated in place).

    For each 2px pair it picks the cheapest hardware-valid (left,right) source combo
    from {ink, paper, sprite} and diffuses the residual to neighbours. Returns the
    per-pixel source labels (0=ink, 1=paper, 2=sprite). The visit/accumulation order
    is identical to the reference loop so the float output is bit-for-bit the same."""
    h, w = work.shape[0], work.shape[1]
    label = np.zeros((h, w), np.int8)
    for y in range(h):
        lp = y >> 1
        has_nxt = y + 1 < h
        l2r = (y & 1) == 0
        direction = 1 if l2r else -1
        x = 0 if l2r else w - 2
        while 0 <= x <= w - 2:
            c = x >> 3
            s = (c - 3) // 6 if 3 <= c <= 38 else -1
            ci, cp = ink[lp, c], paper[lp, c]
            cs = spr[lp, s] if s >= 0 else -1
            best, bca, bcb = 1e30, 0, 0
            for t in range(comb.shape[0]):
                ca, cb = comb[t, 0], comb[t, 1]
                k0 = ci if ca == 0 else (cp if ca == 1 else cs)
                k1 = ci if cb == 0 else (cp if cb == 1 else cs)
                if k0 < 0 or k1 < 0:
                    continue
                cost = 0.0
                for ch in range(3):
                    e0 = (work[y, x, ch] - palv[k0, ch]) * wt[ch]
                    e1 = (work[y, x + 1, ch] - palv[k1, ch]) * wt[ch]
                    cost += e0 * e0 + e1 * e1
                if cost < best:
                    best, bca, bcb = cost, ca, cb
            label[y, x], label[y, x + 1] = bca, bcb
            k0 = ci if bca == 0 else (cp if bca == 1 else cs)
            k1 = ci if bcb == 0 else (cp if bcb == 1 else cs)
            for which in range(2):
                xx = x + which
                kk = k0 if which == 0 else k1
                fx = xx + direction
                for ch in range(3):
                    qe = work[y, xx, ch] - palv[kk, ch]
                    if 0 <= fx < w:
                        work[y, fx, ch] += (7.0 / 16.0) * qe
                    if has_nxt:
                        if 0 <= xx - direction < w:
                            work[y + 1, xx - direction, ch] += (3.0 / 16.0) * qe
                        work[y + 1, xx, ch] += (5.0 / 16.0) * qe
                        if 0 <= fx < w:
                            work[y + 1, fx, ch] += (1.0 / 16.0) * qe
            x += 2 * direction
    return label


def _yuv(a):
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return np.stack([y, (b - y) * 0.493, (r - y) * 0.877], axis=-1)


def _sprite_of_col(c):
    """Main-sprite index for char column c (3..38), else -1 (cols 0..2 flibug, 39 none)."""
    return (c - 3) // 6 if 3 <= c <= 38 else -1


def encode_clean(
    rgb: np.ndarray, iters: int = 3, cohere: float = 600.0, texture: float = 0.7
) -> bytearray:
    """FLI-aware encode of ``rgb`` (200,320,3) to a NUFLI body. Fills the main
    image (char cols 3..39); cols 0..2 are left for the flibug edge.

    ``cohere`` is the vertical-coherence penalty for changing a cell's ink/paper or
    a region's sprite colour from the line-pair above (higher = less streaking).
    ``texture`` (0..1) blends the cell colour choice between nearest-endpoint error
    (0 = flat, lowest MSE) and dithered/segment error (1 = bracketing colours the
    dither blends, mufflon-like high-frequency texture)."""
    COHERE = cohere
    pal = _yuv(np.array(C64_PALETTE, dtype=np.float64))  # (16,3)
    img = _yuv(rgb.astype(np.float64))  # (200,320,3)

    def dist16(v):  # weighted sq distance of values v(...,3) to the 16 colours
        d = (v[..., None, :] - pal[None, ...]) * _WT
        return (d * d).sum(-1)

    # Pre-compute, per 8x2 cell, the weighted pixels and their distance to each
    # colour. The structure is chosen by *dithered* error (distance to the SEGMENT
    # between ink and paper, not the nearer endpoint), so bracketing colours the
    # FS dither can blend into the true shade win -- that's what gives texture
    # instead of collapsing sub-palette gradients to a flat colour.
    pw = pal * _WT  # weighted palette (16,3)
    pwpw = pw @ pw.T  # (16,16) dot products
    ab2 = pwpw.diagonal()[:, None] + pwpw.diagonal()[None, :] - 2 * pwpw  # |pw_j-pw_i|^2
    ab2 = np.where(ab2 > 1e-9, ab2, 1.0)  # (16i,16j)
    diag = pwpw.diagonal()
    cd = [[None] * 40 for _ in range(100)]  # cd[lp][c] = (16px,16col)
    cppw = [[None] * 40 for _ in range(100)]  # P . pw  (16px,16col)
    for lp in range(100):
        for c in range(40):
            px = img[lp * 2 : lp * 2 + 2, c * 8 : c * 8 + 8].reshape(-1, 3)
            cd[lp][c] = dist16(px)
            cppw[lp][c] = (px * _WT) @ pw.T

    def seg_pre_of(d, ppw):
        """Per-pixel dist^2 to the i..j palette segment, ``(px,16,16)``, sprite-free.
        Depends only on the cell (d, ppw) so it is hoisted out of the iters loop."""
        # dist^2 to segment [i,j]: t = (P-A).(B-A)/|B-A|^2; clamp; line dist via Pythagoras
        dot = (ppw[:, None, :] - ppw[:, :, None]) - (pwpw[None] - diag[:, None][None])  # (px,i,j)
        t = dot / ab2[None]
        line = d[:, :, None] - (np.clip(t, 0, 1) ** 2) * ab2[None]  # (px,i,j)
        return np.where(t < 0, d[:, :, None], np.where(t > 1, d[:, None, :], line))

    def pair_cost(d, seg_pre, sprite_d, tex):
        """Per-cell cost cij[i,j] for choosing ink=i, paper=j, blended between the
        *nearest-endpoint* error (tex=0, flat/accurate) and the *dithered* error
        (tex=1, distance to the i..j segment -- bracketing colours the FS dither
        blends, giving texture). The sprite is a 3rd point in both. d=(px,col)
        squared distances, ``seg_pre`` the cached sprite-free segment distances."""
        m = np.minimum(d, sprite_d[:, None]) if sprite_d is not None else d
        near = np.minimum(m[:, :, None], m[:, None, :]).sum(0)  # nearest-endpoint
        if tex <= 0:
            return near
        seg = np.minimum(seg_pre, sprite_d[:, None, None]) if sprite_d is not None else seg_pre
        seg = seg.sum(0)
        return (1 - tex) * near + tex * seg

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
        # segment geometry is sprite-free and constant across iters -- compute once.
        cseg = [seg_pre_of(cd[lp][c], cppw[lp][c]) for c in range(40)] if texture > 0 else None
        for _ in range(iters):
            for c in range(40):
                s = spr[lp, _sprite_of_col(c)] if 0 <= _sprite_of_col(c) else -1
                sprite_d = cd[lp][c][:, s] if s >= 0 else None
                cij = pair_cost(cd[lp][c], cseg[c] if cseg is not None else None, sprite_d, texture)
                if lp > 0:  # coherence vs cell above
                    pi, pj = int(ink[lp - 1, c]), int(paper[lp - 1, c])
                    new = ((iv != pi) & (iv != pj)).astype(float) * COHERE
                    cij = cij + new[:, None] + new[None, :]
                i, j = np.unravel_index(int(np.argmin(cij)), (16, 16))
                ink[lp, c], paper[lp, c] = i, j
            for s in range(6):
                cols = range(3 + 6 * s, 9 + 6 * s)
                ck = np.zeros(16)  # cost of sprite colour k
                for c in cols:
                    d = cd[lp][c]
                    bb = np.minimum(d[:, ink[lp, c]], d[:, paper[lp, c]])
                    ck += np.minimum(bb[:, None], d).sum(0)
                if lp > 0:  # coherence vs region above
                    ck = ck + (iv != int(spr[lp - 1, s])).astype(float) * COHERE
                spr[lp, s] = int(np.argmin(ck))

    # --- 2px-pair Floyd-Steinberg to each cell's {ink,paper,sprite}, with feedback ---
    # Serpentine scan (alternate row direction) so the residual doesn't bias one way
    # and streak horizontally; diffuse the combo-quantisation residual to neighbours.
    work = np.ascontiguousarray(img, dtype=np.float64).copy()
    label = _dither_kernel(work, pal, _WT, _COMB_ARR, ink, paper, spr)

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
    body[o1 : o1 + l1] = hires[0:l1]
    body[o2 : o2 + l2] = hires[l1 : l1 + l2]
    # main sprite bitmaps (SPRITE labels), 2px-wide sprite pixels
    addr = _sprite_addr_map()
    sbm = {}
    for y in range(HEIGHT):
        for x in range(FLI, WIDTH - 8, 2):
            if label[y, x] == SPRITE:
                col = (x - FLI) // 16  # byte index 0..17 (6 sprites x 3)
                bit = ((x - FLI) % 16) // 2  # 0..7 within byte
                sbm[(y, col)] = sbm.get((y, col), 0) | (1 << (7 - bit))
    for (y, col), val in sbm.items():
        if (y, col) in addr:
            body[addr[(y, col)]] = val
    return body
