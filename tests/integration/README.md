# Integration tests

These exercise `pynuvie` against the **real** Crest tooling — `mufflon` (the
NUFLI encoder) and `nuvieplayer1.0.prg` (the reference player) — running inside
the [`docker-nuviemaker`](https://github.com/anarkiwi/docker-nuviemaker) image.
They are **not** run in CI (they need Docker, the built image, and network);
they are how we check `pynuvie` against the original stack and catch regressions
without watching video by eye.

The portable, no-emulator regression test lives in `tests/test_encode.py`: it
encodes frames carrying a per-frame **barcode of their index**, round-trips them
through the container + DMA map, and asserts each frame still decodes to its
index. That runs in CI.

## `make_movie.py`

Generates a deterministic test movie whose every frame encodes its index as a
binary barcode (plus corner fiducials, a 16-colour swatch strip and a moving
block). The barcode is the automation hook: any decode regression makes a
frame's barcode stop matching its index. Used by both the portable test and the
Docker checks.

```sh
python tests/integration/make_movie.py -n 256 -o test.mp4
```

## Docker checks (manual)

Build the image once:

```sh
docker build -t nuviemaker:local ../docker-nuviemaker
```

* **`verify_decode.py`** — feeds the generated frames to the real `mufflon` to
  produce `.nuf` NUFLI images, decodes them with `pynuvie`'s `nuvie.nufli`, and
  asserts the barcode of each decoded frame matches its index. This validates
  `pynuvie`'s NUFLI decoder against the old stack.

  ```sh
  python tests/integration/verify_decode.py
  ```

Note: the headless VICE build in the image needs its state dirs to exist
(`/root/.local/state/vice`, `/root/.config/vice`) or `x64sc` segfaults; the
helper scripts create them.
