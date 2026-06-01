"""The NUVIE REU container format.

A NUVIE is a 16 MiB Commodore 64 REU (RAM Expansion Unit) image: 256 banks of
64 KiB. It holds up to 768 NUFLI frames, an optional SID soundtrack, and a
playlist that scripts playback. This module reads and writes that container
without an emulator.

The layout below was established by reverse-engineering Crest's
``nuvieplayer1.0.prg`` (the reference player) -- watching which bytes it
validates and where it DMAs them -- and cross-checked against the
`C64-Wiki Nuvie article <https://www.c64-wiki.de/wiki/Nuvie>`_ and the
``NUVIEmaker`` README. See ``docs/FORMAT.md``.

Per bank (65536 bytes)::

    offset 0x0000..0x00EF   three 80-byte image "part 1" blocks (slots 0,1,2)
    offset 0x00F0..0x00FF   16-byte auxiliary block (see below)
    offset 0x0100..0xFFFF   three 0x5500-byte image "part 2" blocks (slots 0,1,2)

A frame's image data is its part 1 (80 bytes) followed by its part 2 (21760
bytes) = 21840 bytes; the split exists so the player can DMA it quickly.
Frame ``f`` lives in bank ``f // 3``, slot ``f % 3``.

The 16-byte auxiliary block of every bank is special:

* **bank 0** holds the 16-byte signature ``"nuvie001v1.0    "`` (in screen
  codes); the player refuses to play if it does not match.
* **bank 1** holds the control block (music flags/addresses, border and
  infoscreen colours, character set -- see :class:`Control`).
* **banks 16..143** together hold the 2048-byte playlist (16 bytes each),
  which the player assembles and runs (see :mod:`nuvie.playlist`).

SID music, when present, is stored growing *downwards* from the top of the REU
(``$FFFFF4``), 25 SID register values per 1/50 s frame.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .playlist import Playlist

BANK_SIZE = 0x10000
N_BANKS = 256
REU_SIZE = N_BANKS * BANK_SIZE  # 16 MiB
IMAGES_PER_BANK = 3
MAX_FRAMES = N_BANKS * IMAGES_PER_BANK  # 768

PART1_SIZE = 0x50  # 80 bytes
PART2_SIZE = 0x5500  # 21760 bytes
SLOT_SIZE = PART1_SIZE + PART2_SIZE  # 21840 bytes
PART2_BASE = 0x0100  # part 2 region starts here within a bank

AUX_OFFSET = 0x00F0
AUX_SIZE = 0x10

# Signature stored in bank 0's aux block (C64 screen codes for "nuvie001v1.0").
SIGNATURE = bytes(
    [0x0E, 0x15, 0x16, 0x09, 0x05, 0x30, 0x30, 0x31, 0x16, 0x31, 0x2E, 0x30, 0x20, 0x20, 0x20, 0x20]
)

# Playlist: 2048 bytes spread across the aux blocks of banks 16..143.
PLAYLIST_FIRST_BANK = 16
PLAYLIST_SIZE = 2048
PLAYLIST_BANKS = PLAYLIST_SIZE // AUX_SIZE  # 128 banks (16..143)

# Music grows downward from here (exclusive upper bound is $FFFFF5).
MUSIC_TOP = 0xFFFFF4
SID_REGS_PER_FRAME = 25


def frame_location(frame: int) -> tuple:
    """Return ``(bank, slot)`` for a frame index (0..767)."""
    if not 0 <= frame < MAX_FRAMES:
        raise IndexError(f"frame {frame} out of range 0..{MAX_FRAMES - 1}")
    return divmod(frame, IMAGES_PER_BANK)


def part1_offset(slot: int) -> int:
    return slot * PART1_SIZE


def part2_offset(slot: int) -> int:
    return PART2_BASE + slot * PART2_SIZE


@dataclass
class Control:
    """The per-movie control block (bank 1's auxiliary bytes ``$F0..$FF``)."""

    music: int = 0  # $F0: 0=none, $E8=loop, $F8=restart
    music_start: int = 0  # $F1..$F3 (lo/mid/hi)
    music_end: int = 0  # $F4..$F6 (lo/mid/hi)
    custom_code: int = 0  # $F7: $FF if custom code present
    border_lr: int = 0  # $F8
    border_tb: int = 0  # $F9
    infoscreen: int = 0  # $FA: flag (bit7) + text colour
    infoscreen_bg: int = 0  # $FB: border/background colour
    infoscreen_frames: int = 0  # $FC..$FD: display duration in frames
    charset: int = 0  # $FE: $A7 small, $A5 large
    unused: int = 0  # $FF

    @classmethod
    def from_bytes(cls, aux: bytes) -> "Control":
        if len(aux) < AUX_SIZE:
            raise ValueError("control block must be 16 bytes")
        return cls(
            music=aux[0],
            music_start=aux[1] | aux[2] << 8 | aux[3] << 16,
            music_end=aux[4] | aux[5] << 8 | aux[6] << 16,
            custom_code=aux[7],
            border_lr=aux[8],
            border_tb=aux[9],
            infoscreen=aux[10],
            infoscreen_bg=aux[11],
            infoscreen_frames=aux[12] | aux[13] << 8,
            charset=aux[14],
            unused=aux[15],
        )

    def to_bytes(self) -> bytes:
        return bytes(
            [
                self.music & 0xFF,
                self.music_start & 0xFF,
                (self.music_start >> 8) & 0xFF,
                (self.music_start >> 16) & 0xFF,
                self.music_end & 0xFF,
                (self.music_end >> 8) & 0xFF,
                (self.music_end >> 16) & 0xFF,
                self.custom_code & 0xFF,
                self.border_lr & 0xFF,
                self.border_tb & 0xFF,
                self.infoscreen & 0xFF,
                self.infoscreen_bg & 0xFF,
                self.infoscreen_frames & 0xFF,
                (self.infoscreen_frames >> 8) & 0xFF,
                self.charset & 0xFF,
                self.unused & 0xFF,
            ]
        )

    @property
    def has_music(self) -> bool:
        return self.music != 0


class Nuvie:
    """A NUVIE REU image. Read with :meth:`read`/:meth:`from_bytes`, write with
    :meth:`write`/:meth:`to_bytes`. Frames are accessed as raw 21840-byte slots."""

    def __init__(self, data: Optional[bytearray] = None):
        if data is None:
            data = bytearray(REU_SIZE)
            self._data = data
            self.set_signature()
            self.set_control(Control(charset=0xA7))
        else:
            if len(data) != REU_SIZE:
                raise ValueError(f"REU image must be exactly {REU_SIZE} bytes, got {len(data)}")
            self._data = bytearray(data)

    # --- construction ---
    @classmethod
    def from_bytes(cls, data: bytes) -> "Nuvie":
        return cls(bytearray(data))

    @classmethod
    def read(cls, path: str) -> "Nuvie":
        with open(path, "rb") as f:
            return cls(bytearray(f.read()))

    def to_bytes(self) -> bytes:
        return bytes(self._data)

    def write(self, path: str) -> None:
        with open(path, "wb") as f:
            f.write(self._data)

    # --- raw bank/aux access ---
    def aux(self, bank: int) -> bytes:
        base = bank * BANK_SIZE + AUX_OFFSET
        return bytes(self._data[base : base + AUX_SIZE])

    def set_aux(self, bank: int, value: bytes) -> None:
        if len(value) != AUX_SIZE:
            raise ValueError("aux block must be 16 bytes")
        base = bank * BANK_SIZE + AUX_OFFSET
        self._data[base : base + AUX_SIZE] = value

    # --- signature ---
    @property
    def signature(self) -> bytes:
        return self.aux(0)

    def set_signature(self) -> None:
        self.set_aux(0, SIGNATURE)

    def is_valid(self) -> bool:
        """True if the bank-0 signature matches what the player requires."""
        return self.signature == SIGNATURE

    # --- control block ---
    @property
    def control(self) -> Control:
        return Control.from_bytes(self.aux(1))

    def set_control(self, control: Control) -> None:
        self.set_aux(1, control.to_bytes())

    # --- frames ---
    def frame(self, index: int) -> bytes:
        """Return frame ``index`` as its 21840-byte slot (part 1 + part 2)."""
        bank, slot = frame_location(index)
        base = bank * BANK_SIZE
        p1 = base + part1_offset(slot)
        p2 = base + part2_offset(slot)
        return bytes(self._data[p1 : p1 + PART1_SIZE]) + bytes(self._data[p2 : p2 + PART2_SIZE])

    def set_frame(self, index: int, slot_bytes: bytes) -> None:
        """Write frame ``index`` from a 21840-byte slot (part 1 + part 2)."""
        if len(slot_bytes) != SLOT_SIZE:
            raise ValueError(f"frame slot must be {SLOT_SIZE} bytes, got {len(slot_bytes)}")
        bank, slot = frame_location(index)
        base = bank * BANK_SIZE
        p1 = base + part1_offset(slot)
        p2 = base + part2_offset(slot)
        self._data[p1 : p1 + PART1_SIZE] = slot_bytes[:PART1_SIZE]
        self._data[p2 : p2 + PART2_SIZE] = slot_bytes[PART1_SIZE:]

    def frame_is_empty(self, index: int) -> bool:
        return not any(self.frame(index))

    def count_frames(self) -> int:
        """Number of leading non-empty frame slots (best-effort frame count)."""
        n = 0
        for i in range(MAX_FRAMES):
            if self.frame_is_empty(i):
                break
            n += 1
        return n

    # --- playlist ---
    @property
    def playlist_bytes(self) -> bytes:
        out = bytearray(PLAYLIST_SIZE)
        for j in range(PLAYLIST_SIZE):
            bank = PLAYLIST_FIRST_BANK + j // AUX_SIZE
            off = bank * BANK_SIZE + AUX_OFFSET + (j % AUX_SIZE)
            out[j] = self._data[off]
        return bytes(out)

    def set_playlist_bytes(self, data: bytes) -> None:
        if len(data) > PLAYLIST_SIZE:
            raise ValueError(f"playlist must be <= {PLAYLIST_SIZE} bytes")
        data = bytes(data) + bytes(PLAYLIST_SIZE - len(data))
        for j in range(PLAYLIST_SIZE):
            bank = PLAYLIST_FIRST_BANK + j // AUX_SIZE
            off = bank * BANK_SIZE + AUX_OFFSET + (j % AUX_SIZE)
            self._data[off] = data[j]

    @property
    def playlist(self) -> Playlist:
        return Playlist.parse(self.playlist_bytes)

    def set_playlist(self, playlist: Playlist) -> None:
        self.set_playlist_bytes(playlist.to_bytes())

    # --- music ---
    def music_region(self) -> bytes:
        """Bytes from the control block's music start..end (empty if no music)."""
        c = self.control
        if not c.has_music or c.music_end <= c.music_start:
            return b""
        return bytes(self._data[c.music_start : c.music_end])

    def __len__(self) -> int:
        return MAX_FRAMES

    def __repr__(self) -> str:
        return (
            f"<Nuvie valid={self.is_valid()} frames={self.count_frames()} "
            f"music={self.control.has_music}>"
        )
