#!/bin/sh
# cases/rem — reproduce the REM transfer case from the repository.
#
# The proof *helper* (tb.sv) is committed here; the rest of the model comes
# from the repository sources:
#
#   benchmarks/picorv32/insn_rem/                (core + wrapper + defines)
#   benchmarks/riscv-formal/insn/insn_rem.v      (architectural spec)
#
# The sandbox is provisioned under /tmp (ephemeral) because the model build is
# large; only the helper text and the config live in the repository, so the
# helper assertions that back every "PROVED_TRUSTED" link are auditable.
#
# Usage:  sh automation/decomp/cases/rem/repro.sh [SANDBOX]
#
# Steps
#   1. stage the case into SANDBOX (default /tmp/opencode/cill/t3/rem_case)
#   2. build the BTOR and print its sha256 (the "model" id of the proof graph)
#   3. run CIll (`ric3 cill check`): BMC + inductiveness of every property
#
# RIC3 must be the local patched build (read_slang --allow-genblk-reference),
# see automation/decomp/README.md §2.
set -eu

SB="${1:-/tmp/opencode/cill/t3/rem_case}"
REPO="$(CDPATH= cd -- "$(dirname -- "$0")/../../../.." && pwd)"
SRC="$REPO/benchmarks/picorv32/insn_rem"
SPEC="$REPO/benchmarks/riscv-formal/insn/insn_rem.v"
RIC3="${RIC3:-$HOME/.cargo/bin/ric3}"

rm -rf "$SB"
mkdir -p "$SB"
cp -rL "$SRC"/. "$SB"/
cp "$SPEC" "$SB"/insn_rem.v
cp "$REPO/automation/decomp/cases/rem/tb.sv" "$SB"/tb.sv
cp "$REPO/automation/decomp/cases/rem/ric3.toml" "$SB"/ric3.toml
cp "$REPO/automation/decomp/cases/rem/defines.sv" "$SB"/defines.sv
# the case is the real (non-ALTOPS) divider
sed -i '/RISCV_FORMAL_ALTOPS/d' "$SB"/defines.sv

cd "$SB"
"$RIC3" build
echo "model id (BTOR sha256):"
sha256sum ric3proj/dut/dut.btor
echo
echo "CIll (BMC + inductiveness):"
"$RIC3" cill check
