"""Encode ordinary images / video into NUVIE frames.

:func:`encode_video` is the end-to-end entry point: it decodes a video and writes
a player-ready ``.reu`` using the FLI-aware :mod:`nuvie._clean` encoder (or the
``mufflon`` backend). :func:`encode_frame_slot` is a lightweight single-image
two-colour hi-res encoder used by the fast pipeline regression tests; it places
the hi-res bitmap at the player's bitmap address via :mod:`nuvie.slotmap`.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from typing import List, Optional

from .nufli import HEIGHT, WIDTH
from .palette import LUMA, nearest_index
from .reu import MAX_FRAMES, SLOT_SIZE, Nuvie
from .slotmap import runs

# The player streams the hi-res bitmap to this C64 address (VIC bank 3 + $2000).
BITMAP_C64_BASE = 0xE000
BITMAP_SIZE = 8000


def _hires_bitmap(indices: List[List[int]], ink: int, paper: int) -> bytearray:
    """Standard C64 hi-res bitmap: bit set where the pixel is closer to ink."""
    bmp = bytearray(BITMAP_SIZE)
    ink_luma, paper_luma = LUMA[ink], LUMA[paper]
    for y in range(HEIGHT):
        for x in range(WIDTH):
            v = LUMA[indices[y][x]]
            if abs(v - ink_luma) <= abs(v - paper_luma):
                cell = (y >> 3) * 320 + (x >> 3) * 8 + (y & 7)
                bmp[cell] |= 1 << (7 - (x & 7))
    return bmp


def _quantise(img) -> List[List[int]]:
    img = img.convert("RGB").resize((WIDTH, HEIGHT))
    px = img.load()
    return [[nearest_index(px[x, y]) for x in range(WIDTH)] for y in range(HEIGHT)]


def encode_frame_slot(img, ink: int = 1, paper: int = 0) -> bytes:
    """Encode one image into a 21840-byte NUVIE frame slot (two-colour hi-res)."""
    indices = _quantise(img)
    bmp = _hires_bitmap(indices, ink, paper)
    screen = (ink << 4) | paper
    slot = bytearray(SLOT_SIZE)
    for r in runs():
        for k in range(r.length):
            ca = r.c64 + k
            if BITMAP_C64_BASE <= ca < BITMAP_C64_BASE + BITMAP_SIZE:
                slot[r.slot + k] = bmp[ca - BITMAP_C64_BASE]
            else:
                slot[r.slot + k] = screen
    return bytes(slot)


def _video_frames(video: str, fps: float, max_frames: int):
    from PIL import Image

    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                video,
                "-vf",
                f"fps={fps},scale={WIDTH}:{HEIGHT}",
                "-frames:v",
                str(max_frames),
                os.path.join(td, "f%04d.png"),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        names = sorted(os.listdir(td))
        for n in names:
            yield Image.open(os.path.join(td, n))


def build_reu(frame_slots: List[bytes], out_path: Optional[str] = None) -> Nuvie:
    """Pack frame slots into a NUVIE with a sequential play-through playlist."""
    from .playlist import Playlist, Token

    movie = Nuvie()
    n = min(len(frame_slots), MAX_FRAMES)
    for i in range(n):
        movie.set_frame(i, frame_slots[i])
    # playlist: show frame 0, play the rest forward, wrap to the start.
    tokens = [Token(0x00, 0x00)]
    remaining = n - 1
    while remaining > 0:
        step = min(remaining, 0xFF)
        tokens.append(Token(0x91, step))  # play forward `step` frames
        remaining -= step
    tokens.append(Token(0xE8, 0x00))  # wrap to playlist start
    movie.set_playlist(Playlist(tokens))
    if out_path:
        movie.write(out_path)
    return movie


def encode_video(
    video: str,
    out_path: str,
    fps: float = 12.5,
    max_frames: int = MAX_FRAMES,
    backend: str = "clean",
    flibug: bool = True,
    cohere: float = 600.0,
    mufflon_bin=None,
) -> int:
    """Encode a video file into a full-colour, player-ready NUVIE ``.reu``.

    Decodes the video to frames, NUFLI-encodes each (``backend`` = ``"clean"``
    pynuvie FLI-aware encoder, or ``"mufflon"`` to drive the real binary; plus the
    generated left-24px flibug edge when ``flibug`` is set), packs them into REU
    slots with NUVIEmaker's layout, and writes a sequential-playback ``.reu`` that
    runs on the reference player. Returns the frame count.
    """
    from .pack import build_movie

    frames = list(_video_frames(video, fps, max_frames))
    build_movie(
        frames, out_path, backend=backend, flibug=flibug, cohere=cohere, mufflon_bin=mufflon_bin
    )
    return len(frames)
