"""Encode the NUFLI "flibug" left-edge plane (leftmost 24px), mufflon-free.

The VIC-II FLI bug corrupts the leftmost three character columns. NUFLI hides it
with two sprites (a hi-res + a multicolour, pinned at x=24) recoloured per line.
This module reproduces mufflon's flibug encoding: per line-pair it picks four
sprite colours for the left 24px, assigns each pixel a colour source via
``combinations_flibug``, and emits

* the FLI ink/paper for the 3 left columns + the left-edge hi-res bitmap,
* the two flibug sprite bitmaps (``flibug_*_spram`` offsets),
* the four initial flibug colours (``$1ff7/$1ff1/$1ff0/$1ff6``),
* per-line colour switches woven into the 6-column sprite-colour table that
  :mod:`nuvie._displayer` bakes into the per-frame displayer.

Verified end-to-end on the reference player (a vertical-bands test image renders
its left edge correctly). The colour-source channels and ``switch_vals`` match
mufflon; the displayer side is validated byte-exact in
``research/nuviemaker_flibug/``.
"""

from __future__ import annotations

from typing import Optional

from .palette import C64_PALETTE
from .nufli import NUIFLI_SCRAM

WIDTH, HEIGHT, FLI = 320, 200, 0x18
SPLITSTART, SPLITEND = 0x3E, 0x52  # split-region line-pairs (mufflon)
INK, PAPER = 0, 1
FLISPRITE, M1, M2, M3 = 6, 7, 8, 9
_CH = (FLISPRITE, M1, M2, M3)

# valid (left-pixel, right-pixel) colour-source pairs for a 2px group (mufflon
# combinations_flibug). Ordered so earlier == preferred on ties.
_COMB = ((PAPER, PAPER), (PAPER, FLISPRITE), (FLISPRITE, PAPER), (M1, M1),
         (M1, FLISPRITE), (M2, M2), (M2, FLISPRITE), (M3, M3), (M3, FLISPRITE),
         (FLISPRITE, FLISPRITE), (FLISPRITE, M1), (FLISPRITE, M2), (FLISPRITE, M3),
         (INK, PAPER), (PAPER, INK), (M3, INK), (M2, INK), (M1, INK),
         (FLISPRITE, INK), (INK, M3), (INK, M2), (INK, M1), (INK, FLISPRITE),
         (INK, INK))

_SWITCH = {FLISPRITE: 0x70, M1: 0x50, M2: 0x60, M3: 0xE0}   # mufflon switch_vals
_MSPR_BITS = {M1: 0b01, M2: 0b11, M3: 0b10}
_INIT_OFF = {FLISPRITE: 0x1FF7, M1: 0x1FF1, M2: 0x1FF0, M3: 0x1FF6}
# sprite-pointer (multiplex) switches: column 5, line-pairs 70..81 (content-
# independent; the displayer needs these to reposition the flibug sprites).
_PTR_SWITCHES = {70: 0x1F, 72: 0x1D, 74: 0x1B, 76: 0x19, 78: 0x17, 79: 0x15,
                 80: 0x13, 81: 0x11}

# flibug sprite-bitmap body offsets per line-pair (mufflon flibug_*_spram).
_FH = ([0x59C0, 0x5980, 0x5940, 0x5900, 0x58C0, 0x5880, 0x5840, 0x5800] * 8
       + [0x1200, 0x1240, 0x1280, 0x12C0] * 5 + [0x1240, 0x1280, 0x12C0, 0x1200] * 4)
_FM = ([0x57C0, 0x5780, 0x5740, 0x5700, 0x56C0, 0x5680, 0x5640, 0x5600] * 8
       + [0x0000, 0x0040, 0x0080, 0x00C0] * 5 + [0x0040, 0x0080, 0x00C0, 0x0000] * 4)

_SP_OFF: Optional[tuple] = None


def _sprite_offsets():
    global _SP_OFF
    if _SP_OFF is not None:
        return _SP_OFF
    ho = [[0, 0, 0] for _ in range(HEIGHT)]
    mo = [[0, 0, 0] for _ in range(HEIGHT)]
    row = 5
    for y in range(HEIGHT):
        for b in range(3):
            srow = (row + (b % 3)) & 0x3F
            ho[y][b] = _FH[y // 2] + srow
            mo[y][b] = _FM[y // 2] + srow
        if (y & 1) == 0:
            row += 3
        if row > 0x3F:
            row &= 0x3F
        elif row == 0x3F:
            row = 0
    _SP_OFF = (ho, mo)
    return _SP_OFF


def _bitmap_off(logical: int) -> int:
    return (0x4000 + logical) if logical < 0x1400 else (0x1400 + logical - 0x1400)


def encode_flibug(img, body: bytearray, has_main: bool = False, sprite_tab=None) -> None:
    """Fill ``body`` with the flibug plane for the target image ``img`` (Pillow,
    resized to 320x200). ``body`` already holds the main FLI encode; this overlays
    the left-24px bitmap/ink-paper, the two sprite bitmaps, the colour table and
    the initial colours. The displayer is generated separately by
    :func:`nuvie._displayer.generate` and spliced in by the packer.

    With ``has_main`` the body already carries the 3rd-colour underlay's per-line
    sprite colours in the colour table; the flibug colour switches are woven only
    into free slots (columns whose main colour is unchanged), so the underlay and
    the flibug coexist. ``sprite_tab`` is the main encoder's un-wiped 101x6 sprite
    colour table (0xFF = unused); it gives the per-line switch budget that bounds
    how many flibug colours may change (mufflon ``free_switches_flibug``)."""
    import numpy as np
    from ._displayer import COLOUR_COLS

    ho, mo = _sprite_offsets()
    pal = np.asarray(C64_PALETTE, dtype=np.int64)
    arr = np.asarray(img.convert("RGB").resize((WIDTH, HEIGHT)), dtype=np.int64)
    w = np.array([0.299, 0.587, 0.114])
    err = np.abs((arr[:, :FLI, None, :] - pal[None, None, :, :]) * w).sum(axis=3).astype(np.int64)
    nearest = err.argmin(axis=2)

    used = [[set() for _ in range(3)] for _ in range(HEIGHT)]
    for y in range(HEIGHT):
        for x in range(FLI):
            used[y][x // 8].add(int(nearest[y, x]))

    def combo(x, y, cols):
        """Best channel pair + cost for the 2px group (x,x+1) on line y."""
        ey, ey1 = err[y, x], err[y, x + 1]
        best, ra, rb = 1 << 60, -1, -1
        for ca, cb in _COMB:
            c0, c1 = cols[ca], cols[cb]
            if c0 < 0 or c1 < 0 or (c0 == c1 and ca != cb):
                continue
            d = ey[c0] + ey1[c1]
            if d < best:
                best, ra, rb = d, ca, cb
                if best == 0:
                    break
        return best, ra, rb

    def block_cost(x0, y, cols):
        return sum(combo(x0 + k, y, cols)[0] for k in (0, 2, 4, 6))

    def line_cost(lp, sprite_cols):
        """Total left-24px error for a line-pair given 4 sprite colours, choosing
        the best ink/paper per block. Returns (total, [(ink,paper) per block])."""
        y = lp * 2
        cols = [-1] * 10
        cols[FLISPRITE], cols[M1], cols[M2], cols[M3] = sprite_cols
        afli = (y & 7) < 2
        total, ip = 0, []
        for b in range(3):
            x0 = b * 8
            u = used[y][b]
            inks = sorted(u) if afli else [0x0F]
            paps = (sorted(u) + [-1]) if afli else [-1]
            bb, bi, bp = 1 << 60, 0x0F, -1
            for ink in inks:
                for paper in paps:
                    cols[INK], cols[PAPER] = ink, paper
                    c = block_cost(x0, y, cols) + block_cost(x0, y + 1, cols)
                    if c < bb:
                        bb, bi, bp = c, ink, paper
            total += bb
            ip.append((bi, bp))
        return total, ip

    # per-line flibug switch budget (mufflon find_free_register_switches /
    # free_switches_flibug): a colour-table column is a free switch slot on line lp
    # if its main sprite colour is unchanged from lp-1 (or unused, 0xFF); column 0
    # is reserved, so the flibug budget is the free slots in columns 1..5. This caps
    # how many of the 4 flibug colours may change per line, which is what keeps them
    # stable across a region (mufflon's continuity).
    if sprite_tab is not None:
        tab = [[int(sprite_tab[lp][b]) for b in range(6)] for lp in range(101)]
    else:  # no 3rd-colour underlay: every slot is unused (0xFF) -> all free
        tab = [[0xFF] * 6 for _ in range(101)]
    # fsw[lp][col] = 1 if that colour-table column is a free switch slot at lp (the
    # underlay colour is unchanged from lp-1 or unused); free_flibug excludes col 0
    # (reserved), matching mufflon free_switches / free_switches_flibug.
    fsw = [[1 if (lp == 0 or tab[lp][b] == tab[lp - 1][b] or tab[lp][b] == 0xFF) else 0
            for b in range(6)] for lp in range(100)]
    free_flibug = [sum(fsw[lp][1:6]) for lp in range(100)]

    # per-line present colours (mufflon flibug_col_is_used): only colours that
    # actually appear in that line-pair's left 24px are candidates (+ unused). This
    # is mufflon's candidate set and stops the search spending a sprite colour on an
    # absent value (which would render as a full-width streak).
    present = []
    for lp in range(100):
        s = set()
        for yy in (lp * 2, lp * 2 + 1):
            for b in range(3):
                s |= used[yy][b]
        present.append(sorted(s))

    # --- mufflon find_best_colors_flibug, ported (switch-budget continuity) ---
    # Per line-pair, decide which of the 4 sprite colours may CHANGE: a colour can
    # only change where a sprite-colour-table switch is free, found by scanning back
    # to the earliest free slot (find_last_available_switch), and only while keeping
    # 8 switches in reserve for the screen-split pointers (free_switches_max). The
    # changeable colours are searched over the present colours; the rest are pinned
    # to the colour carried from the previous line, then a colour change is
    # propagated forward (so colours stay stable across a region instead of
    # streaking). flibug_optimize then drops any change that doesn't actually help.
    fb_col = [[-1] * 100 for _ in range(4)]  # [channel][line-pair], carried forward
    free_max = sum(sum(fsw[lp]) for lp in range(SPLITSTART, min(SPLITEND + 1, 100)))

    def last_available_switch(lp, ch, free_temp):
        """mufflon find_last_available_switch: earliest line-pair <= lp with a free
        slot, before this channel's colour was last set. Returns (ok, line-pair)."""
        newy, yp = lp + 1, lp
        while yp >= 0:
            if yp != lp and fb_col[ch][yp] >= 0:
                break
            if free_temp[yp] > 0:
                newy = yp
            yp -= 1
        return (newy <= lp), newy

    def line_delta(lp, cols4):
        return line_cost(lp, cols4)[0]

    for lp in range(100):
        y = lp * 2
        free_temp = list(free_flibug)
        test_col = [0, 0, 0, 0]
        free_ypos = [lp + 1] * 4
        cand = [None] * 4   # per-channel candidate colours (search set or single preset)
        free_cols = 0
        for i in range(4):
            ok, ny = last_available_switch(lp, i, free_temp)
            free_ypos[i] = ny
            if ok and free_max - free_cols > 8:   # keep 8 switches for the split pointers
                test_col[i] = 1
                free_temp[ny] -= 1
                free_cols += 1
            preset = -1 if lp == 0 else fb_col[i][lp]
            if test_col[i]:                       # changeable -> search present colours
                pool = [c for c in present[lp] if (y & 7) == 0 or c != 0x0F]
                cand[i] = (pool or [preset if preset >= 0 else 0]) + [-1]
            else:                                 # pinned to the carried colour
                cand[i] = [-1] if ((y & 7) >= 2 and preset == 0x0F) else [preset]
        # coordinate-descent search over the changeable channels (pinned ones fixed),
        # seeded from the carried colours; prefer not to spend a colour on $0f.
        afli = (y & 7) < 2
        best = [(-1 if lp == 0 else fb_col[i][lp]) for i in range(4)]
        for i in range(4):
            if best[i] not in cand[i]:
                best[i] = cand[i][0]
        best_cost = line_delta(lp, best)
        for _ in range(3):
            improved = False
            for i in range(4):
                if len(cand[i]) <= 1:
                    continue
                cc, ccost = best[i], best_cost
                for c in cand[i]:
                    if c == best[i]:
                        continue
                    t = list(best)
                    t[i] = c
                    d = line_delta(lp, t)
                    if d < ccost or (d == ccost and not afli and cc == 0x0F and 0 <= c != 0x0F):
                        ccost, cc = d, c
                if cc != best[i]:
                    best[i], best_cost, improved = cc, ccost, True
            if not improved:
                break
        # flibug_optimize: drop a change (revert to carried colour) if it doesn't help
        for i in range(4):
            if test_col[i]:
                carried = -1 if lp == 0 else fb_col[i][lp]
                t = list(best)
                t[i] = carried
                if line_delta(lp, t) <= best_cost:
                    best[i] = carried
                    test_col[i] = 0
        # propagate each colour forward from its switch line-pair (continuity)
        for i in range(4):
            carried = -1 if lp == 0 else fb_col[i][lp]
            if best[i] != carried:
                for j in range(free_ypos[i], 100):
                    fb_col[i][j] = best[i]
            else:
                fb_col[i][lp] = carried

    fb = [[fb_col[i][lp] for i in range(4)] for lp in range(100)]
    inkpap = [line_cost(lp, fb[lp])[1] for lp in range(100)]

    # render: per-pixel channel choice -> bitmaps + ink/paper
    for lp in range(100):
        cols = [-1] * 10
        cols[FLISPRITE], cols[M1], cols[M2], cols[M3] = fb[lp]
        for dy in (0, 1):
            y = lp * 2 + dy
            for b in range(3):
                cols[INK], cols[PAPER] = inkpap[lp][b]
                x0 = b * 8
                bmp = hspr = mspr = 0
                for k in range(0, 8, 2):
                    _, ca, cb = combo(x0 + k, y, cols)
                    for off, ch in ((0, ca), (1, cb)):
                        bit = k + off
                        if ch == INK:
                            bmp |= 1 << (7 - bit)
                        elif ch == FLISPRITE:
                            hspr |= 1 << (7 - bit)
                        elif ch in _MSPR_BITS and off == 0:
                            mspr |= _MSPR_BITS[ch] << (6 - k)
                logical = (y >> 3) * 320 + x0 + (y & 7)
                body[_bitmap_off(logical)] = bmp
                body[ho[y][b]] = hspr
                body[mo[y][b]] = mspr
            for b in range(3):
                ink, paper = inkpap[lp][b]
                body[NUIFLI_SCRAM[lp] + b] = ((ink & 0xF) << 4) | (paper & 0xF if paper >= 0 else 0)

    for i, ch in enumerate(_CH):
        body[_INIT_OFF[ch]] = fb[0][i] & 0xF

    # colour table (mufflon layout: column base $0400/$0480/...; the generator reads
    # base+1+lp). Without a 3rd-colour underlay the main columns are unused ($0f);
    # with one they already hold the per-line sprite colours. Flibug colour-switches
    # are woven into free slots (columns whose main colour is unchanged here, so the
    # displayer holding it is harmless); pointer switches drive the multiplex.
    base0 = [c - 1 for c in COLOUR_COLS]
    if not has_main:
        for base in base0:
            for lp in range(101):
                body[base + lp] = 0x0F
    main = [[body[base0[c] + lp] for lp in range(101)] for c in range(6)]  # snapshot
    for lp, val in _PTR_SWITCHES.items():
        body[base0[5] + lp] = val
    prev = [-1, -1, -1, -1]
    for lp in range(100):
        changes = [(ch, fb[lp][i] & 0xF) for i, ch in enumerate(_CH)
                   if fb[lp][i] != prev[i] and fb[lp][i] >= 0]
        used = set()
        for ch, colour in changes:
            for col in range(6):
                if col in used or (col == 5 and lp in _PTR_SWITCHES):
                    continue
                if has_main and lp > 0 and main[col][lp] != main[col][lp - 1]:
                    continue  # main colour changes here -> not a free slot
                body[base0[col] + lp] = _SWITCH[ch] | colour
                used.add(col)
                break
        prev = list(fb[lp])
