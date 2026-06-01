# pynuvie

A pure-Python library and command-line tool to **read, write and document**
Commodore 64 [NUVIE](https://www.c64-wiki.de/wiki/Nuvie) REU video files.

A NUVIE is a 16 MiB [REU](https://www.c64-wiki.com/wiki/REU) (RAM Expansion Unit)
image holding a sequence of [NUFLI](https://www.c64-wiki.com/wiki/NUFLI) still
images, an optional SID soundtrack, and a playlist that scripts playback. NUVIEs
are normally produced on a real C64 (or in VICE) with Crest's `NUVIEmaker`;
`pynuvie` reads, builds and documents the same files **without** an emulator.

The byte format is documented in [`docs/FORMAT.md`](docs/FORMAT.md), recovered by
reverse-engineering the reference player and cross-checking the published
sources. The decoder is verified frame-for-frame against Crest's `mufflon`
output (see `tests/integration`).

## Install

```sh
pip install pynuvie          # core library + CLI
pip install pynuvie[image]   # also decode/encode images (needs Pillow)
```

## Library

```python
from nuvie import Nuvie

movie = Nuvie.read("zardoz.reu")
print(movie)                         # <Nuvie valid=True frames=256 music=False>
print(movie.is_valid(), movie.count_frames())
print(movie.control)                 # music flags, borders, infoscreen, charset
for tok in movie.playlist:           # decoded playback script
    print(tok.describe())

slot = movie.frame(0)                # one frame as its 21840-byte slot
movie.set_frame(0, slot)
movie.write("out.reu")               # losslessly round-trips
```

Decode a standalone NUFLI `.nuf` image (e.g. `mufflon` output) to a picture, and
encode one back (pure-Python NUFLI, no `mufflon` — per-8×2 two-colour FLI):

```python
from nuvie.nufli import NufliImage
NufliImage.from_prg(open("000.nuf", "rb").read()).to_image().save("000.png")

from PIL import Image
# full-colour NUFLI: per-8x2 hi-res + the sprite-underlay third colour;
# optional Floyd-Steinberg dithering for the mufflon "video" look.
NufliImage.from_image(Image.open("photo.png"), third_colour=True, dither=False)
```

The decoder renders all three colours (hi-res + FLI ink/paper + sprite underlay)
and is checked frame-for-frame against mufflon's own rendering.

Encode a video into a **full-colour, player-ready** NUVIE with no `mufflon` and
no emulator:

```python
from nuvie.encode import encode_video
encode_video("clip.mp4", "clip.reu", fps=12.5)        # full per-8x2 colour + sprite underlay

from nuvie import build_movie                          # or from a list of images
build_movie([img0, img1, ...], "out.reu", dither=True)
```

Each frame is NUFLI-encoded (per-8×2 colour + the sprite-underlay third colour)
and packed into the REU exactly as Crest's `NUVIEmaker` would — `pynuvie`'s
pure-Python pack reproduces NUVIEmaker's own packed slot to 99.9% and the output
plays on the reference player. See `docs/FORMAT.md`.

## CLI

```sh
nuvie info movie.reu                 # signature, frame count, music, playlist
nuvie playlist movie.reu             # full decoded playlist
nuvie extract movie.reu -o frames/   # dump each frame as a .slot
nuvie build frames/*.slot -o out.reu # pack frame slots into a NUVIE
nuvie encode clip.mp4 -o clip.reu    # video -> NUVIE (no mufflon)
```

## License

Apache-2.0. NUVIE, NUVIEmaker, NUFLI and the reference player are the work of
Crossbow & DeeKay of Crest.
