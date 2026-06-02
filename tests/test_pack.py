import os

import pytest

from nuvie.nufli import NufliImage
from nuvie.pack import build_movie, build_slot
from nuvie.reu import MAX_FRAMES, SLOT_SIZE, Nuvie

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def test_build_movie_parallel_matches_serial():
    pytest.importorskip("PIL")
    from PIL import Image

    imgs = [Image.new("RGB", (320, 200), (c, 0, 255 - c)) for c in (10, 120, 230)]
    serial = build_movie(list(imgs)).to_bytes()
    parallel = build_movie(list(imgs), workers=3).to_bytes()
    assert parallel == serial  # parallel encode must be byte-identical to serial


def test_build_slot_matches_real_nuviemaker_slot():
    """Packing a real mufflon .nuf must reproduce the slot NUVIEmaker itself
    produced (captured from the C64), to within the handful of displayer-setup
    bytes. This guards the pack table + source template against regressions."""
    with open(os.path.join(FIX, "nufli_sample.nuf"), "rb") as f:
        nuf = NufliImage.from_prg(f.read())
    slot = build_slot(nuf)
    with open(os.path.join(FIX, "pack_sample_slot.bin"), "rb") as f:
        real = f.read()
    assert len(slot) == SLOT_SIZE == len(real)
    match = sum(1 for a, b in zip(slot, real) if a == b)
    assert match / len(slot) > 0.999  # 99.9%+ identical to NUVIEmaker's output


def test_build_slot_size():
    slot = build_slot(NufliImage(bytes(0x5A00)))
    assert len(slot) == SLOT_SIZE


def test_build_movie_valid_and_playlist():
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    imgs = []
    for k in range(3):
        im = Image.new("RGB", (320, 200), (0, 0, 0))
        ImageDraw.Draw(im).rectangle([k * 20, 20, k * 20 + 60, 120], fill=(200, 40, 40))
        imgs.append(im)
    movie = build_movie(imgs)
    assert isinstance(movie, Nuvie)
    assert movie.is_valid()
    assert movie.count_frames() == 3
    pl = list(movie.playlist)
    assert pl[0].image_number == 0
    assert pl[-1].is_end()


def test_build_movie_caps_at_max_frames(monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image

    from nuvie import pack

    # encoding 768+ frames for real is far too slow; stub the per-frame work.
    monkeypatch.setattr(pack, "build_slot", lambda _img: bytes([1]) + bytes(SLOT_SIZE - 1))
    monkeypatch.setattr(
        NufliImage, "from_image", classmethod(lambda cls, *_a, **_k: cls(bytes(0x5A00)))
    )

    def gen():
        for _ in range(MAX_FRAMES + 5):
            yield Image.new("RGB", (1, 1))

    movie = build_movie(gen())
    assert movie.count_frames() == MAX_FRAMES
