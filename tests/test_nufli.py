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
