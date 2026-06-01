"""A faithful, byte-exact port of mufflon's NUFLI encoder (non-flibug path).

This transliterates Crest's ``mufflon.c`` colour optimiser so ``pynuvie`` produces
**byte-identical** NUFLI graphics to mufflon for the default (no ``--flibug``)
output: the hi-res bitmap, the per-8x2 FLI screen RAM, the six main sprite
bitmaps and the sprite colour table.

Scope and fidelity
------------------
mufflon's encoder is deterministic for the non-flibug path (single- and
multi-threaded output agree); only its ``--flibug`` plane is racy/nondeterministic
(mufflon does not produce identical bytes there run-to-run), so byte-parity is
defined and achieved only for the non-flibug graphics. The reference is mufflon
built from its published source, run with ``--dest-palette pepto`` on an image
whose pixels are already exact Pepto colours (so ``prepare()`` is an identity and
the only thing under test is the colour search). ``EVEN`` and ``--deblock`` are
mufflon's defaults (0), so ``find_best_colors_new`` and error-feedback are dead
code and are not ported.

The mufflon globals/functions reproduced here keep their original names in the
docstrings: ``find_used_colors``, ``find_best_combinations``,
``find_best_colors_line``, ``find_best_colors_normal_columns``,
``find_free_register_switches``, ``set_8_switches`` and ``render``.
"""

from __future__ import annotations

import functools

import numpy as np

from .nufli import (
    NUFLI_BODY_SIZE,
    NUIFLI_SCRAM,
    _SPRITE_COLOUR_BASE,
    _sprite_addr_map,
)
from .palette import C64_PALETTE

C64XRES, C64YRES = 320, 200
FLI = 0x18
SPLITSTART, SPLITEND = 0x3E, 0x52
WEIGHTS_RGB = (0.299, 0.587, 0.114)
PAIR_INF = 256 * 256 * 256  # mufflon's per-pair "no match" sentinel (256^3)
_BIG = 1 << 60

# combination-index constants (mufflon.h)
INK, PAPER, SPRITE = 0, 1, 2

# combinations_normal as (idx0, idx1) pairs, in mufflon's table order.
_COMB_NORMAL = (
    (INK, INK), (INK, SPRITE), (INK, PAPER),
    (PAPER, INK), (PAPER, PAPER), (SPRITE, SPRITE), (SPRITE, INK),
)

# ink/paper search values, in mufflon's iteration order: 15..0 then -1 (unused).
_VALS = list(range(15, -1, -1)) + [-1]
_NV = len(_VALS)  # 17
_VALS_ARR = np.array(_VALS)
_GE0 = _VALS_ARR >= 0  # which of the 17 values are real colours


def _cost_array(rgb: np.ndarray) -> np.ndarray:
    """mufflon ``find_used_colors`` diff_lut/abs-sum: cost[y,x,colour] =
    |trunc((r-pr)*0.299)| + |trunc((g-pg)*0.587)| + |trunc((b-pb)*0.114)|.

    The per-channel weighted differences are cast to C ``int`` (truncate toward
    zero) before the abs-sum, exactly as mufflon stores them in diff_lut."""
    pal = np.array(C64_PALETTE, dtype=np.float64)            # (16,3)
    diff = rgb[:, :, None, :].astype(np.float64) - pal[None, None, :, :]
    w = np.array(WEIGHTS_RGB)
    d = np.trunc(diff * w).astype(np.int64)                  # toward zero
    return np.abs(d).sum(axis=3)                             # (200,320,16)


def _padded_cost(cost_row_x: np.ndarray) -> np.ndarray:
    """Append an INF colour slot at index 16 so a value of -1 maps to INF."""
    return np.concatenate([cost_row_x, np.full(cost_row_x.shape[:-1] + (1,), _BIG)],
                          axis=-1)


def _vidx(v: int) -> int:
    return v if v >= 0 else 16


def _cell_delta_grid(costpad, x0, y, spr1, spr2):
    """mufflon ``find_best_combinations`` summed over one 8x2 cell, as a function
    of (ink, paper) on the 17x17 search grid. Row ``y`` uses sprite colour
    ``spr1``; row ``y+1`` uses ``spr2`` (mufflon row1/row2). Returns a (17,17)
    int grid of total deltas (axis0=ink, axis1=paper, in mufflon value order)."""
    ink_pad = [_vidx(v) for v in _VALS]
    grid = np.zeros((_NV, _NV), dtype=np.int64)

    for row_y, spr in ((y, spr1), (y + 1, spr2)):
        cp = costpad[row_y]  # (320, 17)
        spr_i = cp[:, _vidx(spr)]                      # (320,) cost of sprite colour
        ci = cp[:, ink_pad]                            # (320, 17) cost over ink vals
        cp_ = cp[:, ink_pad]                           # cost over paper vals (same set)
        ink_ge0 = _GE0[:, None]                        # (17,1)
        pap_ge0 = _GE0[None, :]                        # (1,17)
        ink_ne_spr = (_VALS_ARR != spr)[:, None]
        ink_ne_pap = (_VALS_ARR[:, None] != _VALS_ARR[None, :])
        spr_ge0 = spr >= 0

        for a, b in ((x0, x0 + 1), (x0 + 2, x0 + 3), (x0 + 4, x0 + 5), (x0 + 6, x0 + 7)):
            cia, cib = ci[a][:, None], ci[b][:, None]          # (17,1)
            cpa, cpb = cp_[a][None, :], cp_[b][None, :]        # (1,17)
            csa, csb = spr_i[a], spr_i[b]                      # scalars

            cands = []
            # INK,INK  (valid: ink>=0)
            cands.append(np.where(ink_ge0, cia + cib, _BIG))
            # INK,SPR  (ink>=0 & spr>=0 & ink!=spr)
            m = ink_ge0 & spr_ge0 & ink_ne_spr
            cands.append(np.where(m, cia + csb, _BIG))
            # INK,PAP  (ink>=0 & pap>=0 & ink!=pap)
            m = ink_ge0 & pap_ge0 & ink_ne_pap
            cands.append(np.where(m, cia + cpb, _BIG))
            # PAP,INK  (pap>=0 & ink>=0 & pap!=ink)
            cands.append(np.where(m, cpa + cib, _BIG))
            # PAP,PAP  (pap>=0)
            cands.append(np.where(pap_ge0, cpa + cpb, _BIG))
            # SPR,SPR  (spr>=0)
            cands.append(np.where(spr_ge0, np.full((_NV, _NV), csa + csb), _BIG))
            # SPR,INK  (spr>=0 & ink>=0 & spr!=ink)
            m = spr_ge0 & ink_ge0 & ink_ne_spr
            cands.append(np.where(m, csa + cib, _BIG))

            pairmin = functools.reduce(np.minimum, cands)  # broadcasts to (17,17)
            grid = grid + np.minimum(pairmin, PAIR_INF)

    # guard: a result is only recorded if some row2 colour (ink|paper|spr2) >= 0.
    if spr2 < 0:
        guard = _GE0[:, None] | _GE0[None, :]   # ink>=0 or paper>=0
        grid = np.where(guard, grid, _BIG)
    return grid


def _argmin_grid(grid):
    """First (ink desc, paper desc) cell achieving the min (mufflon's strict-<)."""
    flat = int(np.argmin(grid))
    bi, bp = divmod(flat, _NV)
    return _VALS[bi], _VALS[bp], int(grid[bi, bp])


# --- vectorised sprite search (computes find_best_colors_line over all
# sprite/ink/paper values at once; equivalent to the per-call _line, just fast) ---

_INK_PAD = [_vidx(v) for v in _VALS]
_GE0_S = _GE0[:, None, None]                            # sprite axis
_GE0_I = _GE0[None, :, None]                            # ink axis
_GE0_P = _GE0[None, None, :]                            # paper axis


def _row_grid_all(costpad, row_y, block_x, ncells):
    """For one row, return G[cell, spr, ink, paper] = mufflon
    ``find_best_combinations`` summed over the cell's 4 pixel-pairs, evaluated for
    every (sprite, ink, paper) value at once. Axes use mufflon value order."""
    cp = costpad[row_y]                                  # (320, 17)
    ne_is = (_VALS_ARR[:, None] != _VALS_ARR[None, :])   # (spr,ink) inequality
    ne_ip = (_VALS_ARR[:, None] != _VALS_ARR[None, :])   # (ink,paper) inequality
    out = np.empty((ncells, _NV, _NV, _NV), dtype=np.int64)
    for c in range(ncells):
        x0 = block_x + c * 8
        grid = np.zeros((_NV, _NV, _NV), dtype=np.int64)  # (spr, ink, paper)
        for a, b in ((x0, x0 + 1), (x0 + 2, x0 + 3), (x0 + 4, x0 + 5), (x0 + 6, x0 + 7)):
            va = cp[a, _INK_PAD]                          # (17,) cost of each value
            vb = cp[b, _INK_PAD]
            S = va[:, None, None]   # value indexed by sprite axis (pixel a)
            Sb = vb[:, None, None]
            Ia = va[None, :, None]  # by ink axis
            Ib = vb[None, :, None]
            Pa = va[None, None, :]  # by paper axis
            Pb = vb[None, None, :]
            cands = []
            # INK,INK (ink>=0)
            cands.append(np.where(_GE0_I, Ia + Ib, _BIG))
            # INK,SPR (ink>=0 & spr>=0 & ink!=spr); ne_is axes are (spr,ink)
            m = _GE0_I & _GE0_S & ne_is[:, :, None]
            cands.append(np.where(m, Ia + Sb, _BIG))
            # INK,PAP (ink>=0 & pap>=0 & ink!=pap)
            mip = _GE0_I & _GE0_P & ne_ip[None, :, :]
            cands.append(np.where(mip, Ia + Pb, _BIG))
            # PAP,INK (pap>=0 & ink>=0 & pap!=ink)
            cands.append(np.where(mip, Pa + Ib, _BIG))
            # PAP,PAP (pap>=0)
            cands.append(np.where(_GE0_P, Pa + Pb, _BIG))
            # SPR,SPR (spr>=0)
            cands.append(np.where(_GE0_S, S + Sb, _BIG))
            # SPR,INK (spr>=0 & ink>=0 & spr!=ink)
            cands.append(np.where(m, S + Ib, _BIG))
            pairmin = functools.reduce(np.minimum, cands)
            grid = grid + np.minimum(pairmin, PAIR_INF)
        out[c] = grid
    return out


def _line(costpad, block_x, y, width, spr1, spr2):
    """mufflon ``find_best_colors_line``: per 8px cell pick best (ink,paper).

    Returns ``(delta, cells)`` where ``delta`` is the summed block minimum used to
    rank sprite colours and ``cells`` is a list of ``(char_col, ink, paper)`` after
    mufflon's post-search "optimize a bit" relabelling (used to fill screen RAM)."""
    delta = 0
    cells = []
    for x in range(block_x, block_x + width, 8):
        grid = _cell_delta_grid(costpad, x, y, spr1, spr2)
        best_ink, best_paper, blk_best = _argmin_grid(grid)
        delta += blk_best
        # "optimize a bit": mufflon's ink/paper loop breaks on a perfect match
        # (blk_best==0), so row1[INK]==row2[INK] hold that break ink (==best_ink);
        # otherwise they end at -1. row1[PAPER]/row2[PAPER] always end at -1.
        row_ink = best_ink if blk_best == 0 else -1
        if best_paper == row_ink:
            best_paper = -1
        if best_ink == spr1 and best_ink == spr2:
            best_ink, best_paper = best_paper, -1
        if best_paper == spr1 and best_paper == spr2:
            best_paper = -1
        cells.append((x // 8, best_ink, best_paper))
    return delta, cells


class _State:
    def __init__(self):
        self.sprites = np.full((C64YRES, 6), -1, dtype=np.int64)
        self.inks = np.full((C64YRES, C64XRES // 8), -1, dtype=np.int64)
        self.papers = np.full((C64YRES, C64XRES // 8), -1, dtype=np.int64)
        self.final = np.zeros((C64YRES // 2 + 1, 6), dtype=np.int64)
        self.free = np.zeros((C64YRES // 2 + 1, 6), dtype=np.int64)
        self.free_sum = np.zeros(C64YRES // 2 + 1, dtype=np.int64)
        self.free_max = 0


def _find_free_register_switches(st: _State):
    """mufflon ``find_free_register_switches``: downsample sprites into
    final_sprite_tab (101 rows) and tally per-row switching opportunities."""
    spr = st.sprites
    src, dest = 0, 0
    while src < C64YRES:
        for b in range(6):
            v = spr[src, b]
            st.final[dest, b] = 0xFF if v < 0 else v
        dest += 1
        src += 2
        if src == 2:
            src = 1
    for y in range(C64YRES // 2 + 1):
        s = 0
        for b in range(6):
            if y == 0:
                st.free[y, b] = 1
                s += 1
            elif st.final[y, b] == st.final[y - 1, b] or st.final[y, b] == 0xFF:
                st.free[y, b] = 1
                s += 1
            else:
                st.free[y, b] = 0
        st.free_sum[y] = s
    st.free_max = int(st.free_sum[SPLITSTART:SPLITEND + 1].sum())


def _set_free_register(st: _State, y: int, reg: int):
    if y == 0:
        return
    for a in range(5, -1, -1):
        if st.free[y, a]:
            st.final[y, a] = reg
            st.free[y, a] = 0
            st.free_sum[y] -= 1
            return


def _set_8_switches(st: _State):
    """mufflon ``set_8_switches``: inject sprite-pointer switch register codes
    (0x11,0x13,...) into final_sprite_tab across the split region."""
    reg = 0x11
    for b in range(6, 0, -1):
        for y in range(SPLITEND, SPLITSTART - 1, -1):
            if reg < 0x20 and b == st.free_sum[y]:
                _set_free_register(st, y, reg)
                reg += 2


def _idx_of(v):
    return 15 - v if v >= 0 else 16


def _best_sprites(costpad, block_x, y, width, spr1_vals, spr2_vals):
    """Vectorised ``find_best_colors_line`` ranking: return the (spr1, spr2) pair
    minimising the 48px block delta, searched over the candidate value lists (each
    in mufflon's descending order). Identical result to looping ``_line`` over the
    candidates, but evaluates all sprite/ink/paper at once."""
    ncells = width // 8
    si1 = [_idx_of(v) for v in spr1_vals]
    si2 = [_idx_of(v) for v in spr2_vals]
    gy = _row_grid_all(costpad, y, block_x, ncells)[:, si1, :, :]       # (c,S1,I,P)
    gy1 = _row_grid_all(costpad, y + 1, block_x, ncells)[:, si2, :, :]  # (c,S2,I,P)
    totals = gy[:, :, None, :, :] + gy1[:, None, :, :, :]              # (c,S1,S2,I,P)
    # guard: drop (ink=-1, paper=-1) where spr2 is also -1
    for j, v in enumerate(spr2_vals):
        if v < 0:
            totals[:, :, j, 16, 16] = _BIG
    cell_min = totals.min(axis=(3, 4))                                 # (c,S1,S2)
    line_delta = cell_min.sum(axis=0)                                  # (S1,S2)
    flat = int(np.argmin(line_delta))
    a, b = divmod(flat, len(spr2_vals))
    return spr1_vals[a], spr2_vals[b]


def _find_best_colors_normal_columns(st: _State, costpad):
    """mufflon ``find_best_colors_normal_columns`` (EVEN=0): for columns 0..5 pick
    per row-pair sprite colours with continuity (sprite1 pinned from the previous
    pair, sprite2 freely searched) and the split-region switch budget, then the
    lone column 6 (x=312)."""
    width, offset = 48, FLI
    allvals = list(range(15, -2, -1))  # 15..-1, mufflon order
    for column in range(6):
        for y in range(0, C64YRES, 2):
            spr1s, spr1e, spr2s, spr2e = -1, 15, -1, 15
            _find_free_register_switches(st)
            cur = int(st.sprites[y, column])
            if SPLITSTART <= y // 2 <= SPLITEND and st.free_max <= 8:
                spr1s = spr1e = spr2s = spr2e = cur
            elif y != 0 and cur >= 0:
                spr1s = spr1e = cur

            block_x = column * width + offset
            spr1_vals = [cur] if spr1s == spr1e else allvals
            spr2_vals = [cur] if spr2s == spr2e else allvals
            best_spr1, best_spr2 = _best_sprites(costpad, block_x, y, width,
                                                 spr1_vals, spr2_vals)
            # final recalc with the chosen sprite colours -> screen RAM
            _, cells = _line(costpad, block_x, y, width, best_spr1, best_spr2)
            for charcol, ink, paper in cells:
                for ry in (y, y + 1):
                    st.inks[ry, charcol] = ink
                    st.papers[ry, charcol] = paper
            if spr1s != spr1e:
                if y != 0:
                    st.sprites[y - 1, column] = best_spr1
                st.sprites[y, column] = best_spr1
            st.sprites[y + 1, column] = best_spr2
            if y < C64YRES - 2:
                st.sprites[y + 2, column] = best_spr2

    # column 6: the last 8px char column (x=312), no sprite.
    block_x = C64XRES - 8
    for y in range(0, C64YRES, 2):
        _, cells = _line(costpad, block_x, y, 8, -1, -1)
        for charcol, ink, paper in cells:
            for ry in (y, y + 1):
                st.inks[ry, charcol] = ink
                st.papers[ry, charcol] = paper


def _best_combinations_labels(costpad, x0, y, ink, paper, spr):
    """mufflon ``find_best_combinations`` for render: per pixel in an 8px block
    return the chosen combination index (INK/PAPER/SPRITE) for each of the 8
    pixels, with the post-pick "optimize" relabel to INK when colours coincide."""
    cols = {INK: ink, PAPER: paper, SPRITE: spr}
    cp = costpad[y]
    out = [PAPER] * 8
    for off in (0, 2, 4, 6):
        best = PAIR_INF
        r0 = r1 = -1
        for i0, i1 in _COMB_NORMAL:
            c0, c1 = cols[i0], cols[i1]
            if c0 < 0 or c1 < 0:
                continue
            if c0 == c1 and i0 != i1:
                continue
            delta = int(cp[x0 + off, _vidx(c0)] + cp[x0 + off + 1, _vidx(c1)])
            if delta < best:
                best = delta
                r0, r1 = i0, i1
            if best == 0:
                break
        # "optimize a bit": fold a colour that equals ink back to the INK label
        if r0 >= 0 and cols[r0] == cols[INK]:
            r0 = INK
        if r1 >= 0 and cols[r1] == cols[INK]:
            r1 = INK
        out[off] = r0
        out[off + 1] = r1
    return out


def _render(st: _State, costpad) -> np.ndarray:
    """mufflon ``render`` (non-flibug, start=FLI): build the hi-res bitmap and the
    six main sprite bitmaps from the final per-pixel combination labels."""
    hires = np.zeros(C64XRES // 8 * C64YRES, dtype=np.uint8)  # mufflon hires layout
    spr_bm = np.zeros(C64YRES * 3 * 6, dtype=np.uint8)
    for y in range(C64YRES):
        labels = {}
        for x0 in range(FLI, C64XRES, 8):
            ink = int(st.inks[y, x0 // 8])
            paper = int(st.papers[y, x0 // 8])
            if (x0 - FLI) < 6 * 48:
                spr = int(st.sprites[y, (x0 - FLI) // 48])
            else:
                spr = -1
            lab = _best_combinations_labels(costpad, x0, y, ink, paper, spr)
            for j in range(8):
                labels[x0 + j] = lab[j]
        bmp_mask = spr_mask = 0
        for x in range(FLI, C64XRES):
            bmp_mask = (bmp_mask << 1) & 0xFF
            if (x & 1) == 0:
                spr_mask = (spr_mask << 1) & 0xFF
            lab = labels[x]
            if lab == INK:
                bmp_mask |= 1
            elif lab == SPRITE:
                spr_mask |= 1
            if (x & 7) == 7:
                hires[y // 8 * C64XRES + (x - 7) + (y & 7)] = bmp_mask
                bmp_mask = 0
            if ((x - FLI) & 15) == 15 and FLI <= x < C64XRES - 8:
                spr_bm[y * 18 + (x - FLI - 15) // 16] = spr_mask
                spr_mask = 0
    return hires, spr_bm


def encode_body(rgb: np.ndarray) -> bytearray:
    """Encode an exact-Pepto ``(200,320,3)`` RGB array to a NUFLI body
    (``$2000..$7A00``) byte-identical to mufflon's non-flibug graphics regions:
    hi-res bitmap, FLI screen RAM, main sprite bitmaps and sprite colour table."""
    cost = _cost_array(rgb)                       # (200,320,16)
    costpad = _padded_cost(cost)                  # (200,320,17), index 16 == INF
    st = _State()
    _find_best_colors_normal_columns(st, costpad)
    _find_free_register_switches(st)
    _set_8_switches(st)
    hires, spr_bm = _render(st, costpad)

    body = bytearray(NUFLI_BODY_SIZE)
    # sprite colour table (final_sprite_tab, 0xff wiped to 0)
    final = st.final.copy()
    final[final == 0xFF] = 0
    for y in range(C64YRES // 2 + 1):
        for b in range(6):
            body[_SPRITE_COLOUR_BASE[b] + y] = int(final[y, b])
    # hi-res bitmap split (convert_nufli): [0:0x1400]->$6000, [0x1400:0x1f40]->$3400
    body[0x4000:0x4000 + 0x1400] = bytes(hires[0:0x1400])
    body[0x1400:0x1400 + 0x0B40] = bytes(hires[0x1400:0x1F40])
    # screen RAM (ink<<4 | paper); unset (-1) -> 0
    for y in range(0, C64YRES, 2):
        for x in range(C64XRES // 8):
            i = int(st.inks[y, x])
            p = int(st.papers[y, x])
            i = 0 if i < 0 else i
            p = 0 if p < 0 else p
            body[NUIFLI_SCRAM[y // 2] + x] = (i << 4) | p
    # main sprite bitmaps
    addr_map = _sprite_addr_map()
    for (yy, col), addr in addr_map.items():
        body[addr] = int(spr_bm[yy * 18 + col])
    return body
