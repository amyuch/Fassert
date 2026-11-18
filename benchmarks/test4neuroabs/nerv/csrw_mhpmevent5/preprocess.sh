#!/bin/sh
# The yosys built-in Verilog frontend cannot preprocess the `quoted`-style
# macro nesting used by this checker, so preprocess with Verilator first.
# (The rIC3 build covers the same case with its yosys-slang frontend.)
set -eu
cd "$(dirname "$0")"
VERILATOR="${VERILATOR:-verilator}"
"$VERILATOR" -E -DYOSYS -I. rvfi_csrw_check.sv nerv.sv wrapper.sv tb.sv > design_pp.v
