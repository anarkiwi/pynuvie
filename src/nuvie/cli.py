"""Command-line interface for pynuvie."""

from __future__ import annotations

import argparse
import os
import sys

from .reu import SLOT_SIZE, Nuvie


def _cmd_info(args) -> int:
    movie = Nuvie.read(args.reu)
    c = movie.control
    print(f"file:       {args.reu}")
    print(f"signature:  {'valid' if movie.is_valid() else 'INVALID'} ({movie.signature!r})")
    print(f"frames:     {movie.count_frames()} (capacity {len(movie)})")
    print(f"music:      {'yes' if c.has_music else 'no'}", end="")
    if c.has_music:
        print(f"  (${c.music_start:06x}..${c.music_end:06x}, flag ${c.music:02x})")
    else:
        print()
    print(f"borders:    lr=${c.border_lr:02x} tb=${c.border_tb:02x}")
    print(f"infoscreen: flag=${c.infoscreen:02x} frames={c.infoscreen_frames}")
    print(f"charset:    ${c.charset:02x}")
    pl = movie.playlist
    print(f"playlist:   {len(pl)} tokens")
    for tok in list(pl)[: args.playlist_limit]:
        print(f"    ${tok.cmd:02x} ${tok.value:02x}  {tok.describe()}")
    if len(pl) > args.playlist_limit:
        print(f"    ... ({len(pl) - args.playlist_limit} more)")
    return 0


def _cmd_playlist(args) -> int:
    movie = Nuvie.read(args.reu)
    for i, tok in enumerate(movie.playlist):
        print(f"{i:4d}: ${tok.cmd:02x} ${tok.value:02x}  {tok.describe()}")
    return 0


def _cmd_extract(args) -> int:
    movie = Nuvie.read(args.reu)
    os.makedirs(args.out, exist_ok=True)
    n = movie.count_frames() if args.frames is None else args.frames
    for i in range(n):
        with open(os.path.join(args.out, f"frame{i:04d}.slot"), "wb") as f:
            f.write(movie.frame(i))
    print(f"extracted {n} frames to {args.out}")
    return 0


def _cmd_build(args) -> int:
    movie = Nuvie()
    for i, path in enumerate(args.slots):
        with open(path, "rb") as f:
            data = f.read()
        if len(data) != SLOT_SIZE:
            print(f"error: {path} is {len(data)} bytes, expected {SLOT_SIZE}", file=sys.stderr)
            return 1
        movie.set_frame(i, data)
    movie.write(args.out)
    print(f"wrote {len(args.slots)} frames to {args.out}")
    return 0


def _cmd_encode(args) -> int:
    from .encode import encode_video

    n = encode_video(
        args.video,
        args.out,
        fps=args.fps,
        max_frames=args.max_frames,
        backend=args.backend,
        mufflon_bin=args.mufflon_bin,
    )
    print(f"encoded {n} frames from {args.video} to {args.out}")
    return 0


def _cmd_testpattern(args) -> int:
    from .testpattern import build

    movie = build(args.out, n=args.frames, style=args.style, backend=args.backend)
    print(f"wrote {movie.count_frames()}-frame test pattern to {args.out}")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="nuvie", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("info", help="summarise a .reu nuvie")
    pi.add_argument("reu")
    pi.add_argument("--playlist-limit", type=int, default=16)
    pi.set_defaults(func=_cmd_info)

    pp = sub.add_parser("playlist", help="dump the playlist tokens")
    pp.add_argument("reu")
    pp.set_defaults(func=_cmd_playlist)

    pe = sub.add_parser("extract", help="extract frame slots from a .reu")
    pe.add_argument("reu")
    pe.add_argument("-o", "--out", required=True)
    pe.add_argument("-n", "--frames", type=int, default=None)
    pe.set_defaults(func=_cmd_extract)

    pb = sub.add_parser("build", help="pack frame slots into a .reu")
    pb.add_argument("slots", nargs="+")
    pb.add_argument("-o", "--out", required=True)
    pb.set_defaults(func=_cmd_build)

    pn = sub.add_parser("encode", help="encode a video file into a .reu")
    pn.add_argument("video")
    pn.add_argument("-o", "--out", required=True)
    pn.add_argument("--fps", type=float, default=12.5)
    pn.add_argument("--max-frames", type=int, default=768)
    pn.add_argument("--backend", choices=("clean", "mufflon"), default="clean")
    pn.add_argument("--mufflon-bin", default=None)
    pn.set_defaults(func=_cmd_encode)

    pt = sub.add_parser(
        "testpattern", help="generate an animated test-pattern .reu (no video needed)"
    )
    pt.add_argument("-o", "--out", required=True)
    pt.add_argument("-n", "--frames", type=int, default=64)
    pt.add_argument("--style", choices=("colour", "greyscale"), default="colour")
    pt.add_argument("--backend", choices=("clean", "mufflon"), default="clean")
    pt.set_defaults(func=_cmd_testpattern)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
