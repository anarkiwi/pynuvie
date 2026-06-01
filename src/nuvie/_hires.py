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


def dither_to_palette(rgb):
    """Dither an image to the C64 Pepto palette the way mufflon's ``prepare()``
    does -- YUV-space Floyd-Steinberg with weighted error (see
    :mod:`nuvie._dither`). This is the dominant contributor to mufflon's
    perceptual quality; output pixels are exact Pepto colours."""
    from ._dither import dither

    return dither(rgb)


def _encode_hires_numpy(img):
    """Vectorised encode_hires: pick the optimal ink/paper pair per 8x2 block and
    build the bitmap, all in numpy. ~50x faster than the pure-Python path."""
    import numpy as np

    pal = np.array(C64_PALETTE, dtype=np.int32)  # (16,3)
    arr = np.asarray(img, dtype=np.int32)  # (H,W,3)
    # squared distance from every pixel to every palette colour -> (H,W,16)
    d = ((arr[:, :, None, :] - pal[None, None, :, :]) ** 2).sum(axis=3)
    # group into 8x2 blocks: (BLOCK_ROWS, COLS, 16 pixels, 16 palette)
    db = (
        d.reshape(BLOCK_ROWS, 2, COLS, 8, 16)
        .transpose(0, 2, 1, 3, 4)
        .reshape(BLOCK_ROWS * COLS, 16, 16)
    )
    # for every (ink,paper) pair, error = sum over pixels of min(d_ink, d_paper)
    pairs = [(i, j) for i in range(16) for j in range(i, 16)]
    errs = np.empty((db.shape[0], len(pairs)), dtype=np.int64)
    for p, (i, j) in enumerate(pairs):
        errs[:, p] = np.minimum(db[:, :, i], db[:, :, j]).sum(axis=1)
    best = errs.argmin(axis=1)
    pair_arr = np.array(pairs)
    ink = pair_arr[best, 0].reshape(BLOCK_ROWS, COLS)
    paper = pair_arr[best, 1].reshape(BLOCK_ROWS, COLS)
    screen = [[(int(ink[by, cx]), int(paper[by, cx])) for cx in range(COLS)]
              for by in range(BLOCK_ROWS)]
    # per-pixel ink/paper, then bit = pixel closer to ink
    ink_px = np.repeat(np.repeat(ink, 2, axis=0), 8, axis=1)  # (H,W)
    paper_px = np.repeat(np.repeat(paper, 2, axis=0), 8, axis=1)
    d_ink = np.take_along_axis(d, ink_px[:, :, None], axis=2)[:, :, 0]
    d_paper = np.take_along_axis(d, paper_px[:, :, None], axis=2)[:, :, 0]
    mask = d_ink <= d_paper  # (H,W) bool, True == ink
    # pack to C64 hi-res byte order: bitmap[(y>>3)*320 + (x>>3)*8 + (y&7)]
    blk = mask.reshape(25, 8, COLS, 8)  # (cy, r, cx, bit)
    weights = (1 << np.arange(7, -1, -1)).astype(np.uint16)
    bytes_ = (blk * weights).sum(axis=3).astype(np.uint8)  # (cy, r, cx)
    bitmap = bytearray(bytes_.transpose(0, 2, 1).reshape(-1).tobytes())  # (cy, cx, r)
    return bitmap, screen


def encode_hires(rgb, dither: bool = False) -> Tuple[bytearray, List[List[Tuple[int, int]]]]:
    """Encode a Pillow RGB image (resized to 320x200) into (bitmap, screen grid).

    ``screen[by][cx]`` is the ``(ink, paper)`` pair for the 8x2 block at column
    ``cx`` and block-row ``by``. With ``dither`` the image is Floyd-Steinberg
    dithered to the C64 palette first. Uses numpy when available (much faster),
    else a pure-Python fallback.
    """
    img = dither_to_palette(rgb) if dither else rgb.convert("RGB").resize((WIDTH, HEIGHT))
    try:
        return _encode_hires_numpy(img)
    except ImportError:
        pass
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
