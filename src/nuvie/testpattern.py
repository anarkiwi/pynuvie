"""Generate a self-contained animated test pattern -- no video file needed.

The pattern is a smooth gradient field, which is the hardest thing for a 16-colour
FLI encoder to reproduce and so the clearest showcase of its dithering. ``style``
picks what the field shows:

* ``"colour"`` -- a hue sweep across the screen over a vertical light->dark ramp,
  so the encoder has to dither between bracketing C64 colours everywhere;
* ``"greyscale"`` -- a black->white luma ramp with a soft sine ripple, showing how
  the five C64 greys plus dithering approximate a continuous tone.

The field drifts a little each frame (so motion is visible) and carries a binary
frame counter along the top. Use via ``nuvie testpattern`` or
:func:`nuvie.testpattern.build`.
"""

from __future__ import annotations

from typing import Iterator

import numpy as np

WIDTH, HEIGHT = 320, 200
COUNTER_BITS = 10


def _hsv_to_rgb(h, s, v):
    """Vectorised HSV->RGB on arrays in [0,1]; returns (..,3) uint8."""
    i = np.floor(h * 6.0).astype(int)
    f = h * 6.0 - i
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    i = i % 6
    r = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [v, q, p, p, t, v])
    g = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [t, v, v, q, p, p])
    b = np.select([i == 0, i == 1, i == 2, i == 3, i == 4, i == 5], [p, p, t, v, v, q])
    return (np.stack([r, g, b], -1) * 255).astype(np.uint8)


def _field(i: int, style: str) -> np.ndarray:
    """The (200,320,3) gradient field for frame ``i``."""
    xs = np.linspace(0, 1, WIDTH)[None, :]
    ys = np.linspace(0, 1, HEIGHT)[:, None]
    phase = (i % 100) / 100.0
    if style == "greyscale":
        ramp = (xs + 0.08 * np.sin((ys + phase) * 2 * np.pi)) % 1.0
        g = (ramp * np.ones((HEIGHT, 1)) * 255).astype(np.uint8)
        return np.repeat(g[:, :, None], 3, axis=2)
    hue = (xs + phase) % 1.0 * np.ones((HEIGHT, 1))
    val = 0.25 + 0.75 * (1 - ys) * np.ones((1, WIDTH))
    sat = 0.4 + 0.6 * ys * np.ones((1, WIDTH))
    return _hsv_to_rgb(hue, sat, val)


def make_frame(i: int, style: str = "colour"):
    """Build showcase frame ``i`` for ``style`` as a Pillow ``Image``."""
    from PIL import Image, ImageDraw

    img = Image.fromarray(_field(i, style), "RGB")
    d = ImageDraw.Draw(img)

    # binary frame counter along the top (white = 1), MSB left, with guard bars.
    bits = [1] + [(i >> b) & 1 for b in range(COUNTER_BITS - 1, -1, -1)] + [1]
    cw = WIDTH // (len(bits) + 1)
    for k, bit in enumerate(bits):
        if bit:
            x0 = (k + 1) * cw - cw // 3
            d.rectangle([x0, 6, x0 + cw // 3, 22], fill=(255, 255, 255))
    return img


def frames(n: int = 64, style: str = "colour") -> Iterator:
    """Yield ``n`` showcase frames in ``style`` (``"colour"`` or ``"greyscale"``)."""
    for i in range(n):
        yield make_frame(i, style)


def build(out_path: str, n: int = 64, style: str = "colour", backend: str = "clean"):
    """Encode an ``n``-frame showcase test pattern into a playable NUVIE ``.reu``."""
    from .pack import build_movie

    return build_movie(frames(n, style), out_path, backend=backend)
