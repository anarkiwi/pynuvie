"""The NUVIE playlist token language.

A NUVIE playlist is a stream of two-byte tokens ``(command, value)`` that the
NuviePlayer interprets to script playback: which frames to show, in what order,
at what speed, loops, blank screens and where to wrap at the end.

The semantics below are taken from the ``NUVIEmaker 0.1e`` README by DeeKay &
Crossbow of Crest (the playlist editor section). Every token is two bytes; for
some commands the low nibble of the command byte carries a parameter (written
here as ``y``) and ``xx`` is the value byte.

Token reference (``cmd value``)::

    0y xx   Show image number (y*100 + xx), DECIMAL, and set the frame counter
            to it.  e.g. ``05 63`` shows frame 563.
    10 xx   Begin loop, played ``xx`` times (0 does not count).
    20 ??   End loop, resetting to the image shown when the loop started.
    30 ??   End loop, NOT resetting the current image.
    4y ??   Character screen (orange token) -- not supported by NUVIEmaker.
    8f xx   Play ``xx`` frames backwards from the frame counter.
    8e/8d.. Play backwards skipping frames (2x, 3x .. speed): 8e=2x, 8d=3x ...
    90 xx   Hold the current image for ``xx`` frames (frame counter unchanged).
    91 xx   Play ``xx`` frames forwards from the frame counter.
    92/93.. Play forwards skipping frames (2x, 3x .. speed): 92=2x, 93=3x ...
    by xx   Set playback speed: show each image for ``y`` ticks (3 == normal,
            i.e. 4 frames per image). Second byte ignored. Frame counter unchanged.
    cy xx   Blank screen of colour ``y`` for ``xx`` frames (frame counter unchanged).
    dy xx   Blank screen of colour ``y`` WITH matching border, for ``xx`` frames.
    ey xx   End: wrap to playlist address ``(y << 8) | xx`` independently of music.
    fy xx   End: wrap to playlist address ``(y << 8) | xx`` in sync with music.

A token whose command byte matches none of the above is *illegal* (the editor
shows these in dark grey); :class:`Token` preserves the raw bytes so such
playlists round-trip losslessly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterator, List


class TokenKind(Enum):
    """Semantic classification of a playlist token's command byte."""

    SHOW_IMAGE = "show_image"  # 0y
    LOOP_BEGIN = "loop_begin"  # 10
    LOOP_END_RESET = "loop_end_reset"  # 20
    LOOP_END_KEEP = "loop_end_keep"  # 30
    CHARSCREEN = "charscreen"  # 4y (unsupported by maker)
    PLAY_BACKWARD = "play_backward"  # 8f .. 80 (skip = 0x8f - cmd + 1)
    HOLD = "hold"  # 90
    PLAY_FORWARD = "play_forward"  # 91 .. 9f (skip = cmd - 0x91 + 1)
    SPEED = "speed"  # by
    BLANK = "blank"  # cy
    BLANK_BORDER = "blank_border"  # dy
    END_WRAP_MUSIC_FREE = "end_wrap_music_free"  # ey
    END_WRAP_MUSIC_SYNC = "end_wrap_music_sync"  # fy
    UNKNOWN = "unknown"


def classify(cmd: int) -> TokenKind:
    """Map a command byte to its :class:`TokenKind`."""
    if cmd == 0x10:
        return TokenKind.LOOP_BEGIN
    if cmd == 0x20:
        return TokenKind.LOOP_END_RESET
    if cmd == 0x30:
        return TokenKind.LOOP_END_KEEP
    if cmd == 0x90:
        return TokenKind.HOLD
    if cmd == 0x8F:
        return TokenKind.PLAY_BACKWARD
    if 0x80 <= cmd <= 0x8E:
        return TokenKind.PLAY_BACKWARD
    if 0x91 <= cmd <= 0x9F:
        return TokenKind.PLAY_FORWARD
    hi = cmd & 0xF0
    if hi == 0x00:
        return TokenKind.SHOW_IMAGE
    if hi == 0x40:
        return TokenKind.CHARSCREEN
    if hi == 0xB0:
        return TokenKind.SPEED
    if hi == 0xC0:
        return TokenKind.BLANK
    if hi == 0xD0:
        return TokenKind.BLANK_BORDER
    if hi == 0xE0:
        return TokenKind.END_WRAP_MUSIC_FREE
    if hi == 0xF0:
        return TokenKind.END_WRAP_MUSIC_SYNC
    return TokenKind.UNKNOWN


@dataclass
class Token:
    """A single two-byte playlist token, preserving its raw bytes."""

    cmd: int
    value: int

    def __post_init__(self) -> None:
        if not (0 <= self.cmd <= 0xFF and 0 <= self.value <= 0xFF):
            raise ValueError("token bytes must be 0..255")

    @property
    def kind(self) -> TokenKind:
        return classify(self.cmd)

    @property
    def low_nibble(self) -> int:
        """The ``y`` parameter carried in the low nibble of the command byte."""
        return self.cmd & 0x0F

    def is_end(self) -> bool:
        """True for the wrap/end tokens ``ey``/``fy`` that terminate playback."""
        return self.kind in (
            TokenKind.END_WRAP_MUSIC_FREE,
            TokenKind.END_WRAP_MUSIC_SYNC,
        )

    @property
    def image_number(self) -> int:
        """For ``SHOW_IMAGE`` tokens, the decimal frame number ``y*100 + xx``.

        Note the value byte ``xx`` is interpreted as a decimal pair of digits,
        matching the on-C64 editor (``05 63`` -> frame 563).
        """
        if self.kind is not TokenKind.SHOW_IMAGE:
            raise ValueError("not a SHOW_IMAGE token")
        return self.low_nibble * 100 + (self.value >> 4) * 10 + (self.value & 0x0F)

    @property
    def play_skip(self) -> int:
        """For play tokens, frames advanced per shown image (1 == every frame)."""
        if self.kind is TokenKind.PLAY_FORWARD:
            return self.cmd - 0x91 + 1
        if self.kind is TokenKind.PLAY_BACKWARD:
            return 0x8F - self.cmd + 1
        raise ValueError("not a play token")

    @property
    def wrap_address(self) -> int:
        """For end tokens, the playlist wrap target ``(y << 8) | xx``."""
        if not self.is_end():
            raise ValueError("not an end token")
        return (self.low_nibble << 8) | self.value

    def to_bytes(self) -> bytes:
        return bytes((self.cmd, self.value))

    def describe(self) -> str:
        k = self.kind
        if k is TokenKind.SHOW_IMAGE:
            return f"show image {self.image_number}"
        if k is TokenKind.LOOP_BEGIN:
            return f"loop begin x{self.value}"
        if k is TokenKind.LOOP_END_RESET:
            return "loop end (reset image)"
        if k is TokenKind.LOOP_END_KEEP:
            return "loop end (keep image)"
        if k is TokenKind.CHARSCREEN:
            return f"charscreen {self.low_nibble} (unsupported)"
        if k is TokenKind.PLAY_FORWARD:
            return f"play {self.value} frames forward (skip {self.play_skip})"
        if k is TokenKind.PLAY_BACKWARD:
            return f"play {self.value} frames backward (skip {self.play_skip})"
        if k is TokenKind.HOLD:
            return f"hold image for {self.value} frames"
        if k is TokenKind.SPEED:
            return f"speed: {self.low_nibble + 1} frames per image"
        if k is TokenKind.BLANK:
            return f"blank colour {self.low_nibble} for {self.value} frames"
        if k is TokenKind.BLANK_BORDER:
            return f"blank+border colour {self.low_nibble} for {self.value} frames"
        if k is TokenKind.END_WRAP_MUSIC_FREE:
            return f"end, wrap to ${self.wrap_address:04x} (music-free)"
        if k is TokenKind.END_WRAP_MUSIC_SYNC:
            return f"end, wrap to ${self.wrap_address:04x} (music-sync)"
        return f"unknown token ${self.cmd:02x} ${self.value:02x}"

    def __repr__(self) -> str:
        return f"Token(${self.cmd:02x}, ${self.value:02x}: {self.describe()})"


@dataclass
class Playlist:
    """An ordered list of :class:`Token` describing playback."""

    tokens: List[Token]

    @classmethod
    def parse(cls, data: bytes, *, stop_at_end: bool = True) -> "Playlist":
        """Parse a raw playlist byte stream into tokens.

        If ``stop_at_end`` is set (the default), parsing stops after the first
        ``ey``/``fy`` end token, which terminates a NUVIE playlist.
        """
        tokens: List[Token] = []
        for i in range(0, len(data) - 1, 2):
            tok = Token(data[i], data[i + 1])
            tokens.append(tok)
            if stop_at_end and tok.is_end():
                break
        return cls(tokens)

    def to_bytes(self) -> bytes:
        return b"".join(t.to_bytes() for t in self.tokens)

    def __iter__(self) -> Iterator[Token]:
        return iter(self.tokens)

    def __len__(self) -> int:
        return len(self.tokens)

    def __getitem__(self, i: int) -> Token:
        return self.tokens[i]
