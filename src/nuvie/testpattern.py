"""Generate a self-contained animated test pattern -- no video file needed.

``frames(n)`` yields ``n`` 320x200 Pillow images that, encoded into a NUVIE and
played, make it obvious the player is running: the 16 C64 colours as vertical
bars, a per-frame binary frame counter, corner registration marks, and a white
block that sweeps across the screen. Use via ``nuvie testpattern`` or
:func:`nuvie.testpattern.build`.
"""

from __future__ import annotations

from typing import Iterator

from .palette import C64_PALETTE

WIDTH, HEIGHT = 320, 200
COUNTER_BITS = 10


def make_frame(i: int):
    """Build test-pattern frame ``i`` as a Pillow ``Image``."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (WIDTH, HEIGHT), C64_PALETTE[0])
    d = ImageDraw.Draw(img)

    # 16 colour bars across the full width.
    bw = WIDTH // 16
    for c in range(16):
        d.rectangle([c * bw, 60, c * bw + bw - 1, 150], fill=C64_PALETTE[c])

    # binary frame counter along the top (white = 1), MSB left, with guard bars.
    bits = [1] + [(i >> b) & 1 for b in range(COUNTER_BITS - 1, -1, -1)] + [1]
    cw = WIDTH // (len(bits) + 1)
    for k, bit in enumerate(bits):
        if bit:
            x0 = (k + 1) * cw - cw // 3
            d.rectangle([x0, 8, x0 + cw // 3, 40], fill=C64_PALETTE[1])

    # corner registration marks.
    for cx, cy in ((6, 6), (WIDTH - 18, 6), (6, HEIGHT - 18), (WIDTH - 18, HEIGHT - 18)):
        d.rectangle([cx, cy, cx + 11, cy + 11], fill=C64_PALETTE[1])

    # a white block sweeping left<->right to show motion.
    span = WIDTH - 40
    pos = i % (2 * span)
    x = pos if pos < span else 2 * span - pos
    d.rectangle([20 + x - 8, 165, 20 + x + 8, 185], fill=C64_PALETTE[1])
    return img


def frames(n: int = 64) -> Iterator:
    """Yield ``n`` test-pattern frames."""
    for i in range(n):
        yield make_frame(i)


def build(out_path: str, n: int = 64, third_colour: bool = False, dither: bool = False,
          flibug: bool = True):
    """Encode an ``n``-frame test pattern into a playable NUVIE ``.reu``.

    The pattern is flat (bars / blocks) so it uses clean two-colour hi-res. With
    ``flibug`` (default) the left-24px edge is generated so it follows the pattern.
    """
    from .pack import build_movie

    return build_movie(frames(n), out_path, third_colour=third_colour, dither=dither,
                       flibug=flibug)
