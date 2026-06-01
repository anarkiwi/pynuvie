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
