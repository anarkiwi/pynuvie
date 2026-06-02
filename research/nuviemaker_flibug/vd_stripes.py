import subprocess, time, logging

logging.basicConfig(level=logging.ERROR)
from vice_driver import BinMon
from vice_driver.binmon import TAP_MODE_FIXED
from vice_driver.screen import parse_screen_response
from vice_driver.keys import chord_to_keys, text_to_chords

cid = subprocess.run(
    [
        "docker",
        "run",
        "-d",
        "--rm",
        "-p",
        "6502:6502",
        "-v",
        "/tmp/d64S:/work",
        "--entrypoint",
        "bash",
        "nuviemaker:local",
        "-c",
        "mkdir -p /root/.local/state/vice /root/.config/vice /root/.cache/vice && "
        "exec /usr/local/bin/x64sc -default -binarymonitor -binarymonitoraddress ip4://0.0.0.0:6502 "
        "-warp -sounddev dummy -8 /work/nuvie.d64 -drive8type 1541 "
        "-reu -reusize 16384 -reuimage /work/out.reu -reuimagerw -autostart /work/nuvie.d64",
    ],
    capture_output=True,
    text=True,
).stdout.strip()


def text(bm):
    return parse_screen_response(bm.screen_get()).text()


def waitfor(bm, kw, t=60):
    for _ in range(int(t * 2)):
        if kw.lower() in text(bm).lower():
            return True
        time.sleep(0.5)
    return False


def tap(bm, *n):
    bm.keymatrix_tap(chord_to_keys(*n), mode=TAP_MODE_FIXED, frames=15)
    time.sleep(0.6)


def reu_read(bm, off, length, target=0x8000):
    code = bytes(
        [
            0xA9,
            target & 0xFF,
            0x8D,
            0x02,
            0xDF,
            0xA9,
            (target >> 8) & 0xFF,
            0x8D,
            0x03,
            0xDF,
            0xA9,
            off & 0xFF,
            0x8D,
            0x04,
            0xDF,
            0xA9,
            (off >> 8) & 0xFF,
            0x8D,
            0x05,
            0xDF,
            0xA9,
            (off >> 16) & 0xFF,
            0x8D,
            0x06,
            0xDF,
            0xA9,
            length & 0xFF,
            0x8D,
            0x07,
            0xDF,
            0xA9,
            (length >> 8) & 0xFF,
            0x8D,
            0x08,
            0xDF,
            0xA9,
            0,
            0x8D,
            0x0A,
            0xDF,
            0xA9,
            0x91,
            0x8D,
            0x01,
            0xDF,
            0x60,
        ]
    )
    rts = 0x9000 + len(code) - 1
    with bm.halted():
        bm.mem_set(0x9000, code)
        bm.registers_set({3: 0x9000})
    bm.run_until_pc(rts, timeout=6)
    return bm.mem_get(target, target + length - 1)


try:
    time.sleep(5)
    bm = BinMon("127.0.0.1", 6502)
    bm.connect(timeout=20, attempts=160, retry_delay=0.25)
    bm.exit()
    waitfor(bm, "proceed", 40)
    tap(bm, "space")
    waitfor(bm, "music")
    tap(bm, "return")
    waitfor(bm, "prefix")
    time.sleep(1)
    for ch in text_to_chords("aa"):
        tap(bm, *ch)
    tap(bm, "return")
    waitfor(bm, "loading", 20)
    time.sleep(10)
    print("SCREEN after load:\n", text(bm)[:400], flush=True)
    # capture the generated displayer for the stripes frame
    with bm.halted():
        disp = bm.mem_get(0x1000, 0x1FFF)
    open("/tmp/stripes_displayer.bin", "wb").write(disp)
    print("displayer $1000-$1fff captured, nonzero", sum(1 for x in disp if x), flush=True)
    # call pack on frame 0
    with bm.halted():
        bm.mem_set(0x12, bytes([0x01, 0x00]))
        bm.registers_set({3: 0x0E00})
    bm.run_until_pc(0x0E7F, timeout=10)
    buf = bytearray()
    for off in range(0, 0x5600, 0x800):
        buf += reu_read(bm, off, min(0x800, 0x5600 - off))
    open("/tmp/stripes_slot.bin", "wb").write(buf)
    print("packed slot captured, nonzero", sum(1 for x in buf if x), flush=True)
    bm.close()
finally:
    subprocess.run(["docker", "stop", "-t", "2", cid], capture_output=True)
