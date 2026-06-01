#!/bin/sh
# Play a NUVIE .reu on the C64 via VICE's x64sc.
#   ./play.sh [file.reu]            (defaults to test-play.reu)
#
# Notes:
#  * -reusize 16384 is REQUIRED: a NUVIE is a full 16 MiB REU. Without it VICE
#    uses a small default REU, the 16 MiB image won't load, and the player shows
#    "no valid nuvie data found".
#  * +reuimagerw attaches the image read-only, so VICE never writes/erases it
#    (no need to keep a spare copy).
#  * nuvieplayer1.0.prg is Crest's NUVIE player (bundled here for convenience).
set -e
cd "$(dirname "$0")"
REU="${1:-test-play.reu}"
exec x64sc -warp \
    -reu -reusize 16384 -reuimage "$REU" +reuimagerw \
    -autostart nuvieplayer1.0.prg
