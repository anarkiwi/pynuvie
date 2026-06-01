import pytest

from nuvie.playlist import Playlist, Token, TokenKind, classify


def test_classify():
    assert classify(0x00) is TokenKind.SHOW_IMAGE
    assert classify(0x05) is TokenKind.SHOW_IMAGE
    assert classify(0x10) is TokenKind.LOOP_BEGIN
    assert classify(0x20) is TokenKind.LOOP_END_RESET
    assert classify(0x30) is TokenKind.LOOP_END_KEEP
    assert classify(0x42) is TokenKind.CHARSCREEN
    assert classify(0x8F) is TokenKind.PLAY_BACKWARD
    assert classify(0x8E) is TokenKind.PLAY_BACKWARD
    assert classify(0x90) is TokenKind.HOLD
    assert classify(0x91) is TokenKind.PLAY_FORWARD
    assert classify(0x9F) is TokenKind.PLAY_FORWARD
    assert classify(0xB3) is TokenKind.SPEED
    assert classify(0xC1) is TokenKind.BLANK
    assert classify(0xD2) is TokenKind.BLANK_BORDER
    assert classify(0xE8) is TokenKind.END_WRAP_MUSIC_FREE
    assert classify(0xF8) is TokenKind.END_WRAP_MUSIC_SYNC


def test_show_image_decimal():
    # $05 $63 shows frame 563 (decimal), per the NUVIEmaker README
    assert Token(0x05, 0x63).image_number == 563
    assert Token(0x00, 0x00).image_number == 0
    assert Token(0x07, 0x68).image_number == 768


def test_play_skip():
    assert Token(0x91, 0x10).play_skip == 1
    assert Token(0x92, 0x10).play_skip == 2
    assert Token(0x8F, 0x10).play_skip == 1
    assert Token(0x8E, 0x10).play_skip == 2


def test_wrap_address():
    assert Token(0xE8, 0x00).wrap_address == 0x0800
    assert Token(0xF8, 0x00).wrap_address == 0x0800
    assert Token(0xE8, 0x10).wrap_address == 0x0810
    assert Token(0xE8, 0x00).is_end()


def test_parse_stops_at_end():
    data = bytes([0x00, 0x00, 0x91, 0x05, 0xE8, 0x00, 0x00, 0x00])
    pl = Playlist.parse(data)
    assert len(pl) == 3
    assert pl[-1].is_end()


def test_parse_no_stop():
    data = bytes([0x00, 0x00, 0xE8, 0x00, 0x90, 0x10])
    pl = Playlist.parse(data, stop_at_end=False)
    assert len(pl) == 3


def test_roundtrip_bytes():
    data = bytes([0x10, 0x05, 0x91, 0x13, 0x8F, 0x13, 0x20, 0x00, 0xE8, 0x00])
    pl = Playlist.parse(data)
    assert pl.to_bytes() == data


def test_token_validation():
    with pytest.raises(ValueError):
        Token(0x100, 0)


def test_describe_does_not_crash():
    for cmd in range(256):
        for val in (0x00, 0x7F, 0xFF):
            Token(cmd, val).describe()
