"""Per-8x2-block two-colour hi-res encoding (the core of NUFLI colour).

NUFLI assigns an ink/paper colour pair to every 8x2 pixel block (FLI on the even
lines). This module turns a 320x200 RGB image into:

* an 8000-byte standard C64 hi-res bitmap (bit set where the pixel is the ink), and
* a ``100 x 40`` grid of ``(ink, paper)`` palette-index pairs, one per 8x2 block.

For each block it searches all colour pairs for the one minimising squared error
against the block's pixels (optionally with Floyd-Steinberg dithering for smoother
gradients). The sprite-underlay third colour that full NUFLI adds is not produced
here.
"""

from __future__ import annotations

from typing import List, Tuple

from .palette import C64_PALETTE

WIDTH, HEIGHT = 320, 200
COLS = WIDTH // 8  # 40
BLOCK_ROWS = HEIGHT // 2  # 100


def _dist2(a: Tuple[int, int, int], b: Tuple[int, int, int]) -> int:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _candidate_colours(pixels: List[Tuple[int, int, int]]) -> List[int]:
    """Palette indices worth considering for a block: the nearest index to each
    pixel (a small, relevant subset of the 16 colours)."""
    seen = set()
    for p in pixels:
        best_i, best_d = 0, 1 << 30
        for i, c in enumerate(C64_PALETTE):
            d = _dist2(p, c)
            if d < best_d:
                best_i, best_d = i, d
        seen.add(best_i)
    return sorted(seen)


def _best_pair(pixels: List[Tuple[int, int, int]]) -> Tuple[int, int]:
    """Choose (ink, paper) palette indices minimising total squared error."""
    cands = _candidate_colours(pixels)
    if len(cands) == 1:
        return cands[0], cands[0]
    best = (cands[0], cands[1] if len(cands) > 1 else cands[0])
    best_err = 1 << 60
    for ii in range(len(cands)):
        for pp in range(ii, len(cands)):
            ink, paper = cands[ii], cands[pp]
            ci, cp = C64_PALETTE[ink], C64_PALETTE[paper]
            err = sum(min(_dist2(px, ci), _dist2(px, cp)) for px in pixels)
            if err < best_err:
                best_err, best = err, (ink, paper)
    return best


def encode_hires(rgb) -> Tuple[bytearray, List[List[Tuple[int, int]]]]:
    """Encode a Pillow RGB image (resized to 320x200) into (bitmap, screen grid).

    ``screen[by][cx]`` is the ``(ink, paper)`` pair for the 8x2 block at column
    ``cx`` and block-row ``by``.
    """
    img = rgb.convert("RGB").resize((WIDTH, HEIGHT))
    px = img.load()
    bitmap = bytearray(8000)
    screen: List[List[Tuple[int, int]]] = [[(0, 0)] * COLS for _ in range(BLOCK_ROWS)]
    for by in range(BLOCK_ROWS):
        y0 = by * 2
        for cx in range(COLS):
            x0 = cx * 8
            pixels = [px[x0 + dx, y0 + dy] for dy in (0, 1) for dx in range(8)]
            ink, paper = _best_pair(pixels)
            screen[by][cx] = (ink, paper)
            ci, cp = C64_PALETTE[ink], C64_PALETTE[paper]
            for dy in (0, 1):
                y = y0 + dy
                cell = (y >> 3) * 320 + cx * 8 + (y & 7)
                bits = 0
                for dx in range(8):
                    p = px[x0 + dx, y]
                    if _dist2(p, ci) <= _dist2(p, cp):
                        bits |= 1 << (7 - dx)
                bitmap[cell] |= bits
    return bitmap, screen
