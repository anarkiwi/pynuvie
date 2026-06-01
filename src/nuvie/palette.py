"""The 16-colour Commodore 64 palette (Pepto PAL values, as mufflon uses)."""

from __future__ import annotations

from typing import List, Tuple

# Index -> (R, G, B). The "Pepto" PAL palette -- the same values mufflon encodes
# against (its palette_pepto), so pynuvie's colour choices match mufflon's and the
# reference player's rendering.
C64_PALETTE: List[Tuple[int, int, int]] = [
    (0x00, 0x00, 0x00),  # 0 black
    (0xFF, 0xFF, 0xFF),  # 1 white
    (0x68, 0x37, 0x2B),  # 2 red
    (0x70, 0xA4, 0xB2),  # 3 cyan
    (0x6F, 0x3D, 0x86),  # 4 purple
    (0x58, 0x8D, 0x43),  # 5 green
    (0x35, 0x28, 0x79),  # 6 blue
    (0xB8, 0xC7, 0x6F),  # 7 yellow
    (0x6F, 0x4F, 0x25),  # 8 orange
    (0x43, 0x39, 0x00),  # 9 brown
    (0x9A, 0x67, 0x59),  # 10 light red
    (0x44, 0x44, 0x44),  # 11 dark grey
    (0x6C, 0x6C, 0x6C),  # 12 grey
    (0x9A, 0xD2, 0x84),  # 13 light green
    (0x6C, 0x5E, 0xB5),  # 14 light blue
    (0x95, 0x95, 0x95),  # 15 light grey
]

# Perceived luma per palette index (Rec. 601), useful for nearest-colour work.
LUMA: List[float] = [0.299 * r + 0.587 * g + 0.114 * b for (r, g, b) in C64_PALETTE]


def nearest_index(rgb: Tuple[int, int, int]) -> int:
    """Nearest C64 palette index to an RGB triple (squared-distance)."""
    r, g, b = rgb
    best_i, best_d = 0, 1 << 30
    for i, (pr, pg, pb) in enumerate(C64_PALETTE):
        d = (pr - r) ** 2 + (pg - g) ** 2 + (pb - b) ** 2
        if d < best_d:
            best_i, best_d = i, d
    return best_i
