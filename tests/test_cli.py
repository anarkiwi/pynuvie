"""Cover the ``nuvie`` CLI: each subcommand's handler and argument parsing."""

import os

import pytest

from nuvie.cli import main
from nuvie.pack import _sequential_playlist
from nuvie.reu import SLOT_SIZE, Nuvie


def _make_reu(path, frames=3):
    movie = Nuvie()
    for i in range(frames):
        slot = bytearray(SLOT_SIZE)
        slot[0] = i + 1  # distinguishable frame content
        movie.set_frame(i, bytes(slot))
    movie.set_playlist(_sequential_playlist(frames))
    movie.write(path)
    return movie


def test_info(tmp_path, capsys):
    reu = str(tmp_path / "m.reu")
    _make_reu(reu)
    assert main(["info", reu]) == 0
    out = capsys.readouterr().out
    assert "frames:" in out and "playlist:" in out
    assert main(["info", reu, "--playlist-limit", "1"]) == 0


def test_playlist(tmp_path, capsys):
    reu = str(tmp_path / "m.reu")
    _make_reu(reu)
    assert main(["playlist", reu]) == 0
    assert capsys.readouterr().out.strip()


def test_extract(tmp_path):
    reu = str(tmp_path / "m.reu")
    _make_reu(reu, frames=3)
    out = tmp_path / "frames"
    assert main(["extract", reu, "-o", str(out)]) == 0
    assert len(list(out.glob("*.slot"))) == 3
    out2 = tmp_path / "frames2"
    assert main(["extract", reu, "-o", str(out2), "-n", "2"]) == 0
    assert len(list(out2.glob("*.slot"))) == 2


def test_build_and_roundtrip(tmp_path):
    slots = []
    for i in range(2):
        p = tmp_path / f"f{i}.slot"
        data = bytearray(SLOT_SIZE)
        data[0] = i + 1
        p.write_bytes(bytes(data))
        slots.append(str(p))
    out = str(tmp_path / "built.reu")
    assert main(["build", *slots, "-o", out]) == 0
    movie = Nuvie.read(out)
    assert movie.is_valid()
    assert movie.count_frames() == 2


def test_build_rejects_wrong_size(tmp_path, capsys):
    bad = tmp_path / "bad.slot"
    bad.write_bytes(b"\x00" * 10)
    rc = main(["build", str(bad), "-o", str(tmp_path / "x.reu")])
    assert rc == 1
    assert "expected" in capsys.readouterr().err


def test_testpattern(tmp_path):
    pytest.importorskip("PIL")
    out = str(tmp_path / "tp.reu")
    assert main(["testpattern", "-o", out, "-n", "2", "--style", "greyscale"]) == 0
    assert Nuvie.read(out).count_frames() == 2


def test_encode_dispatch(tmp_path, monkeypatch):
    # _cmd_encode just forwards to encode_video; stub it so no ffmpeg/video needed.
    import nuvie.encode as enc

    seen = {}

    def fake(video, out_path, **kw):
        seen.update(video=video, out=out_path, **kw)
        Nuvie().write(out_path)
        return 7

    monkeypatch.setattr(enc, "encode_video", fake)
    out = str(tmp_path / "v.reu")
    rc = main(["encode", "clip.mp4", "-o", out, "--backend", "mufflon", "--fps", "10"])
    assert rc == 0
    assert seen["backend"] == "mufflon" and seen["fps"] == 10.0
    assert os.path.exists(out)
