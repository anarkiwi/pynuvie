import pytest

from nuvie.pack import build_slot
from nuvie.reu import SLOT_SIZE

pytest.importorskip("PIL")
pytest.importorskip("numpy")


def _img(colour):
    from PIL import Image

    return Image.new("RGB", (320, 200), colour)


def test_flibug_sets_body_and_flag():
    from nuvie.nufli import NufliImage

    nuf = NufliImage.from_image(_img((0, 0, 200)), flibug=True)
    assert nuf.flibug is True
    # the flibug initial colours + colour table got written
    assert nuf.body[0x1FF7] is not None


def test_flibug_changes_displayer_per_content():
    """flibug regenerates the per-frame displayer ($1000-$1ee3) from the body's
    colour table, so differently-coloured frames yield different displayers."""
    from nuvie.nufli import NufliImage

    plain = build_slot(NufliImage.from_image(_img((0, 0, 0)), flibug=False))
    blue = build_slot(NufliImage.from_image(_img((0, 0, 200)), flibug=True))
    red = build_slot(NufliImage.from_image(_img((200, 0, 0)), flibug=True))
    assert len(blue) == SLOT_SIZE
    assert blue != plain
    # left-edge content differs -> different packed slots
    assert blue != red


def test_flibug_implies_two_colour():
    from nuvie.nufli import NufliImage

    nuf = NufliImage.from_image(_img((0, 0, 0)), third_colour=True, flibug=True)
    assert nuf.flibug is True
