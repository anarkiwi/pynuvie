"""Cover the mufflon backend driver without needing the real binary."""

import pytest

from nuvie import _mufflon_driver as drv


def test_find_mufflon_uses_explicit_path(tmp_path):
    fake = tmp_path / "mufflon"
    fake.write_text("#!/bin/sh\n")
    assert drv.find_mufflon(str(fake)) == str(fake)


def test_find_mufflon_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        drv.find_mufflon(str(tmp_path / "nope"))


def test_find_mufflon_path_lookup(monkeypatch):
    monkeypatch.delenv("NUVIE_MUFFLON", raising=False)
    monkeypatch.setattr(drv.shutil, "which", lambda _c: None)
    with pytest.raises(FileNotFoundError):
        drv.find_mufflon()


def test_encode_via_mufflon_mocked(monkeypatch):
    pytest.importorskip("PIL")
    from PIL import Image

    monkeypatch.setattr(drv, "find_mufflon", lambda mufflon_bin=None: "/fake/mufflon")
    captured = {}

    def fake_run(args, **_kw):
        captured["args"] = args
        out = args[args.index("-o") + 1]
        with open(out, "wb") as f:
            f.write(b"\x00\x20" + b"\xab" * 100)  # $2000 load addr + body

    monkeypatch.setattr(drv.subprocess, "run", fake_run)
    body = drv.encode_via_mufflon(Image.new("RGB", (320, 200)), flibug=True)
    assert body == b"\xab" * 100  # load address stripped

    args = captured["args"]
    # makenuvie's video settings are passed through, plus the flibug edge.
    assert "nufli" in args and "--dither" in args and "--flibug" in args
    assert args[args.index("--dest-palette") + 1] == "pepto"
