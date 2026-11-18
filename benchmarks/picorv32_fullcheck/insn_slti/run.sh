#!/bin/sh
# Build this benchmark with rIC3 using the case-local ric3.toml.
set -eu
cd "$(dirname "$0")"
RIC3="${RIC3:-ric3}"
"$RIC3" build
echo "model id (BTOR sha256):"
sha256sum ric3proj/dut/dut.btor
