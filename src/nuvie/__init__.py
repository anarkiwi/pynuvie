"""pynuvie -- read, write and document Commodore 64 NUVIE REU video files.

The :class:`~nuvie.reu.Nuvie` class is the entry point for the container format.
:mod:`nuvie.nufli` decodes the still-image frames, :mod:`nuvie.playlist` handles
the playback script, and :mod:`nuvie.slotmap` documents how a frame's bytes are
streamed into the C64 by the reference player.
"""

from .nufli import NufliImage
from .pack import build_movie, build_slot
from .palette import C64_PALETTE
from .playlist import Playlist, Token, TokenKind
from .reu import Control, Nuvie

try:
    from importlib.metadata import version

    __version__ = version("pynuvie")
except Exception:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = [
    "Nuvie",
    "Control",
    "NufliImage",
    "Playlist",
    "Token",
    "TokenKind",
    "C64_PALETTE",
    "build_movie",
    "build_slot",
    "__version__",
]
