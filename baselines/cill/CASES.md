# CIll baseline cases


## Active scope

| Family | Cases | Directory | Status |
|---|---:|---|---|
| `picorv32` | 43 | `../../benchmarks/picorv32/` | active |
| `serv` | 4 | `../../benchmarks/serv/` | active |
| `nerv` | 25 | `../../benchmarks/nerv/` | active |
| `flute` | 17 | `../../benchmarks/flute/` | ILA/depth family |
| `piccolo` | 15 | `../../benchmarks/piccolo/` | ILA/depth family |


## picorv32 active set

`../../benchmarks/picorv32/manifest.csv` is authoritative. The active set is 43 cases:
40 selected originals plus 3 ALTOPS variants. The preserved set is the 30
unselected originals under `../../benchmarks/picorv32_full/`.

Print the active list:

```sh
awk -F, 'NR > 1 && $2 == "yes" { print $1 }' ../../benchmarks/picorv32/manifest.csv
```

Count by group:

```sh
awk -F, 'NR > 1 && $2 == "yes" { c[$3]++ } END { for (k in c) print k, c[k] }' \
  ../../benchmarks/picorv32/manifest.csv | sort
```

The active coverage is:

- `alu` — 13: `add`, `addi`, `and`, `andi`, `sll`, `slli`, `slt`, `slti`,
  `sltiu`, `sltu`, `sub`, `xor`, `sra`;
- `branch` — 6: `beq`, `bge`, `bgeu`, `blt`, `bltu`, `bne`;
- `compressed` — 5: `c_add`, `c_j`, `c_lw`, `c_sub`, `c_sw`;
- `divrem` — 6: `div`, `divu`, `rem`, `remu`, plus `div_altops` and
  `rem_altops`;
- `jump` — 2: `jal`, `jalr`;
- `load` — 2: `lb`, `lw`;
- `mul` — 5: `mul`, `mulh`, `mulhsu`, `mulhu`, plus `mul_altops`;
- `store` — 2: `sb`, `sw`;
- `upper` — 2: `auipc`, `lui`.

The three ALTOPS representatives are `insn_mul_altops`, `insn_div_altops`, and
`insn_rem_altops`. All eight base MUL/DIV/REM cases are non-ALTOPS.
`insn_mul_altops` is the only active case with a case-local serial-multiplier
wrapper override.

## serv and nerv

`serv` has four cases:

```text
causal
pc_bwd
pc_fwd
reg
```

`nerv` has 25 cases: instruction, CSR, PC, bus, and register properties. List
them with:

```sh
find ../../benchmarks/nerv -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort
```

## Staging convention

Each case is self-contained and is copied to a temporary sandbox before a run:

```sh
export FAMILY=picorv32
export CASE=insn_add
export SB="/tmp/opencode/cill/$FAMILY/$CASE"

rm -rf "$SB"
mkdir -p "$(dirname "$SB")"
cp -rL "../../benchmarks/$FAMILY/$CASE" "$SB"
rm -rf "$SB/ric3proj"
```

Use `cp -rL`, not a symlink farm, and never reuse `ric3proj/` from a previous
run. The benchmark tree itself is read-only for baseline purposes.

