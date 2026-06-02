import subprocess, time, logging, struct

logging.basicConfig(level=logging.ERROR)
from vice_driver import BinMon
from vice_driver.binmon import TAP_MODE_FIXED, CHECK_STORE
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
        "/tmp/d64V:/work",
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


def pc(bm):
    regs = bm.registers_get()
    return regs.get(3)


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
    # watchpoint: stop on store to $1ff7 (hires flibug initial colour)
    cp = bm.checkpoint_set(0x1FF7, 0x1FF7, op=CHECK_STORE, stop_when_hit=True)
    for ch in text_to_chords("aa"):
        tap(bm, *ch)
    tap(bm, "return")
    # catch writes to $1ff7 during load
    hits = []
    for _ in range(8):
        try:
            bm.run_until_pc(0x1FF7, timeout=8)  # won't match; rely on watchpoint stop
        except Exception:
            pass
        p = pc(bm)
        if p is not None:
            hits.append(p)
        time.sleep(0.2)
    print("PCs near $1ff7 store:", [hex(h) for h in hits], flush=True)
    # also dump code around likely generator (read $0800-$2400 again for offline disasm)
    with bm.halted():
        code = bm.mem_get(0x0800, 0x2400)
    open("/tmp/nm_code2.bin", "wb").write(code)
    bm.close()
finally:
    subprocess.run(["docker", "stop", "-t", "2", cid], capture_output=True)
