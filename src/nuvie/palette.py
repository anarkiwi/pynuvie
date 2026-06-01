"""The 16-colour Commodore 64 palette (Pepto/colodore values)."""

from __future__ import annotations

from typing import List, Tuple

# Index -> (R, G, B). The classic "Pepto" PAL palette.
C64_PALETTE: List[Tuple[int, int, int]] = [
    (0x00, 0x00, 0x00),  # 0 black
    (0xFF, 0xFF, 0xFF),  # 1 white
    (0x81, 0x33, 0x38),  # 2 red
    (0x75, 0xCE, 0xC8),  # 3 cyan
    (0x8E, 0x3C, 0x97),  # 4 purple
    (0x56, 0xAC, 0x4D),  # 5 green
    (0x2E, 0x2C, 0x9B),  # 6 blue
    (0xED, 0xF1, 0x71),  # 7 yellow
    (0x8E, 0x50, 0x29),  # 8 orange
    (0x55, 0x38, 0x00),  # 9 brown
    (0xC4, 0x6C, 0x71),  # 10 light red
    (0x4A, 0x4A, 0x4A),  # 11 dark grey
    (0x7B, 0x7B, 0x7B),  # 12 grey
    (0xA9, 0xFF, 0x9F),  # 13 light green
    (0x70, 0x6D, 0xEB),  # 14 light blue
    (0xB2, 0xB2, 0xB2),  # 15 light grey
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
