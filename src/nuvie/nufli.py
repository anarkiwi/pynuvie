"""NUFLI still-image decoding.

NUFLI ("New Underlayed Flexible Line Interpretation", by Crossbow/Crest) is the
320x200 hi-res C64 picture format used for every NUVIE frame. A frame is FLI on
the even raster lines (a fresh ink/paper colour pair for each 8x2 block) plus a
hires sprite underlay that adds a third colour and recolours the odd lines. All
16 C64 colours are available across a frame.

The memory layout used here was taken directly from Crest's ``mufflon`` encoder
source (``mufflon.c`` / ``mufflon.h``), which is the authoritative description of
where each byte of a NUFLI image lives. A standalone NUFLI ``.prg`` ("``.nuf``")
loads to ``$2000`` and occupies ``$2000-$7A00`` (0x5a00 bytes), the last ~0x4b0
of which is a self-contained displayer; NUVIE strips the displayer and keeps only
the graphics bytes (see :mod:`nuvie.reu`).

This module decodes the *graphics* into a 320x200 grid of C64 palette indices.
The base decode (hi-res bitmap + the per-8x2 FLI screen-RAM colours) is exact for
hi-res content; the sprite-underlay colours are applied as a refinement.

All offsets below are **relative to $2000** (i.e. indices into the NUFLI body
with the 2-byte load address removed), because ``mufflon`` builds its result
buffer at that base.
"""

from __future__ import annotations

from typing import List, Optional

from .palette import C64_PALETTE

WIDTH, HEIGHT = 320, 200
NUFLI_LOAD_ADDR = 0x2000
NUFLI_BODY_SIZE = 0x5A00  # $2000..$7A00

# Hi-res bitmap is stored in two contiguous runs (mufflon.c render()):
#   body[0x4000:0x5400] = logical bitmap[0x0000:0x1400]   (first 5120 bytes)
#   body[0x1400:0x1f40] = logical bitmap[0x1400:0x1f40]   (next  2880 bytes)
_BITMAP_HI = (0x4000, 0x1400)  # (offset, length)
_BITMAP_LO = (0x1400, 0x0B40)

# Screen-RAM (ink<<4 | paper) address for each of the 100 even-line 8x2 rows,
# verbatim from mufflon.h `nuifli_scram`. Index = y // 2; add the column (0..39).
NUIFLI_SCRAM: List[int] = [
    0x3C00, 0x3800, 0x3400, 0x3000, 0x2C28, 0x2828, 0x2428, 0x2028,
    0x3C50, 0x3850, 0x3450, 0x3050, 0x2C78, 0x2878, 0x2478, 0x2078,
    0x3CA0, 0x38A0, 0x34A0, 0x30A0, 0x2CC8, 0x28C8, 0x24C8, 0x20C8,
    0x3CF0, 0x38F0, 0x34F0, 0x30F0, 0x2D18, 0x2918, 0x2518, 0x2118,
    0x3D40, 0x3940, 0x3540, 0x3140, 0x2D68, 0x2968, 0x2568, 0x2168,
    0x3D90, 0x3990, 0x3590, 0x3190, 0x2DB8, 0x29B8, 0x25B8, 0x21B8,
    0x3DE0, 0x39E0, 0x35E0, 0x31E0, 0x2E08, 0x2A08, 0x2608, 0x2208,
    0x3E30, 0x3A30, 0x3630, 0x3230, 0x2E58, 0x2A58, 0x2658, 0x2258,
    0x0280, 0x0680, 0x0A80, 0x0E80, 0x02A8, 0x06A8, 0x0AA8, 0x0EA8,
    0x02D0, 0x06D0, 0x0AD0, 0x0ED0, 0x02F8, 0x06F8, 0x0AF8, 0x0EF8,
    0x0320, 0x0720, 0x0B20, 0x0F20, 0x0748, 0x0B48, 0x0F48, 0x0348,
    0x0770, 0x0B70, 0x0F70, 0x0370, 0x0798, 0x0B98, 0x0F98, 0x0398,
    0x07C0, 0x0BC0, 0x0FC0, 0x03C0,
]


def _bitmap_bit(bitmap: bytes, x: int, y: int) -> int:
    """Standard C64 hi-res bitmap pixel: 1 == ink, 0 == paper."""
    cell = (y >> 3) * 320 + (x >> 3) * 8 + (y & 7)
    return (bitmap[cell] >> (7 - (x & 7))) & 1


class NufliImage:
    """A NUFLI image, addressed as a C64 memory image based at ``$2000``.

    Construct from a standalone ``.nuf``/NUFLI ``.prg`` with :meth:`from_prg`, or
    from the graphics regions held in a NUVIE REU slot (see :mod:`nuvie.reu`).
    """

    def __init__(self, body: bytes):
        if len(body) < NUFLI_BODY_SIZE:
            body = bytes(body) + bytes(NUFLI_BODY_SIZE - len(body))
        self.body = bytes(body)

    @classmethod
    def from_prg(cls, data: bytes) -> "NufliImage":
        """Parse a NUFLI ``.prg`` whose first two bytes are the ``$2000`` load addr."""
        if len(data) >= 2 and data[0] | (data[1] << 8) == NUFLI_LOAD_ADDR:
            data = data[2:]
        return cls(data)

    @classmethod
    def from_image(cls, img) -> "NufliImage":
        """Encode a Pillow image into a NUFLI graphics image (hi-res, per-8x2
        two colours -- no sprite-underlay third colour). Round-trips exactly with
        :meth:`decode_indices`. This is the pure-Python, mufflon-free NUFLI encoder.
        """
        from ._hires import encode_hires

        bitmap, screen = encode_hires(img)
        o1, l1 = _BITMAP_HI
        o2, l2 = _BITMAP_LO
        body = bytearray(NUFLI_BODY_SIZE)
        body[o1 : o1 + l1] = bitmap[0:l1]
        body[o2 : o2 + l2] = bitmap[l1 : l1 + l2]
        for by in range(len(screen)):
            for cx in range(40):
                ink, paper = screen[by][cx]
                body[NUIFLI_SCRAM[by] + cx] = ((ink & 0xF) << 4) | (paper & 0xF)
        return cls(bytes(body))

    def to_prg(self) -> bytes:
        """Serialise as a NUFLI graphics ``.prg`` (2-byte ``$2000`` load address +
        body). Note: this carries graphics only, not a displayer routine."""
        return bytes([NUFLI_LOAD_ADDR & 0xFF, NUFLI_LOAD_ADDR >> 8]) + self.body

    def bitmap(self) -> bytes:
        """The logical 8000-byte hi-res bitmap, reassembled from its two runs."""
        o1, l1 = _BITMAP_HI
        o2, l2 = _BITMAP_LO
        return self.body[o1:o1 + l1] + self.body[o2:o2 + l2]

    def screen_byte(self, col: int, line_pair: int) -> int:
        """Raw screen-RAM byte (ink<<4 | paper) for column ``col`` (0..39),
        ``line_pair`` 0..99 (i.e. screen row ``y // 2``)."""
        return self.body[NUIFLI_SCRAM[line_pair] + col]

    def decode_indices(self) -> List[List[int]]:
        """Decode to a ``HEIGHT`` x ``WIDTH`` grid of C64 palette indices.

        Uses the hi-res bitmap plus the per-8x2 FLI screen-RAM ink/paper colours.
        This is exact for hi-res content; sprite-underlay colours (an extra colour
        and odd-line recolouring near the left edge) are not yet applied.
        """
        bitmap = self.bitmap()
        out: List[List[int]] = []
        for y in range(HEIGHT):
            lp = y >> 1
            row = [0] * WIDTH
            for col in range(40):
                sb = self.body[NUIFLI_SCRAM[lp] + col]
                ink, paper = (sb >> 4) & 0xF, sb & 0xF
                base = col * 8
                for px in range(8):
                    x = base + px
                    row[x] = ink if _bitmap_bit(bitmap, x, y) else paper
            out.append(row)
        return out

    def to_image(self, palette: Optional[List] = None):
        """Render to a Pillow ``Image`` (requires the optional ``Pillow`` dep)."""
        from PIL import Image

        pal = palette or C64_PALETTE
        img = Image.new("RGB", (WIDTH, HEIGHT))
        px = img.load()
        for y, row in enumerate(self.decode_indices()):
            for x, idx in enumerate(row):
                px[x, y] = pal[idx]
        return img
