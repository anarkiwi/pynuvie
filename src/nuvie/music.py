"""Read SID music for a NUVIE soundtrack from an external CSV.

NUVIE stores music as a stream of SID register dumps: ``SID_REGS_PER_FRAME`` (25)
register values for every 1/50 s tick (see :mod:`nuvie.reu`). That maps directly
onto a CSV -- one row per tick, 25 integer columns (the 25 writable SID registers
``$D400..$D418``), values ``0..255``. Decimal or ``0x``-prefixed hex are accepted;
a non-numeric first row is treated as a header and skipped, and blank rows ignored.

Use the result with :meth:`nuvie.reu.Nuvie.set_music`, e.g.::

    movie.set_music(read_sid_csv("tune.csv"))
"""

from __future__ import annotations

import csv

from .reu import SID_REGS_PER_FRAME


def read_sid_csv(path: str) -> bytes:
    """Parse a CSV of SID register dumps into a flat NUVIE music byte stream.

    Returns ``SID_REGS_PER_FRAME * ticks`` bytes. Raises ``ValueError`` on a row
    whose column count is wrong or whose values are out of the ``0..255`` range.
    """
    out = bytearray()
    with open(path, newline="", encoding="utf-8") as f:
        for lineno, row in enumerate(csv.reader(f), start=1):
            cells = [c.strip() for c in row if c.strip()]
            if not cells:
                continue
            try:
                vals = [int(c, 0) for c in cells]
            except ValueError as exc:
                if lineno == 1:
                    continue  # header row
                raise ValueError(f"row {lineno}: non-integer SID register value") from exc
            if len(vals) != SID_REGS_PER_FRAME:
                raise ValueError(
                    f"row {lineno}: expected {SID_REGS_PER_FRAME} values, got {len(vals)}"
                )
            if any(not 0 <= v <= 255 for v in vals):
                raise ValueError(f"row {lineno}: SID register value out of range 0..255")
            out.extend(vals)
    if not out:
        raise ValueError(f"{path}: no SID frames found")
    return bytes(out)
