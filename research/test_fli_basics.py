#!/usr/bin/env python3
"""Emulator self-tests for the NUFLI basics (see FLI_THEORY.md).

Encodes simple, predictable patterns with nuvie._clean, packs them, plays each in
the real nuvieplayer (headless VICE in docker), screenshots, and asserts the
rendered result matches the prediction. This is the ground truth that the base
FLI/pack/displayer work -- so encoder changes can be checked against it instead
of guessing.

Usage:  python3 research/test_fli_basics.py
Needs:  the nuviemaker:local (or asid-vice) docker image, the player .prg, and
        the pynuvie src on PYTHONPATH.
"""
import os
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from nuvie._clean import encode_clean          # noqa: E402
from nuvie._flibug import encode_flibug        # noqa: E402
from nuvie.nufli import NufliImage             # noqa: E402
from nuvie.pack import build_slot, _sequential_playlist  # noqa: E402
from nuvie.palette import C64_PALETTE          # noqa: E402
from nuvie.reu import Nuvie                    # noqa: E402

PLAYER = os.environ.get("NUVIE_PLAYER", "/scratch/tmp/nuvieplayer1.0.prg")
IMAGE = os.environ.get("NUVIE_DOCKER", "asid-vice:latest")


def make_reu(rgb, path):
    img = Image.fromarray(rgb, "RGB")
    body = encode_clean(rgb)
    encode_flibug(img, body, has_main=True)
    nuf = NufliImage(bytes(body))
    nuf.flibug = True
    mv = Nuvie()
    mv.set_frame(0, build_slot(nuf))
    mv.set_playlist(_sequential_playlist(1))
    mv.write(path)


def screenshot(reu, out_png, cycles=40000000):
    work = tempfile.mkdtemp()
    subprocess.run(["cp", reu, f"{work}/movie.reu"], check=True)
    subprocess.run(["cp", PLAYER, f"{work}/player.prg"], check=True)
    subprocess.run([
        "docker", "run", "--rm", "-v", f"{work}:/work", "--entrypoint", "bash", IMAGE, "-c",
        "mkdir -p /root/.local/state/vice /root/.config/vice /root/.cache/vice; "
        "export SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy; "
        f"timeout 90 x64sc -warp -limitcycles {cycles} -reu -reusize 16384 "
        "-reuimage /work/movie.reu -reuimagerw -autostart /work/player.prg "
        "-exitscreenshot /work/shot.png >/work/log 2>&1",
    ], check=False)
    subprocess.run(["cp", f"{work}/shot.png", out_png], check=False)
    return out_png


def active(png):
    im = np.asarray(Image.open(png).convert("RGB"))
    m = im.sum(2) > 20
    ys, xs = np.where(m)
    a = im[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    return a[:, 40:]   # skip the leftmost flibug edge (its own concern)


def check_solid(png):
    a = active(png)
    std = a.reshape(-1, 3).std(0).mean()
    ok = std < 12
    print(f"  solid: per-channel stddev {std:.1f} (want <12) -> {'PASS' if ok else 'FAIL'}")
    return ok


def check_bands(png, n=16):
    a = active(png)
    rows = a.mean(1)                       # (H,3) mean colour per row
    # count distinct horizontal bands (consecutive rows with a colour jump)
    jumps = 1 + int(np.sum(np.abs(np.diff(rows, axis=0)).sum(1) > 30))
    ok = abs(jumps - n) <= 4
    print(f"  bands: ~{jumps} colour bands (want ~{n}) -> {'PASS' if ok else 'FAIL'}")
    return ok


def main():
    tmp = tempfile.mkdtemp()
    pal = np.array(C64_PALETTE, np.uint8)
    results = []

    rgb = np.zeros((200, 320, 3), np.uint8)
    rgb[:] = C64_PALETTE[12]
    make_reu(rgb, f"{tmp}/solid.reu")
    results.append(check_solid(screenshot(f"{tmp}/solid.reu", f"{tmp}/solid.png")))

    rgb = np.zeros((200, 320, 3), np.uint8)
    for i in range(16):
        rgb[i * 12:(i + 1) * 12] = pal[i]
    make_reu(rgb, f"{tmp}/bands.reu")
    results.append(check_bands(screenshot(f"{tmp}/bands.reu", f"{tmp}/bands.png")))

    print("RESULT:", "ALL PASS" if all(results) else "SOME FAILED")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
