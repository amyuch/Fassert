#!/bin/sh
# cases/<case>/min — reproduce the *isolated divider* fact set (CTI/CIll).
#
# The DIV/REM interface is proved on the divider module in isolation:
#
#   benchmarks/picorv32/picorv32.sv                (identical text in the
#                                                     sandbox, see sha256 check)
#   cases/<case>/min/contract.sv                   (the proof helper: the
#                                                     per-step, entry, terminal
#                                                     and finish facts)
#
# Why isolation: the RTL side must stay *per-step and bit-level*.  The value
# invariant `dividend + N*quotient == M` needs a 32x32 product inside the
# inductive invariant of a bit-level model, which CIll does not close (UNKNOWN
# at 600 s on the isolated model, unfinished after 1.5 h on the full core).
# The product and the division theorem therefore stay in the abstract domain
# (automation/decomp/s19_div_rem_bridge.py), and only the per-step facts are
# discharged here.
#
# The environment is *over-approximated* (pcpi_rs1/rs2/insn/valid are free), so
# every fact proved here also holds in the full core, where the same divider
# module is driven by the core.  The one place where the sandbox is strictly
# more permissive is a *restart* of the divider (the core never restarts one),
# which is why the finish-edge lemmas carry a `!$past(h_start)` guard.
#
# Usage:  sh automation/decomp/cases/<case>/min/repro.sh [SANDBOX]
#
# Steps
#   1. stage the divider + the helper into SANDBOX (default /tmp/opencode/cill/t3/<case>_min)
#   2. build the BTOR and print its sha256 (the "model" id of the proof graph)
#   3. run CIll (`ric3 cill check`): BMC + inductiveness of every property
#
# RIC3 must be the local patched build (read_slang --allow-genblk-reference),
# see automation/decomp/README.md §2.
set -eu

CASE="$(basename "$(dirname -- "$(dirname -- "$0")")")"
SB="${1:-/tmp/opencode/cill/t3/${CASE}_min}"
REPO="$(CDPATH= cd -- "$(dirname -- "$0")/../../../../.." && pwd)"
SRC="$REPO/benchmarks/picorv32"
RIC3="${RIC3:-$HOME/.cargo/bin/ric3}"

rm -rf "$SB"
mkdir -p "$SB"
cp "$SRC/picorv32.sv" "$SB"/
cp "$REPO/benchmarks/riscv-formal/rvfi_macros.vh" "$SB"/
cp "$REPO/automation/decomp/cases/$CASE/min/contract.sv" "$SB"/
cp "$REPO/automation/decomp/cases/$CASE/min/ric3.toml" "$SB"/
cp "$REPO/automation/decomp/cases/$CASE/min/defines.sv" "$SB"/
# the case is the real (non-ALTOPS) divider
sed -i '/RISCV_FORMAL_ALTOPS/d' "$SB"/defines.sv

cd "$SB"
"$RIC3" build
echo "model id (BTOR sha256):"
sha256sum ric3proj/dut/dut.btor
echo
echo "CIll (BMC + inductiveness):"
"$RIC3" cill check
