"""Encode NUFLI's third colour: the six main hi-res sprite underlay.

Each of the six double-width sprites covers 48px (six char columns) and carries
one colour per line-pair. Where the hi-res bitmap is paper (bit 0) and the
sprite bit is set, that sprite colour shows -- giving a third colour per 8x2
block. This module chooses, for each sprite-region x line-pair, the colour that
best repairs the paper pixels, and sets the sprite bits accordingly.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .palette import C64_PALETTE

WIDTH, HEIGHT = 320, 200
FLIBUG_WIDTH = 24
SPRITE_W = 48
N_SPRITES = 6


def _d2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def encode_sprites(px, bitmap_bit, screen) -> Tuple[Dict, List[List[int]]]:
    """Return (sprite_bytes, sprite_cols).

    ``sprite_bytes[(y, col)]`` is the sprite-bitmap byte for col 0..17 (sprite =
    col//3); ``sprite_cols[sprite][line_pair]`` is the chosen palette colour.
    ``px`` is a pixel accessor, ``bitmap_bit(x, y)`` the chosen hi-res bit,
    ``screen[lp][cx]`` the (ink, paper) pair.
    """
    sprite_bytes: Dict[Tuple[int, int], int] = {}
    sprite_cols = [[0] * (HEIGHT // 2) for _ in range(N_SPRITES)]
    for s in range(N_SPRITES):
        x0 = FLIBUG_WIDTH + s * SPRITE_W
        for lp in range(HEIGHT // 2):
            # gather paper pixels in this 48x2 region and the cost of leaving them
            paper = []  # (w, x, y, rgb, paper_rgb)
            for w in range(24):  # 24 sprite bits, each 2px wide
                for sub in range(2):
                    x = x0 + w * 2 + sub
                    if x >= WIDTH:
                        continue
                    cx = x // 8
                    for y in (lp * 2, lp * 2 + 1):
                        if not bitmap_bit(x, y):
                            paper.append((w, C64_PALETTE[screen[lp][cx][1]], px[x, y]))
            if not paper:
                continue
            # pick the third colour that most reduces error over those pixels
            best_c, best_gain = -1, 0
            for c in range(16):
                cc = C64_PALETTE[c]
                gain = sum(max(0, _d2(rgb, prgb) - _d2(rgb, cc)) for _, prgb, rgb in paper)
                if gain > best_gain:
                    best_gain, best_c = gain, c
            if best_c < 0:
                continue
            sprite_cols[s][lp] = best_c
            cc = C64_PALETTE[best_c]
            # set sprite bit w when, for its covered paper pixels, the 3rd colour wins
            for w in range(24):
                votes = win = 0
                for ww, prgb, rgb in paper:
                    if ww == w:
                        votes += 1
                        if _d2(rgb, cc) < _d2(rgb, prgb):
                            win += 1
                if votes and win * 2 >= votes:
                    col = s * 3 + w // 8
                    for y in (lp * 2, lp * 2 + 1):
                        k = (y, col)
                        sprite_bytes[k] = sprite_bytes.get(k, 0) | (1 << (7 - (w & 7)))
    return sprite_bytes, sprite_cols
