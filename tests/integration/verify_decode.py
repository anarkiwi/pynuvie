#!/usr/bin/env python3
"""Validate pynuvie's NUFLI decoder against the real ``mufflon`` (old stack).

Generates the test movie's frames, runs them through ``mufflon`` inside the
``nuviemaker:local`` Docker image to produce real ``.nuf`` NUFLI images, decodes
those with :mod:`nuvie.nufli`, reads the per-frame barcode, and asserts it equals
the frame index.

Requires Docker + the ``nuviemaker:local`` image (see README). Run manually.
"""

import glob
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import make_movie as mm

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))
from nuvie.nufli import NUIFLI_SCRAM, NufliImage

IMAGE = "nuviemaker:local"
N = 32  # frames to convert


def _ink(img: NufliImage, col: int, line_pair: int) -> int:
    return (img.body[NUIFLI_SCRAM[line_pair] + col] >> 4) & 0xF


def _decode_barcode_index(img: NufliImage) -> int:
    bits = []
    for cx_px, cy in mm.barcode_cell_centers():
        # a barcode cell is "set" if its FLI ink colour is light (white-ish)
        from nuvie.palette import LUMA

        ink = _ink(img, cx_px // 8, cy // 2)
        bits.append(1 if LUMA[ink] > 128 else 0)
    assert bits[0] == 1 and bits[-1] == 1, "guard bars missing"
    val = 0
    for b in bits[1:-1]:
        val = (val << 1) | b
    return val


def main() -> int:
    with tempfile.TemporaryDirectory() as work:
        for i in range(N):
            mm.make_frame(i).save(os.path.join(work, f"aa{i + 1:03d}.bmp"))
        # run mufflon on every bmp inside the image
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-v",
                f"{work}:/work",
                "--entrypoint",
                "bash",
                IMAGE,
                "-c",
                "cd /work && for f in *.bmp; do mufflon $f --flibug -p --dither "
                "--prep_mode yuv >/dev/null 2>&1; done",
            ],
            check=True,
        )
        ok = 0
        for path in sorted(glob.glob(os.path.join(work, "*.nuf"))):
            m = re.match(r"aa(\d+)\s*\.nuf$", os.path.basename(path))
            if not m:
                continue
            frame = int(m.group(1)) - 1
            with open(path, "rb") as f:
                img = NufliImage.from_prg(f.read())
            got = _decode_barcode_index(img)
            status = "ok" if got == frame else "MISMATCH"
            if got != frame:
                print(f"  frame {frame}: decoded {got} [{status}]")
            ok += got == frame
        total = len(glob.glob(os.path.join(work, "*.nuf")))
        print(f"{ok}/{total} frames decoded to the correct barcode index")
        return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
