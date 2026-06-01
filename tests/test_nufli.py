from nuvie.nufli import NUFLI_BODY_SIZE, NUIFLI_SCRAM, NufliImage


def _set_bitmap_byte(body, logical_index, value):
    # logical bitmap[0:0x1400] -> body[0x4000:], [0x1400:0x1f40] -> body[0x1400:]
    if logical_index < 0x1400:
        body[0x4000 + logical_index] = value
    else:
        body[0x1400 + (logical_index - 0x1400)] = value


def test_scram_table_complete():
    assert len(NUIFLI_SCRAM) == 100


def test_from_prg_strips_load_address():
    body = bytes([0xAA]) * NUFLI_BODY_SIZE
    img = NufliImage.from_prg(b"\x00\x20" + body)
    assert img.body[:4] == body[:4]


def test_decode_single_cell():
    body = bytearray(NUFLI_BODY_SIZE)
    # top-left cell: ink=white(1), paper=black(0)
    body[NUIFLI_SCRAM[0]] = 0x10
    # row 0 bitmap: leftmost pixel set
    _set_bitmap_byte(body, 0, 0x80)
    px = NufliImage(bytes(body)).decode_indices()
    assert px[0][0] == 1  # ink (bit set)
    assert px[0][1] == 0  # paper (bit clear)


def test_decode_uses_per_cell_color():
    body = bytearray(NUFLI_BODY_SIZE)
    # cell (col=3, line_pair=0): ink=green(5), paper=blue(6)
    body[NUIFLI_SCRAM[0] + 3] = (5 << 4) | 6
    # set whole 8x1 row (y=0) of that cell to ink
    _set_bitmap_byte(body, 3 * 8 + 0, 0xFF)
    px = NufliImage(bytes(body)).decode_indices()
    for x in range(24, 32):
        assert px[0][x] == 5
    # a different cell with default 0 -> paper 0
    assert px[0][0] == 0


def test_decode_dimensions():
    px = NufliImage(bytes(NUFLI_BODY_SIZE)).decode_indices()
    assert len(px) == 200
    assert all(len(row) == 320 for row in px)


def test_from_image_roundtrip_and_constraints():
    pytest = __import__("pytest")
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (320, 200), (0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 150, 100], fill=(255, 0, 0))
    d.ellipse([170, 30, 300, 160], fill=(0, 200, 80))
    nuf = NufliImage.from_image(img)
    dec = nuf.decode_indices()
    # encoding the decoded image must reproduce the same bytes (stable codec)
    assert NufliImage.from_image(nuf.to_image()).body == nuf.body
    # every 8x2 block uses at most two colours (the FLI constraint)
    for by in range(100):
        for cx in range(40):
            cols = {dec[by * 2 + dy][cx * 8 + dx] for dy in range(2) for dx in range(8)}
            assert len(cols) <= 2
    # a colourful image must use more than two colours overall
    assert len({v for row in dec for v in row}) > 2


def test_to_prg_has_load_address():
    nuf = NufliImage(bytes(NUFLI_BODY_SIZE))
    prg = nuf.to_prg()
    assert prg[:2] == b"\x00\x20"
    assert len(prg) == NUFLI_BODY_SIZE + 2


def _mse(a, b, x_range):
    pa, pb = a.load(), b.load()
    s = n = 0
    for y in range(200):
        for x in x_range:
            for k in range(3):
                s += (pa[x, y][k] - pb[x, y][k]) ** 2
            n += 1
    return s // n


def test_sprite_underlay_matches_mufflon():
    """Decode a real mufflon .nuf and check the sprite-underlay third colour
    matches mufflon's own rendering across the main image area."""
    import os

    pytest = __import__("pytest")
    pytest.importorskip("PIL")
    from PIL import Image

    here = os.path.join(os.path.dirname(__file__), "fixtures")
    nuf = NufliImage.from_prg(open(os.path.join(here, "nufli_sample.nuf"), "rb").read())
    ref = Image.open(os.path.join(here, "nufli_sample_result.png")).convert("RGB")
    main = range(24, 312)
    with_sprites = _mse(nuf.to_image(), ref, main)
    without = _mse(NufliImage(nuf.body).to_image_nosprites(), ref, main)
    # the third colour must bring us much closer to mufflon, near the noise floor
    assert with_sprites < without
    assert with_sprites < 3000
