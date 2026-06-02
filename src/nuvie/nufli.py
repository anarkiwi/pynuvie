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
NUIFLI_SCRAM: List[int] = [int(v, 16) for v in """
    3C00 3800 3400 3000 2C28 2828 2428 2028
    3C50 3850 3450 3050 2C78 2878 2478 2078
    3CA0 38A0 34A0 30A0 2CC8 28C8 24C8 20C8
    3CF0 38F0 34F0 30F0 2D18 2918 2518 2118
    3D40 3940 3540 3140 2D68 2968 2568 2168
    3D90 3990 3590 3190 2DB8 29B8 25B8 21B8
    3DE0 39E0 35E0 31E0 2E08 2A08 2608 2208
    3E30 3A30 3630 3230 2E58 2A58 2658 2258
    0280 0680 0A80 0E80 02A8 06A8 0AA8 0EA8
    02D0 06D0 0AD0 0ED0 02F8 06F8 0AF8 0EF8
    0320 0720 0B20 0F20 0748 0B48 0F48 0348
    0770 0B70 0F70 0370 0798 0B98 0F98 0398
    07C0 0BC0 0FC0 03C0
""".split()]


# --- sprite underlay (the NUFLI third colour) ---
# FLI bug width: the left 24px are covered by the "flibug" sprites; the six main
# double-width hi-res sprites tile x in [24, 312), 48px each, and provide a third
# colour: where the bitmap bit is 0 and the sprite bit is 1, the sprite's colour
# shows instead of paper.
FLIBUG_WIDTH = 0x18  # 24
MAIN_SPRITE_X0 = FLIBUG_WIDTH
MAIN_SPRITE_W = 48  # double-width hi-res sprite
N_MAIN_SPRITES = 6

# Per-line-pair colour table base for each main sprite (mufflon render()).
_SPRITE_COLOUR_BASE = [0x0400, 0x0480, 0x0800, 0x0880, 0x0C00, 0x0C80]

# Sprite-bitmap row addresses (mufflon.h `nuifli_spram`), index = y // 2.
NUIFLI_SPRAM: List[int] = (
    [0x3E80, 0x3A80, 0x3680, 0x3280, 0x2E80, 0x2A80, 0x2680, 0x2280] * 8
    + [0x0100, 0x0500, 0x0900, 0x0D00] * 5
    + [0x0500, 0x0900, 0x0D00, 0x0100] * 4
)


def _sprite_addr_map() -> dict:
    """Map (y, col) -> body offset of the sprite-bitmap byte, replicating
    mufflon's render() addressing (col 0..17 == 6 sprites x 3 bytes)."""
    out = {}
    row = 5
    ncols = (WIDTH - 8 - FLIBUG_WIDTH) // 8 // 2  # 18
    for y in range(HEIGHT):
        for col in range(ncols):
            srow = (row + (col % 3)) & 0x3F
            if col >= 15 and y < 128:
                addr = 0x5400 + ((((y // 2) & 7) ^ 7) * 0x40) + srow
            else:
                addr = NUIFLI_SPRAM[y // 2] + srow + (col // 3) * 0x40
            out[(y, col)] = addr
        if (y & 1) == 0:
            row += 3
        if row > 0x3F:
            row &= 0x3F
        elif row == 0x3F:
            row = 0
    return out


_SPRITE_MAP = None


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
        # set by from_image(flibug=True): the body carries a generated flibug plane,
        # so the packer regenerates the per-frame displayer from its colour table.
        self.flibug = False

    @classmethod
    def from_prg(cls, data: bytes) -> "NufliImage":
        """Parse a NUFLI ``.prg`` whose first two bytes are the ``$2000`` load addr."""
        if len(data) >= 2 and data[0] | (data[1] << 8) == NUFLI_LOAD_ADDR:
            data = data[2:]
        return cls(data)

    @classmethod
    def from_image(
        cls,
        img,
        backend: str = "clean",
        flibug: bool = True,
        cohere: float = 600.0,
        mufflon_bin=None,
    ) -> "NufliImage":
        """Encode a Pillow image into a NUFLI graphics image.

        Two backends:

        * ``backend="clean"`` (default, pure-Python, no external tools): pynuvie's
          own FLI-structure-aware encoder (:mod:`nuvie._clean`) -- co-designs the
          per-cell ink/paper + per-region sprite colour with a 2px-pair
          error-diffusion dither and vertical coherence (``cohere``).
        * ``backend="mufflon"``: shell out to Crest's real ``mufflon`` binary (see
          :mod:`nuvie._mufflon_driver`; set ``NUVIE_MUFFLON`` or pass
          ``mufflon_bin``). The original tool's encoding, packed by pynuvie.

        With ``flibug`` the leftmost-24px sprite plane is generated so the left edge
        renders cleanly instead of the VIC FLI-bug corruption (for ``clean`` via
        :mod:`nuvie._flibug`; for ``mufflon`` via its ``--flibug``). ``build_slot``
        regenerates the per-frame displayer from the body's colour table.
        """
        if backend == "mufflon":
            from ._mufflon_driver import encode_via_mufflon

            body = bytearray(encode_via_mufflon(img, flibug=flibug, mufflon_bin=mufflon_bin))
        elif backend == "clean":
            import numpy as np

            from ._clean import encode_clean

            rgb = np.asarray(img.convert("RGB").resize((WIDTH, HEIGHT)), dtype=np.uint8)
            body = bytearray(encode_clean(rgb, cohere=cohere))
            if flibug:
                from ._flibug import encode_flibug

                encode_flibug(img, body, has_main=True)
        else:
            raise ValueError(f"unknown backend {backend!r} (expected 'clean' or 'mufflon')")
        obj = cls(bytes(body))
        obj.flibug = flibug
        return obj

    def to_prg(self) -> bytes:
        """Serialise as a NUFLI graphics ``.prg`` (2-byte ``$2000`` load address +
        body). Note: this carries graphics only, not a displayer routine."""
        return bytes([NUFLI_LOAD_ADDR & 0xFF, NUFLI_LOAD_ADDR >> 8]) + self.body

    def bitmap(self) -> bytes:
        """The logical 8000-byte hi-res bitmap, reassembled from its two runs."""
        o1, l1 = _BITMAP_HI
        o2, l2 = _BITMAP_LO
        return self.body[o1 : o1 + l1] + self.body[o2 : o2 + l2]

    def screen_byte(self, col: int, line_pair: int) -> int:
        """Raw screen-RAM byte (ink<<4 | paper) for column ``col`` (0..39),
        ``line_pair`` 0..99 (i.e. screen row ``y // 2``)."""
        return self.body[NUIFLI_SCRAM[line_pair] + col]

    def decode_indices(self, sprites: bool = True) -> List[List[int]]:
        """Decode to a ``HEIGHT`` x ``WIDTH`` grid of C64 palette indices.

        Combines the hi-res bitmap, the per-8x2 FLI screen-RAM ink/paper, and (when
        ``sprites`` is set) the six main hi-res sprites that provide NUFLI's third
        colour across ``x`` in [24, 312). Validated against mufflon's own rendering
        to the dithering-noise floor over that region. The left 24px "flibug" edge
        (a multicolour + hi-res sprite pair with per-line colour switching) is not
        decoded, so those columns fall back to the raw bitmap colours.
        """
        global _SPRITE_MAP
        bitmap = self.bitmap()
        if sprites and _SPRITE_MAP is None:
            _SPRITE_MAP = _sprite_addr_map()
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
            if sprites:
                self._apply_sprites(row, y, bitmap)
            out.append(row)
        return out

    def _apply_sprites(self, row: List[int], y: int, bitmap: bytes) -> None:
        """Overlay the six main hi-res sprites (third colour) onto a decoded row."""
        lp = y >> 1
        end = MAIN_SPRITE_X0 + N_MAIN_SPRITES * MAIN_SPRITE_W
        for x in range(MAIN_SPRITE_X0, min(end, WIDTH)):
            if _bitmap_bit(bitmap, x, y):
                continue  # foreground hi-res pixel wins over the sprite plane
            rel = x - MAIN_SPRITE_X0
            sprite = rel // MAIN_SPRITE_W
            within = (rel % MAIN_SPRITE_W) // 2  # 0..23, double-width
            byte = self.body[_SPRITE_MAP[(y, sprite * 3 + within // 8)]]
            if (byte >> (7 - (within & 7))) & 1:
                row[x] = self.body[_SPRITE_COLOUR_BASE[sprite] + lp] & 0xF

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

    def to_image_nosprites(self, palette: Optional[List] = None):
        """Render without the sprite underlay (hi-res + FLI screen only)."""
        from PIL import Image

        pal = palette or C64_PALETTE
        img = Image.new("RGB", (WIDTH, HEIGHT))
        px = img.load()
        for y, r in enumerate(self.decode_indices(sprites=False)):
            for x, idx in enumerate(r):
                px[x, y] = pal[idx]
        return img
