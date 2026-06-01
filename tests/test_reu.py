import pytest

from nuvie.reu import (
    MAX_FRAMES,
    REU_SIZE,
    SLOT_SIZE,
    Control,
    Nuvie,
    frame_location,
    part1_offset,
    part2_offset,
)
from nuvie.playlist import Playlist, Token


def test_empty_is_valid_and_sized():
    m = Nuvie()
    assert len(m.to_bytes()) == REU_SIZE
    assert m.is_valid()
    assert m.count_frames() == 0


def test_frame_location_math():
    assert frame_location(0) == (0, 0)
    assert frame_location(1) == (0, 1)
    assert frame_location(2) == (0, 2)
    assert frame_location(3) == (1, 0)
    assert frame_location(767) == (255, 2)
    with pytest.raises(IndexError):
        frame_location(MAX_FRAMES)


def test_slot_offsets_tile_the_bank():
    # the three part-1 blocks + aux occupy the first 256 bytes
    assert part1_offset(0) == 0x00
    assert part1_offset(2) + 0x50 == 0xF0  # then the 16-byte aux at 0xF0
    # the three part-2 blocks fill 0x100..0xFFFF exactly
    assert part2_offset(0) == 0x100
    assert part2_offset(2) + 0x5500 == 0x10000


def test_frame_roundtrip():
    m = Nuvie()
    frame = bytes((i * 31) & 0xFF for i in range(SLOT_SIZE))
    m.set_frame(7, frame)
    assert m.frame(7) == frame
    assert m.count_frames() == 0  # frames 0..6 are empty, so leading count is 0


def test_frame_count_is_leading_run():
    m = Nuvie()
    for i in range(4):
        m.set_frame(i, bytes([1]) + bytes(SLOT_SIZE - 1))
    assert m.count_frames() == 4


def test_bad_frame_size_rejected():
    m = Nuvie()
    with pytest.raises(ValueError):
        m.set_frame(0, b"\x00" * 100)


def test_control_roundtrip():
    c = Control(
        music=0xE8,
        music_start=0x123456,
        music_end=0xFEDCBA,
        custom_code=0xFF,
        border_lr=0x01,
        border_tb=0x02,
        infoscreen=0x83,
        infoscreen_bg=0x10,
        infoscreen_frames=300,
        charset=0xA5,
    )
    assert Control.from_bytes(c.to_bytes()) == c
    assert c.has_music


def test_control_via_nuvie():
    m = Nuvie()
    assert not m.control.has_music
    m.set_control(Control(music=0xF8, music_start=0x1000, music_end=0x2000))
    assert m.control.has_music
    assert m.control.music_start == 0x1000


def test_playlist_roundtrip():
    m = Nuvie()
    pl = Playlist([Token(0x00, 0x05), Token(0x91, 0x10), Token(0xE8, 0x00)])
    m.set_playlist(pl)
    got = m.playlist
    assert [(t.cmd, t.value) for t in got] == [(0x00, 0x05), (0x91, 0x10), (0xE8, 0x00)]


def test_bytes_roundtrip_preserves_everything():
    m = Nuvie()
    frame = bytes((i * 13) & 0xFF for i in range(SLOT_SIZE))
    m.set_frame(0, frame)
    m.set_control(Control(music=0xE8, music_start=0x10, music_end=0x20))
    m.set_playlist(Playlist([Token(0x00, 0x00), Token(0xE8, 0x00)]))
    m2 = Nuvie.from_bytes(m.to_bytes())
    assert m2.is_valid()
    assert m2.frame(0) == frame
    assert m2.control.music == 0xE8
    assert [(t.cmd, t.value) for t in m2.playlist] == [(0x00, 0x00), (0xE8, 0x00)]


def test_rejects_wrong_size():
    with pytest.raises(ValueError):
        Nuvie.from_bytes(b"\x00" * 100)
