#!/bin/sh
# Reproduce the portable certificate/composition checks and, if the sandboxes
# exist, the focused RTL/BTOR checks. See README.md.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
RIC3=${RIC3:-/home/AM2/sec/cur_work/fasten/benchmarks/src/cill_exp/rIC3/target/release/ric3}
SB=/tmp/opencode/cill/t3

echo "== toolchain =="
python3 -c "import z3; print('z3', z3.get_version_string())" 2>/dev/null || echo "z3 missing"
command -v yosys >/dev/null && yosys -V 2>/dev/null | head -1 || echo "yosys missing"
[ -x "$RIC3" ] && echo "ric3: $RIC3" || echo "ric3: not found at $RIC3"

echo
echo "== portable z3 suite =="
for s in s1_compose s2_check_cert s3_synth_cert s4_div_analysis \
         s5_temporal s6_proofgraph s13_div_delta s14_div_signed \
         s15_div_signed_interface s16_div_branch_selection \
         s18_rem_compose s19_div_rem_bridge; do
    echo "--- $s ---"
    python3 -u "$HERE/$s.py" 2>&1 | tail -3
done

echo
echo "== committed isolated divider models (rebuild + CIll) =="
for c in cases/div/min cases/rem/min; do
    if [ -x "$RIC3" ]; then
        echo "--- $c ---"
        sh "$HERE/$c/repro.sh" "${TMPDIR:-/tmp}/div_min_repro_$$" 2>&1 | tail -6
    else
        echo "--- $c : skipped (ric3 missing) ---"
    fi
done

echo
echo "== kernel (L3 structural checks) =="
for g in cases/*/proof_graph.json; do
    python3 "$HERE/kernel.py" "$HERE/$g"
done
python3 "$HERE/kernel.py" --selftest 2>&1 | tail -2

echo
echo "== focused RTL/BTOR checks (sandboxes in $SB) =="
for d in kernel_l4 kernel_div_l4 kernel_m2 kernel_div_m2 kernel_div_pc; do
    if [ -d "$SB/$d" ] && [ -x "$RIC3" ]; then
        echo "--- $d : cill check ---"
        ( cd "$SB/$d" && timeout 900 "$RIC3" cill check 2>&1 | tail -4 )
    else
        echo "--- $d : skipped (sandbox or ric3 missing) ---"
    fi
done

echo
echo "== BTOR artifact scripts (need sandboxes) =="
for s in s7_kernel_mul s9_mul_o6 s10_mul_rvfi s17_div_observation; do
    echo "--- $s ---"
    python3 -u "$HERE/$s.py" 2>&1 | tail -3 || true
done
