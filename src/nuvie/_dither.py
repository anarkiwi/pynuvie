"""mufflon's ``prepare()`` colour dithering, ported faithfully.

mufflon's perceptual quality comes mostly from this step: it dithers the image to
the C64 **Pepto** palette with Floyd-Steinberg error diffusion performed in **YUV**
space using per-channel weights (the makenuvie default ``--prep_mode yuv
--weight_u 1 --weight_v 0.5``). The error is weighted before distribution and the
nearest-colour search is weighted too -- reproduced exactly here so output matches
mufflon's. The result is an image whose pixels are Pepto colours, ready for the
NUFLI encoder. Validated against mufflon's own output on the reference player.
"""

from __future__ import annotations

from .palette import C64_PALETTE as PEPTO_PALETTE  # now the Pepto values mufflon uses

# YUV channel weights (mufflon weights_yuv with makenuvie's -u 1 -v 0.5).
_W = (1.0, 1.0, 0.5)
WIDTH, HEIGHT = 320, 200


def _rgb_to_yuv(arr):
    import numpy as np

    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    y = 0.299 * r + 0.587 * g + 0.114 * b
    return np.stack([y, (b - y) * 0.493, (r - y) * 0.877], axis=-1)


def dither(img):
    """Return ``img`` (resized to 320x200) dithered to the Pepto palette via
    mufflon's YUV Floyd-Steinberg. Pixels are exact Pepto RGB colours."""
    import numpy as np
    from PIL import Image

    arr = np.asarray(img.convert("RGB").resize((WIDTH, HEIGHT)), dtype=np.float64)
    data = _rgb_to_yuv(arr)
    pal_rgb = np.array(PEPTO_PALETTE, dtype=np.float64)
    pal = _rgb_to_yuv(pal_rgb)
    w = np.array(_W)
    out = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    for y in range(HEIGHT):
        row = data[y]
        nxt = data[y + 1] if y + 1 < HEIGHT else None
        for x in range(WIDTH):
            v = row[x]
            c = int((np.abs(v - pal) * w).sum(1).argmin())
            out[y, x] = c
            qe = (v - pal[c]) * w  # weighted error (mufflon's prepare quirk)
            if x + 1 < WIDTH:
                row[x + 1] += 7 / 16 * qe
            if nxt is not None:
                if x - 1 >= 0:
                    nxt[x - 1] += 3 / 16 * qe
                nxt[x] += 5 / 16 * qe
                if x + 1 < WIDTH:
                    nxt[x + 1] += 1 / 16 * qe
    return Image.fromarray(pal_rgb[out].astype(np.uint8), "RGB")
