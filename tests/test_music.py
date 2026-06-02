"""SID-music CSV reading and attaching to a NUVIE."""

import pytest

from nuvie.cli import main
from nuvie.music import read_sid_csv
from nuvie.reu import MUSIC_LOOP, MUSIC_RESTART, MUSIC_TOP, SID_REGS_PER_FRAME, Nuvie


def _csv(tmp_path, rows, header=None):
    p = tmp_path / "tune.csv"
    lines = []
    if header:
        lines.append(",".join(header))
    lines += [",".join(str(v) for v in r) for r in rows]
    p.write_text("\n".join(lines) + "\n")
    return str(p)


def test_read_sid_csv_basic(tmp_path):
    rows = [list(range(SID_REGS_PER_FRAME)), [255] * SID_REGS_PER_FRAME]
    data = read_sid_csv(_csv(tmp_path, rows))
    assert data == bytes(range(SID_REGS_PER_FRAME)) + bytes([255] * SID_REGS_PER_FRAME)


def test_read_sid_csv_skips_header_and_blanks(tmp_path):
    p = tmp_path / "t.csv"
    body = ",".join(["1"] * SID_REGS_PER_FRAME)
    header = ",".join(f"r{i}" for i in range(SID_REGS_PER_FRAME))
    p.write_text(f"{header}\n\n{body}\n\n")
    assert read_sid_csv(str(p)) == bytes([1] * SID_REGS_PER_FRAME)


def test_read_sid_csv_accepts_hex(tmp_path):
    rows = [["0x10"] + ["0"] * (SID_REGS_PER_FRAME - 1)]
    assert read_sid_csv(_csv(tmp_path, rows))[0] == 0x10


def test_read_sid_csv_wrong_width(tmp_path):
    with pytest.raises(ValueError, match="expected 25"):
        read_sid_csv(_csv(tmp_path, [[1, 2, 3]]))


def test_read_sid_csv_out_of_range(tmp_path):
    with pytest.raises(ValueError, match="out of range"):
        read_sid_csv(_csv(tmp_path, [[300] + [0] * (SID_REGS_PER_FRAME - 1)]))


def test_read_sid_csv_empty(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_text("\n\n")
    with pytest.raises(ValueError, match="no SID frames"):
        read_sid_csv(str(p))


def test_set_music_roundtrip():
    movie = Nuvie()
    data = bytes(range(SID_REGS_PER_FRAME)) * 4  # 4 ticks
    movie.set_music(data)
    c = movie.control
    assert c.has_music and c.music == MUSIC_LOOP
    assert c.music_end == MUSIC_TOP + 1
    assert c.music_start == c.music_end - len(data)
    assert movie.music_region() == data
    movie.clear_music()
    assert not movie.control.has_music
    assert movie.music_region() == b""


def test_set_music_rejects_bad_length():
    with pytest.raises(ValueError, match="multiple of 25"):
        Nuvie().set_music(b"\x00" * 13)


def test_set_music_restart_flag():
    movie = Nuvie()
    movie.set_music(bytes(SID_REGS_PER_FRAME), flag=MUSIC_RESTART)
    assert movie.control.music == MUSIC_RESTART


def test_cli_music_subcommand(tmp_path):
    reu = tmp_path / "m.reu"
    Nuvie().write(str(reu))
    csv = _csv(tmp_path, [[7] * SID_REGS_PER_FRAME] * 3)
    out = tmp_path / "withmusic.reu"
    assert main(["music", str(reu), "--csv", csv, "-o", str(out), "--restart"]) == 0
    m = Nuvie.read(str(out))
    assert m.control.music == MUSIC_RESTART
    assert m.music_region() == bytes([7] * SID_REGS_PER_FRAME * 3)
    # original untouched (wrote to -o)
    assert not Nuvie.read(str(reu)).control.has_music


def test_cli_music_in_place(tmp_path):
    reu = tmp_path / "m.reu"
    Nuvie().write(str(reu))
    csv = _csv(tmp_path, [[1] * SID_REGS_PER_FRAME])
    assert main(["music", str(reu), "--csv", csv]) == 0
    assert Nuvie.read(str(reu)).control.has_music


def test_cli_encode_with_music(tmp_path, monkeypatch):
    import nuvie.encode as enc

    out = tmp_path / "v.reu"
    monkeypatch.setattr(enc, "encode_video", lambda *a, **k: Nuvie().write(str(out)) or 1)
    csv = _csv(tmp_path, [[9] * SID_REGS_PER_FRAME] * 2)
    assert main(["encode", "clip.mp4", "-o", str(out), "--music", csv]) == 0
    assert Nuvie.read(str(out)).music_region() == bytes([9] * SID_REGS_PER_FRAME * 2)
