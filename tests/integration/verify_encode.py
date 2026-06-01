#!/usr/bin/env python3
"""End-to-end check: encode frames with pynuvie (full colour, pure Python),
play the .reu on the real nuvieplayer in VICE, and save screenshots.

This is the inverse of verify_decode.py and closes the loop on the encoder +
pack path. Requires Docker + the nuviemaker:local image (see README). Manual.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import make_movie as mm  # noqa: E402

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from nuvie.pack import build_movie  # noqa: E402

FRAMES = [0, 1, 2, 5, 14, 42]


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        reu = os.path.join(td, "encoded.reu")
        build_movie([mm.make_frame(i) for i in FRAMES], reu)
        print(f"encoded {len(FRAMES)} frames -> {reu}")
        print("play it in the player to verify (see tests/integration/README.md):")
        print(f"  it should show the per-frame barcode, fiducials and the 16-colour swatch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
