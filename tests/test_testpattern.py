import pytest

from nuvie.reu import Nuvie

pytest.importorskip("PIL")


def test_frames_shape():
    from nuvie.testpattern import frames

    fs = list(frames(5))
    assert len(fs) == 5
    assert all(f.size == (320, 200) for f in fs)


def test_frames_animate():
    # consecutive frames must differ (the sweeping block / counter move)
    from nuvie.testpattern import make_frame

    a = list(make_frame(0).getdata())
    b = list(make_frame(7).getdata())
    assert a != b


def test_build_testpattern(tmp_path):
    from nuvie.testpattern import build

    out = tmp_path / "tp.reu"
    movie = build(str(out), n=3)
    assert isinstance(movie, Nuvie)
    assert movie.is_valid()
    assert movie.count_frames() == 3
    assert out.stat().st_size == 16 * 1024 * 1024
