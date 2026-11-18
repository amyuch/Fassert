#!/bin/sh
# NeuroAbs-format artifact generation (preprocess -> Yosys -> BTOR2 + AIGER).
set -eu
cd "$(dirname "$0")"
./preprocess.sh
YOSYS="${YOSYS:-yosys}"
"$YOSYS" -q -s gen_btor.ys
"$YOSYS" -q -s gen_aiger.ys
awk '/^[0-9]+ bad /{b++} /^[0-9]+ constraint /{c++} END{printf "problem.btor2: %d bad(s), %d constraint(s)\n", b, c}' problem.btor2
echo "problem.aig:   $(head -1 problem.aig)"
