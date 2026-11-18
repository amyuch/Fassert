#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$root"
mkdir -p models
yosys -Q -T -p 'read_verilog -formal -sv input/rtl/mul.sv; prep -top bridge_mul; async2sync; dffunmap; write_btor models/original.btor'
