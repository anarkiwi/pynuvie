"""End-to-end regression test of the encoder, with no emulator required.

Each generated frame carries a binary barcode of its index (see
``tests/integration/make_movie.py``). We encode frames, pack them into a REU,
read it back, reconstruct each frame's C64 bitmap via the player DMA map, and
decode the barcode. If any link in encode → slot → container → DMA-map → bitmap
regresses, a frame's barcode stops matching its index.
"""

import os
import sys

import pytest

from nuvie import slotmap
from nuvie.encode import BITMAP_C64_BASE, BITMAP_SIZE, build_reu, encode_frame_slot
from nuvie.reu import SLOT_SIZE, Nuvie

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "integration"))
make_movie = pytest.importorskip("make_movie")
pytest.importorskip("PIL")

FRAMES = [0, 1, 2, 3, 14, 42, 100, 255, 256, 500, 767]


def _bitmap_bit(bmp, x, y):
    cell = (y >> 3) * 320 + (x >> 3) * 8 + (y & 7)
    return (bmp[cell] >> (7 - (x & 7))) & 1


def _read_barcode(bmp):
    bits = []
    for cx, _ in make_movie.barcode_cell_centers():
        s = t = 0
        for yy in range(make_movie.BARCODE_Y0 + 4, make_movie.BARCODE_Y0 + make_movie.CELL_H - 4):
            for xx in range(cx - 5, cx + 5):
                s += _bitmap_bit(bmp, xx, yy)
                t += 1
        bits.append(1 if s > t / 2 else 0)
    return bits


def _decode_index(bmp):
    bits = _read_barcode(bmp)
    assert bits[0] == 1 and bits[-1] == 1, "guard bars missing"
    val = 0
    for b in bits[1:-1]:
        val = (val << 1) | b
    return val


def test_encoded_frame_is_lossless_through_container():
    slot = encode_frame_slot(make_movie.make_frame(0))
    assert len(slot) == SLOT_SIZE
    movie = build_reu([slot])
    movie2 = Nuvie.from_bytes(movie.to_bytes())
    assert movie2.frame(0) == slot
    assert movie2.is_valid()


@pytest.mark.parametrize("frame", FRAMES)
def test_barcode_survives_full_pipeline(frame):
    slot = encode_frame_slot(make_movie.make_frame(frame))
    movie = build_reu([bytes(SLOT_SIZE)] * frame + [slot]) if frame else build_reu([slot])
    movie = Nuvie.from_bytes(movie.to_bytes())
    mem = slotmap.scatter(movie.frame(frame))
    bmp = mem[BITMAP_C64_BASE : BITMAP_C64_BASE + BITMAP_SIZE]
    assert _decode_index(bmp) == frame % 1024


def test_build_reu_playlist_and_validity():
    slots = [encode_frame_slot(make_movie.make_frame(i)) for i in range(3)]
    movie = build_reu(slots)
    assert movie.is_valid()
    pl = list(movie.playlist)
    assert pl[0].image_number == 0
    assert pl[-1].is_end()
