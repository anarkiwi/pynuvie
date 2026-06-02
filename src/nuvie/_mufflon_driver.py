"""Drive Crest's real ``mufflon`` binary to encode a NUFLI ``.nuf``.

This is the *original tool* backend: instead of reimplementing mufflon's colour
optimiser, shell out to the actual ``mufflon`` executable (the canonical encoder).
pynuvie then packs the resulting ``.nuf`` with its own (byte-identical) packer.

Set the binary via the ``NUVIE_MUFFLON`` environment variable or the
``mufflon_bin`` argument; otherwise ``mufflon`` is looked up on ``PATH``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

# makenuvie's video settings (YUV prep + dither, Pepto palette).
_FLAGS = ["--otype", "nufli", "-p", "--dither", "--prep_mode", "yuv",
          "--weight_u", "1", "--weight_v", "0.5", "--dest-palette", "pepto",
          "--no-truncate", "--shutup"]


def find_mufflon(mufflon_bin: str | None = None) -> str:
    cand = mufflon_bin or os.environ.get("NUVIE_MUFFLON") or "mufflon"
    path = cand if os.path.sep in cand else shutil.which(cand)
    if not path or not os.path.exists(path):
        raise FileNotFoundError(
            "mufflon binary not found; build it and set NUVIE_MUFFLON=/path/to/mufflon "
            "or pass mufflon_bin=... (or use backend='clean')")
    return path


def encode_via_mufflon(img, flibug: bool = True, mufflon_bin: str | None = None) -> bytes:
    """Encode a Pillow image to a NUFLI body (``$2000..$7A00``, no load address) by
    running the real mufflon binary. ``flibug`` adds ``--flibug`` (the left edge)."""
    binary = find_mufflon(mufflon_bin)
    work = tempfile.mkdtemp(prefix="nuvie-muf-")
    try:
        bmp = os.path.join(work, "in.bmp")
        out = os.path.join(work, "out.nuf")
        img.convert("RGB").resize((320, 200)).save(bmp)
        args = [binary, bmp, "-o", out, *_FLAGS]
        if flibug:
            args.append("--flibug")
        env = {**os.environ, "OMP_NUM_THREADS": "1"}  # deterministic
        subprocess.run(args, check=True, capture_output=True, env=env)
        data = open(out, "rb").read()
        return data[2:] if data[:2] == b"\x00\x20" else data  # strip $2000 load addr
    finally:
        shutil.rmtree(work, ignore_errors=True)
