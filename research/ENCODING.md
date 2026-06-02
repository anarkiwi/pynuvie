# Encoding: the clean encoder, the mufflon backend, and packer parity

Background notes that used to live in the README. For the format itself see
[`../docs/FORMAT.md`](../docs/FORMAT.md); for the FLI hardware model see
[`FLI_THEORY.md`](FLI_THEORY.md).

## Two backends

`NufliImage.from_image(img, backend=...)` has two encoders:

* **`clean`** (default, pure-Python, no external tools) — `nuvie._clean`. A
  clean-slate, FLI-structure-aware encoder. It does *not* reimplement mufflon.
* **`mufflon`** — `nuvie._mufflon_driver` shells out to Crest's real `mufflon`
  binary (set `NUVIE_MUFFLON` or pass `mufflon_bin=`). The original tool's
  encoding, packed by pynuvie.

## Why a clean encoder

mufflon dithers the image to the 16 solid C64 colours first and *then* collapses
each 8×2 cell to its 2–3 hardware-realisable colours with no error feedback. The
two stages optimise different palettes, which is what produces the blocky/noisy
look. The clean encoder instead **co-designs the dither with the FLI structure**:

* per 8×2 cell it picks `ink`/`paper`, and per 48px region the shared sprite
  colour, *jointly* (a few coordinate-descent passes), so the chosen colours are
  ones the hardware can actually show;
* a **vertical-coherence** penalty (`cohere`) discourages changing a cell's
  colours from the line-pair above, which is what stops horizontal streaking;
* it then dithers at the **2px sprite-pair** granularity (the real hardware unit:
  each pair is one of the 7 valid ink/paper/sprite combinations) and **diffuses
  the residual** (Floyd-Steinberg), so the quantisation error mufflon drops is
  spread to neighbours;
* a **texture** knob blends the cell colour metric between nearest-endpoint error
  (flat, lowest MSE) and distance-to-the-ink↔paper-segment (lets the dither blend
  bracketing colours — mufflon-like high-frequency texture). `texture≈0.7` lands
  at roughly mufflon's MSE while keeping the texture.

The encoder works in YUV with perceptual channel weights and is deterministic.
`numba` JITs the dither and the per-cell cost geometry; output is byte-identical
with or without it.

## Packer parity (byte-identical to NUVIEmaker)

pynuvie's pure-Python packer reproduces NUVIEmaker's packed REU slot **byte for
byte**. This was proven by injecting the same source frames into the real
NUVIEmaker (running under VICE) and diffing the resulting REU images: 0 bytes
differ. See [`nuviemaker_pack`](nuviemaker_pack).

## History: the byte-identical mufflon port

An earlier version of pynuvie carried a full Python port of mufflon's colour
optimiser. For any input whose pixels were exact C64 **Pepto** colours it produced
NUFLI graphics byte-for-byte identical to `mufflon --otype nufli`. For arbitrary
RGB the only differences came from mufflon being built with `-ffast-math`, whose
1-ULP rounding flips the occasional colour tie (a strict-IEEE mufflon build agrees
far more closely). mufflon's `--flibug` left-edge plane was never byte-reproducible
because mufflon generates it non-deterministically (OpenMP, run-to-run variance).

That port was removed once the clean encoder matched it on quality: maintaining a
bug-for-bug reimplementation added nothing over driving the real binary, which the
`mufflon` backend now does. pynuvie still generates the left-24px flibug edge
itself, deterministically (`nuvie._flibug`).
