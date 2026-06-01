import subprocess,time,logging,sys,glob
logging.basicConfig(level=logging.ERROR)
sys.path.insert(0,'/scratch/anarkiwi/pynuvie/src')
from vice_driver import BinMon
from vice_driver.binmon import TAP_MODE_FIXED
from vice_driver.screen import parse_screen_response
from vice_driver.keys import chord_to_keys, text_to_chords
from nuvie.nufli import NufliImage
from nuvie.pack import _pack_source, _graphics_offsets, build_slot, _sequential_playlist
from nuvie._displayer import generate, DISPLAYER_LEN, COLOUR_COLS
from nuvie._flibug import _sprite_offsets
from nuvie.reu import Nuvie, frame_location, part1_offset, part2_offset, BANK_SIZE, SLOT_SIZE

files=sorted(glob.glob('/scratch/tmp/nuf10/*.nuf'))
go=_graphics_offsets(); ho,mo=_sprite_offsets()
extra={o for row in ho for o in row}|{o for row in mo for o in row}
for base in COLOUR_COLS: extra.update(range(base-1,base+101))
extra.update((0x1FF0,0x1FF1,0x1FF6,0x1FF7))
def make_src(path):
    body=NufliImage.from_prg(open(path,'rb').read()).body
    src=bytearray(_pack_source())
    for o in go: src[o+0x1000]=body[o]
    for o in extra: src[o+0x1000]=body[o]
    src[0:DISPLAYER_LEN]=generate(body); return bytes(src)
# pynuvie REU (reference)
mv=Nuvie()
for i,f in enumerate(files):
    nuf=NufliImage.from_prg(open(f,'rb').read()); nuf.flibug=True
    mv.set_frame(i, build_slot(nuf))
mv.set_playlist(_sequential_playlist(len(files)))
P=bytearray(); mv_bytes=mv.to_bytes() if hasattr(mv,'to_bytes') else None
mv.write('/tmp/pynref.reu'); P=open('/tmp/pynref.reu','rb').read()
sample=[0,1,2,3,62,124]
cid=subprocess.run(["docker","run","-d","--rm","-p","6502:6502","-v","/tmp/d64M:/work",
  "--entrypoint","bash","nuviemaker:local","-c",
  "mkdir -p /root/.local/state/vice /root/.config/vice /root/.cache/vice && "
  "exec /usr/local/bin/x64sc -default -binarymonitor -binarymonitoraddress ip4://0.0.0.0:6502 "
  "-warp -sounddev dummy -8 /work/nuvie.d64 -drive8type 1541 "
  "-reu -reusize 16384 -reuimage /work/out.reu -reuimagerw -autostart /work/nuvie.d64"],
  capture_output=True,text=True).stdout.strip()
def text(bm): return parse_screen_response(bm.screen_get()).text()
def waitfor(bm,kw,t=60):
    for _ in range(int(t*2)):
        if kw.lower() in text(bm).lower(): return True
        time.sleep(0.5)
    return False
def tap(bm,*n): bm.keymatrix_tap(chord_to_keys(*n),mode=TAP_MODE_FIXED,frames=15); time.sleep(0.6)
def reu_read(bm,off,length,target=0x8000):
    out=bytearray()
    while length>0:
        chunk=min(length,0x1000)
        code=bytes([0xA9,target&0xff,0x8D,0x02,0xDF,0xA9,(target>>8)&0xff,0x8D,0x03,0xDF,
          0xA9,off&0xff,0x8D,0x04,0xDF,0xA9,(off>>8)&0xff,0x8D,0x05,0xDF,0xA9,(off>>16)&0xff,0x8D,0x06,0xDF,
          0xA9,chunk&0xff,0x8D,0x07,0xDF,0xA9,(chunk>>8)&0xff,0x8D,0x08,0xDF,0xA9,0,0x8D,0x0A,0xDF,
          0xA9,0x91,0x8D,0x01,0xDF,0x60]); rts=0x9000+len(code)-1
        with bm.halted(): bm.mem_set(0x9000,code); bm.registers_set({3:0x9000})
        bm.run_until_pc(rts,timeout=6); out+=bm.mem_get(target,target+chunk-1)
        off+=chunk; length-=chunk
    return bytes(out)
try:
    time.sleep(6)
    bm=BinMon("127.0.0.1",6502); bm.connect(timeout=20,attempts=160,retry_delay=0.25); bm.exit()
    waitfor(bm,"proceed",40); tap(bm,"space"); waitfor(bm,"music"); tap(bm,"return")
    waitfor(bm,"prefix"); time.sleep(1)
    for ch in text_to_chords("aa"): tap(bm,*ch)
    tap(bm,"return"); waitfor(bm,"loading",20); time.sleep(8)
    for f in sample:
        src=make_src(files[f]); bank=f//3; slot=f%3; mid=0x01+slot*0x55
        with bm.halted():
            for i in range(0,len(src),0x800): bm.mem_set(0x1000+i, src[i:i+0x800])
            bm.mem_set(0x12, bytes([mid,bank])); bm.registers_set({3:0x0e00})
        bm.run_until_pc(0x0e7f, timeout=12)
        # read genuine part1 + part2 via DMA
        base=bank*BANK_SIZE
        p1=reu_read(bm, base+part1_offset(slot), 0x50)
        p2=reu_read(bm, base+part2_offset(slot), 0x5500)
        gslot=p1+p2
        pslot=P[base+part1_offset(slot):base+part1_offset(slot)+0x50]+P[base+part2_offset(slot):base+part2_offset(slot)+0x5500]
        d=sum(1 for i in range(len(gslot)) if gslot[i]!=pslot[i])
        dp1=sum(1 for i in range(0x50) if gslot[i]!=pslot[i])
        print('frame %3d (bank %d slot %d): slot diffs=%d (part1 diffs=%d)'%(f,bank,slot,d,dp1), flush=True)
    bm.close()
finally:
    subprocess.run(["docker","stop","-t","3",cid],capture_output=True)
