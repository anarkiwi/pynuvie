"""How a NUVIE frame's bytes are streamed into the C64.

The reference player (``nuvieplayer1.0.prg``) does not display a frame from a
single contiguous buffer; it issues a series of REU->C64 DMA transfers that
scatter the 21840-byte slot across the C64's memory into the layout its FLI
displayer expects (bitmap, FLI screen RAMs, sprite data, colour). This module
ships the empirically-derived map of those transfers, as a list of runs
``(slot_offset, c64_address, length)``.

The map was recovered by playing marker REUs in the real player and observing
where each slot byte landed (see ``docs/FORMAT.md``). It lets tools reconstruct
the C64 memory image of a frame for analysis.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import List

try:
    from importlib.resources import files

    def _load_raw() -> list:
        return json.loads((files("nuvie.data") / "slotmap.json").read_text())
except Exception:  # pragma: no cover
    import os

    def _load_raw() -> list:
        here = os.path.join(os.path.dirname(__file__), "data", "slotmap.json")
        with open(here) as f:
            return json.load(f)


from .reu import PART1_SIZE, PART2_BASE


def bank_offset_to_slot_index(off: int) -> int:
    """Convert a bank-relative REU offset to an index into the 21840-byte
    part1+part2 frame slot array."""
    if off < PART1_SIZE:
        return off  # part 1
    return PART1_SIZE + (off - PART2_BASE)  # part 2


@dataclass(frozen=True)
class Run:
    """A contiguous DMA transfer: ``length`` bytes starting at index ``slot``
    of the 21840-byte frame slot, copied to C64 address ``c64``."""

    slot: int
    c64: int
    length: int


@lru_cache(maxsize=1)
def runs() -> List[Run]:
    """The slot->C64 transfer runs used by the reference player.

    ``slot`` is an index into the 21840-byte part1+part2 frame slot."""
    return [Run(bank_offset_to_slot_index(r["slot"]), r["c64"], r["len"]) for r in _load_raw()]


def coverage() -> int:
    """Total number of slot bytes covered by the known map."""
    return sum(r.length for r in runs())


def scatter(slot_bytes: bytes) -> bytearray:
    """Scatter a 21840-byte frame slot into a 64 KiB C64 memory image.

    Bytes not covered by the (partial) map are left zero. The result mirrors
    what the player DMAs into RAM before displaying the frame.
    """
    mem = bytearray(0x10000)
    for r in runs():
        mem[r.c64 : r.c64 + r.length] = slot_bytes[r.slot : r.slot + r.length]
    return mem
