"""Generate a deterministic test movie for the NUVIE integration test.

The movie is designed so a regression can be caught *automatically*, without a
human watching video. Every frame ``i`` carries machine-readable content:

* A **binary barcode** across the top encoding ``i`` (10 bits, MSB left), framed
  by always-on guard bars. Decoding any frame back to pixels must recover ``i``;
  this catches frame-count, ordering, off-by-one, bank-boundary and bitmap-decode
  regressions in one cheap check.
* **Corner fiducials** (white squares) at known positions -> geometry/registration.
* A **16-colour swatch strip** along the bottom, one C64 palette colour per
  segment -> colour decode.
* A **moving block** whose x position is a function of ``i`` -> a redundant,
  visually-obvious motion cue that also keeps consecutive frames distinct.

Content is kept inside the main hi-res bitmap area (clear of the ~48px left edge
that NUFLI renders with sprites) and uses crisp black/white so it survives
mufflon's colour quantisation and dithering deterministically.

The layout constants here are the contract shared with the decoder in
``tests/integration/test_against_nuviemaker.py`` -- keep them in sync.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from typing import List, Tuple

WIDTH, HEIGHT = 320, 200
DEFAULT_FRAMES = 256  # ~20s at 12.5fps; spans 86 REU banks (3 frames/bank)
FPS = 12

# Pepto C64 palette (index -> RGB).
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

# --- Barcode geometry (shared contract with the decoder) ---
BARCODE_BITS = 10  # encodes frame numbers 0..1023 (NUVIE max is 768)
BARCODE_X0 = 56  # clear of the ~48px left sprite-rendered edge
BARCODE_Y0 = 12
CELL_W = 20
CELL_H = 36
# Cell order on screen: [start guard][bit N-1 .. bit 0][stop guard]
N_CELLS = BARCODE_BITS + 2

# --- Corner fiducials ---
FIDUCIAL = 12
FIDUCIALS = [(52, 60), (256, 60), (52, 150), (256, 150)]

# --- Colour swatch strip ---
SWATCH_Y0 = 168
SWATCH_H = 28
SWATCH_X0 = 48
SWATCH_W = 16  # 16 colours * 16px = 256px, x 48..304


def barcode_cell_centers() -> List[Tuple[int, int]]:
    """Pixel centre of each barcode cell (incl. both guards), left to right."""
    cy = BARCODE_Y0 + CELL_H // 2
    return [(BARCODE_X0 + c * CELL_W + CELL_W // 2, cy) for c in range(N_CELLS)]


def expected_bits(i: int) -> List[int]:
    """Expected cell values for frame ``i``: [guard, bitN-1..bit0, guard]."""
    bits = [(i >> b) & 1 for b in range(BARCODE_BITS - 1, -1, -1)]
    return [1, *bits, 1]


def make_frame(i: int):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (WIDTH, HEIGHT), C64_PALETTE[0])
    d = ImageDraw.Draw(img)
    white = C64_PALETTE[1]

    # Barcode: guard + data + guard, white cell == bit set.
    for c, bit in enumerate(expected_bits(i)):
        if bit:
            x0 = BARCODE_X0 + c * CELL_W
            y0 = BARCODE_Y0
            d.rectangle([x0 + 2, y0, x0 + CELL_W - 3, y0 + CELL_H - 1], fill=white)

    # Corner fiducials.
    for fx, fy in FIDUCIALS:
        d.rectangle([fx, fy, fx + FIDUCIAL - 1, fy + FIDUCIAL - 1], fill=white)

    # Colour swatch strip.
    for k in range(16):
        x0 = SWATCH_X0 + k * SWATCH_W
        d.rectangle([x0, SWATCH_Y0, x0 + SWATCH_W - 1, SWATCH_Y0 + SWATCH_H - 1],
                    fill=C64_PALETTE[k])

    # Moving block (redundant motion cue).
    span = 230
    bx = 52 + (i * 3) % span
    d.rectangle([bx, 84, bx + 13, 97], fill=white)

    return img


def generate_pngs(outdir: str, frames: int) -> None:
    os.makedirs(outdir, exist_ok=True)
    for i in range(frames):
        make_frame(i).save(os.path.join(outdir, f"f{i:04d}.png"))


def encode_mp4(pngdir: str, out_mp4: str, frames: int) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-framerate", str(FPS),
            "-i", os.path.join(pngdir, "f%04d.png"),
            "-frames:v", str(frames),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            out_mp4,
        ],
        check=True,
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", "--frames", type=int, default=DEFAULT_FRAMES)
    ap.add_argument("-o", "--out", default="test.mp4")
    ap.add_argument("--pngdir", default=None, help="keep PNG frames in this dir")
    args = ap.parse_args()

    pngdir = args.pngdir or os.path.join(os.path.dirname(args.out) or ".", "_frames")
    generate_pngs(pngdir, args.frames)
    encode_mp4(pngdir, args.out, args.frames)
    print(f"wrote {args.frames} frames -> {args.out}")


if __name__ == "__main__":
    main()
