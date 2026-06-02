"""Pack a NUFLI image into a NUVIE REU frame slot -- the inverse of the player.

This reproduces, in pure Python, what Crest's ``NUVIEmaker`` does when it stashes
a loaded NUFLI image into the REU: it runs a fixed table of C64->REU DMA
descriptors (recovered from NUVIEmaker's pack routine at ``$0e00``, table at
``$9800``). Each descriptor copies a run of the C64 source memory into the slot.

The C64 source memory is the loaded ``.nuf`` graphics at ``$2000+`` plus a fixed
player-displayer stub at ``$1000-$1FFF`` that NUVIEmaker supplies. We ship that
stub and the non-graphics fixed bytes as ``data/pack_source.bin`` and overlay the
encoder's graphics on top, then apply the descriptor table.

A pure-Python slot built this way matches NUVIEmaker's real packed slot to 99.9%
and plays correctly on ``nuvieplayer1.0.prg``.

The pack table and the displayer stub are derived from Crest's NUVIEmaker and are
included here, with attribution, solely to interoperate with the NUVIE format.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import List, Optional

from .nufli import (
    _BITMAP_HI,
    _BITMAP_LO,
    NUIFLI_SCRAM,
    N_MAIN_SPRITES,
    NufliImage,
    _SPRITE_COLOUR_BASE,
    _sprite_addr_map,
)
from .reu import MAX_FRAMES, SLOT_SIZE, Nuvie

PART1_C64 = 0x1EE4  # source of the 80-byte part 1 (in the displayer stub)
PART1_LEN = 0x50
SOURCE_BASE = 0x1000  # pack_source.bin represents C64 $1000..$7A00


def _data_path(name: str):
    """Path to a bundled data file. Uses the module's own directory so it works on
    every Python version and whether installed or run in-tree (the data dir has no
    ``__init__``, which trips ``importlib.resources.files`` on 3.9)."""
    from pathlib import Path

    return Path(__file__).resolve().parent / "data" / name


@lru_cache(maxsize=1)
def _pack_source() -> bytes:
    return bytes(_data_path("pack_source.bin").read_bytes())


@lru_cache(maxsize=1)
def _pack_table() -> List[dict]:
    return json.loads(_data_path("pack_table.json").read_text())


@lru_cache(maxsize=1)
def _graphics_offsets() -> frozenset:
    """The NUFLI body offsets the encoder fills (bitmap, FLI screen RAM, the six
    main sprite bitmaps and their colour tables). These get overlaid on the
    fixed source template; everything else (displayer, flibug, pointers) is kept."""
    offs = set()
    o1, l1 = _BITMAP_HI
    o2, l2 = _BITMAP_LO
    offs.update(range(o1, o1 + l1))
    offs.update(range(o2, o2 + l2))
    for by in range(len(NUIFLI_SCRAM)):
        for cx in range(40):
            offs.add(NUIFLI_SCRAM[by] + cx)
    for addr in _sprite_addr_map().values():
        offs.add(addr)
    for s in range(N_MAIN_SPRITES):
        for lp in range(100):
            offs.add(_SPRITE_COLOUR_BASE[s] + lp)
    return frozenset(offs)


def build_slot(image: NufliImage) -> bytes:
    """Pack a :class:`~nuvie.nufli.NufliImage` into a 21840-byte NUVIE frame slot
    (part 1 + part 2) that plays on the reference player.

    When the image was encoded with ``flibug`` (``NufliImage.from_image(flibug=
    True)``) the body carries a generated flibug plane (sprite bitmaps + a 6-column
    colour table); the per-frame displayer is regenerated from that table (see
    :mod:`nuvie._displayer`) and spliced in, so the left 24px renders the picture
    instead of VIC FLI-bug corruption. Otherwise the displayer template is kept."""
    src = bytearray(_pack_source())  # C64 $1000..$7A00
    body = image.body
    for o in _graphics_offsets():  # overlay the encoder's graphics (C64 $2000+o)
        src[o + 0x1000] = body[o]
    if getattr(image, "flibug", False):
        from ._displayer import generate, DISPLAYER_LEN, COLOUR_COLS
        from ._flibug import _sprite_offsets

        # overlay the flibug graphics the main _graphics_offsets pass doesn't cover
        ho, mo = _sprite_offsets()
        extra = {o for row in ho for o in row} | {o for row in mo for o in row}
        for base in COLOUR_COLS:
            extra.update(range(base - 1, base + 101))
        extra.update((0x1FF0, 0x1FF1, 0x1FF6, 0x1FF7))
        for o in extra:
            src[o + 0x1000] = body[o]
        src[0:DISPLAYER_LEN] = generate(body)  # regenerate displayer ($1000-$1ee3)
    slot = bytearray(SLOT_SIZE)
    slot[0:PART1_LEN] = src[PART1_C64 - SOURCE_BASE : PART1_C64 - SOURCE_BASE + PART1_LEN]
    for d in _pack_table():
        si = d["c64"] - SOURCE_BASE
        slot[PART1_LEN + d["reu"] : PART1_LEN + d["reu"] + d["len"]] = src[si : si + d["len"]]
    return bytes(slot)


def _sequential_playlist(n: int):
    from .playlist import Playlist, Token

    tokens = [Token(0x00, 0x00)]
    remaining = n - 1
    while remaining > 0:
        step = min(remaining, 0xFF)
        tokens.append(Token(0x91, step))
        remaining -= step
    tokens.append(Token(0xE8, 0x00))  # wrap to the start
    return Playlist(tokens)


def build_movie(images, out_path: Optional[str] = None, backend: str = "clean",
                flibug: bool = True, cohere: float = 600.0, mufflon_bin=None) -> Nuvie:
    """Encode an iterable of Pillow images into a full-colour NUVIE.

    Each image is NUFLI-encoded (``backend`` = ``"clean"`` pynuvie encoder, or
    ``"mufflon"`` to drive the real binary) and packed into its slot; a sequential
    play-through playlist is generated. With ``flibug`` (default) the left-24px
    edge is generated so it follows the picture instead of showing VIC FLI-bug
    corruption.
    """
    movie = Nuvie()
    n = 0
    for i, img in enumerate(images):
        if i >= MAX_FRAMES:
            break
        nuf = NufliImage.from_image(img, backend=backend, flibug=flibug,
                                    cohere=cohere, mufflon_bin=mufflon_bin)
        movie.set_frame(i, build_slot(nuf))
        n = i + 1
    movie.set_playlist(_sequential_playlist(n))
    if out_path:
        movie.write(out_path)
    return movie
