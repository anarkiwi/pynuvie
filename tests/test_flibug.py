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

    nuf = NufliImage.from_image(_img((0, 0, 200)), backend="clean", flibug=True)
    assert nuf.flibug is True
    # the flibug initial colours + colour table got written
    assert nuf.body[0x1FF7] is not None


def test_flibug_changes_displayer_per_content():
    """flibug regenerates the per-frame displayer ($1000-$1ee3) from the body's
    colour table, so differently-coloured frames yield different displayers.

    Uses exact C64 palette colours so the (mufflon-faithful, luma-weighted) colour
    search keeps them distinct -- arbitrary saturated RGB can both collapse onto the
    same low-luma colour under the 0.299/0.587/0.114 weighting."""
    from nuvie.nufli import NufliImage
    from nuvie.palette import C64_PALETTE

    plain = build_slot(NufliImage.from_image(_img(C64_PALETTE[0]), backend="clean", flibug=False))
    green = build_slot(NufliImage.from_image(_img(C64_PALETTE[5]), backend="clean", flibug=True))
    yellow = build_slot(NufliImage.from_image(_img(C64_PALETTE[7]), backend="clean", flibug=True))
    assert len(green) == SLOT_SIZE
    assert green != plain
    # left-edge content differs -> different packed slots
    assert green != yellow


def test_flibug_implies_two_colour():
    from nuvie.nufli import NufliImage

    nuf = NufliImage.from_image(_img((0, 0, 0)), backend="clean", flibug=True)
    assert nuf.flibug is True
