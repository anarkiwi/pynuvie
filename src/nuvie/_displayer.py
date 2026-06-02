"""Generate a NUVIE per-frame displayer, reproducing NUVIEmaker's generator.

NUVIEmaker builds each frame's displayer (relocated to C64 ``$1000-$1EE3``, 3812
bytes) from the NUFLI ``.nuf``'s 6-column sprite-colour table. The displayer is
unrolled FLI code: 100 per-line-pair blocks that set the six sprite colours, the
FLI ``$d018`` screen base and ``$d011``. The block *structure* (opcodes, the
``$d018``/``$d011`` raster sequence, the four FLI-phase header variants) is
content-independent; only the six per-line-pair colour writes change per frame.

This module ships that structure as ``data/displayer_template.bin`` and patches
the per-block colour/register bytes from a frame's colour table, decoding each
table cell exactly as NUVIEmaker's ``$33b0`` routine does:

* ``hi nibble == 0``  -> normal colour: ``STY $d028+col`` with the cell value;
* ``hi nibble == 1``  -> sprite-position (multiplex) switch: ``LDY #$d4;
  STY $d0(lo)``;
* ``hi nibble >= 5``  -> flibug colour switch: ``STY $d0(hi|$20)`` -> ``$5x``
  ``$d025``, ``$6x`` ``$d026``, ``$7x`` ``$d027``, ``$ex`` ``$d02e``; the LDY
  operand keeps the full cell value (the VIC uses only the low nibble).

Reverse-engineered from the real NUVIEmaker (driven via vice-driver) and verified
byte-exact against its generated displayers for two independent inputs -- see
``research/nuviemaker_flibug/`` (NOTES.md, lv/stripes captures) and
``tests/test_displayer.py``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import List

DISPLAYER_LEN = 0x0EE4  # 3812 bytes ($1000-$1EE3)

# the six NUFLI body offsets of the per-line-pair sprite-colour columns (+ line-pair)
COLOUR_COLS = (0x0401, 0x0481, 0x0801, 0x0881, 0x0C01, 0x0C81)

# per FLI phase (line-pair & 3): block copy-start, and the col-0 colour offset
# within the 40-byte block ($3340 / $3348 in NUVIEmaker's generator).
_PHASE_START = (2, 0, 0, 2)
_PHASE_COL0_OFF = (6, 6, 6, 3)
# colour-operand and STY-register offsets within the 40-byte block (cols 1..5;
# col 0's colour offset is phase-dependent, above). From NUVIEmaker's builder.
_COL_COLOUR_OFF = (None, 0x0B, 0x10, 0x15, 0x1A, 0x1F)
_COL_REG_OFF = (0x08, 0x0D, 0x12, 0x17, 0x1C, 0x21)

# cumulative output offset of each of the 100 blocks (block length = 40 - start).
_BASES: List[int] = []
_p = 0
for _x in range(100):
    _BASES.append(_p)
    _p += 40 - _PHASE_START[_x & 3]


def _decode(value: int, sprite_reg: int):
    """NUVIEmaker ``$33b0``: map a colour-table cell to (LDY operand, STY reg)."""
    hi = value >> 4
    if hi == 0:
        return value, sprite_reg  # normal colour -> STY $d028+col
    if hi == 1:
        return 0xD4, value & 0x0F  # sprite-position switch -> STY $d0(lo)
    return value, 0x20 | hi  # flibug colour switch -> STY $d0(hi|$20)


@lru_cache(maxsize=1)
def _template() -> bytes:
    from .pack import _data_path

    return bytes(_data_path("displayer_template.bin").read_bytes())


def generate(body: bytes) -> bytes:
    """Build the 3812-byte per-frame displayer for a NUFLI ``body`` (the colour
    table at :data:`COLOUR_COLS`). Returns the displayer bytes for C64 ``$1000``."""
    out = bytearray(_template())
    for x in range(100):
        phase = x & 3
        start = _PHASE_START[phase]
        base = _BASES[x]
        col0_off = _PHASE_COL0_OFF[phase]
        for col in range(6):
            v = body[COLOUR_COLS[col] + x]
            colour, reg = _decode(v, 0x28 + col)
            c_off = (col0_off if col == 0 else _COL_COLOUR_OFF[col]) - start
            r_off = _COL_REG_OFF[col] - start
            if 0 <= base + c_off < DISPLAYER_LEN:
                out[base + c_off] = colour
            if 0 <= base + r_off < DISPLAYER_LEN:
                out[base + r_off] = reg
    return bytes(out)
