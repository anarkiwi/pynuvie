# NUVIEmaker pack table (reverse-engineered)
Pack routine at C64 $0e00 walks an 8-byte-descriptor table at $9800:
[c64_lo, c64_hi, reu_lo, reu_mid, bankidx($12), len_lo, len_hi, term].
df01 command $fc = C64->REU stash. Frame base from zp[$12](mid)/zp[$13](bank);
frame 0 uses zp[$12]=$01 -> slot base offset $0100 (part2 at $0100, part1 $00).
C64 sources $2000+ = the loaded .nuf body (raw, +$2000); sources $1000-$1f34 =
NUVIEmaker's fixed player-displayer stub (c64_1000.bin, frame-independent).
Pure-Python replication matches the real packed slot 22002/22016 (99.9%) and plays
correctly on nuvieplayer1.0.prg. These tables/stub are derived from Crest's
NUVIEmaker and are required for format interop.

## Packer byte-parity PROVEN (vd_pack_parity.py)
Controlled test: build pynuvie's exact C64 source ($1000-$7a00) for a fixed
mufflon `.nuf`, inject it into the real NUVIEmaker in VICE, run its `$0e00`
packer, read the REU, and diff against pynuvie's own pack-table output.
Result: **0 differing bytes** in the packed frame (the only delta was the 16-byte
bank-0 signature at $F0, which the bare `$0e00` call doesn't write — and pynuvie's
signature byte-matches a genuine NUVIEmaker REU anyway). Container also matches:
signature `nuvie001v1.0`, control block (`charset=0xa7`) and the playlist head all
equal `cmp_real_nuviemaker.reu` byte-for-byte. So pynuvie's pack -> REU is
byte-identical to NUVIEmaker's for the same `.nuf`. mufflon's `--flibug` is
nondeterministic, so two mufflon runs of one frame differ regardless of packer.
