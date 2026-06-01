"""Byte-parity regression: pynuvie reproduces mufflon's NUFLI graphics exactly.

The fixture ``mufflon_parity_src.png`` is a palette-exact (Pepto) image and
``mufflon_parity.nuf`` is Crest's mufflon ``--otype nufli --dest-palette pepto``
output for it (single-threaded, the deterministic non-flibug path). For any
palette-exact input pynuvie's encoder must reproduce mufflon's hi-res bitmap, FLI
screen RAM, main sprite bitmaps and sprite colour table **byte-for-byte**; this
test fails if a future change diverges from mufflon.
"""

import os

import pytest

pytest.importorskip("PIL")
pytest.importorskip("numpy")

import numpy as np
from PIL import Image

from nuvie._mufflon import encode_body
from nuvie.nufli import (
    NUIFLI_SCRAM,
    N_MAIN_SPRITES,
    _BITMAP_HI,
    _BITMAP_LO,
    _SPRITE_COLOUR_BASE,
    _sprite_addr_map,
)

_FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def _graphics_regions():
    r = {}
    o1, l1 = _BITMAP_HI
    o2, l2 = _BITMAP_LO
    r["bitmap_hi"] = list(range(o1, o1 + l1))
    r["bitmap_lo"] = list(range(o2, o2 + l2))
    r["screen_ram"] = [NUIFLI_SCRAM[by] + cx for by in range(100) for cx in range(40)]
    r["sprite_bitmap"] = sorted(set(_sprite_addr_map().values()))
    r["sprite_colour"] = [
        _SPRITE_COLOUR_BASE[s] + lp for s in range(N_MAIN_SPRITES) for lp in range(100)
    ]
    return r


def test_encode_body_byte_identical_to_mufflon():
    img = Image.open(os.path.join(_FIX, "mufflon_parity_src.png")).convert("RGB")
    rgb = np.asarray(img, dtype=np.uint8)
    assert rgb.shape == (200, 320, 3)

    muf = open(os.path.join(_FIX, "mufflon_parity.nuf"), "rb").read()
    if muf[:2] == b"\x00\x20":
        muf = muf[2:]
    mine = encode_body(rgb)

    for name, offsets in _graphics_regions().items():
        diffs = [o for o in offsets if mine[o] != muf[o]]
        assert not diffs, f"{name}: {len(diffs)} bytes differ from mufflon"


def test_from_image_uses_mufflon_encoder_by_default():
    """The default full-colour from_image path matches the standalone encoder."""
    from nuvie.nufli import NufliImage

    img = Image.open(os.path.join(_FIX, "mufflon_parity_src.png")).convert("RGB")
    body = NufliImage.from_image(img, third_colour=True, flibug=False).body
    direct = encode_body(np.asarray(img, dtype=np.uint8))
    # bitmap + screen + sprite regions are produced solely by encode_body
    for o in _graphics_regions()["sprite_colour"]:
        assert body[o] == direct[o]
