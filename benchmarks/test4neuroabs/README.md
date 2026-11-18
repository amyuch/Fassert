# test4neuroabs

NeuroAbs-format corpus. Each case is a self-contained directory holding the
RTL/harness sources, a per-case `description.txt`, and a Yosys script that emits
the flat model in both BTOR2 and AIGER form.

```
nerv/<case>/          25 cases   (instruction / CSR / PC / bus properties)
serv/<case>/           4 cases   (causal, pc_bwd, pc_fwd, reg)
picorv32/<insn_*>/    70 cases   (riscv-formal instruction tests)
piccolo/<CASE>/       15 cases   (outer rIC3 package, legacy layout)
flute/<CASE>/         17 cases   (outer rIC3 package, legacy layout)
riscv_formal/                   shared riscv-formal library (legacy)
_legacy/{nerv,serv,picorv32}/   the old single-directory prototypes
fullcheck/<family>/<case>/      99-case full-property variant (generated)
```

## Why the old `nerv/`, `serv/`, `picorv32/` were single directories

Those three directories were early prototypes, not case corpora:

* all five `.ys` scripts in each of them hard-coded `insn_add_ch0.sv` plus
  `iter/0_bx.v` / `iter_btor/1.v`, i.e. NeuroAbs abstraction iterations that are
  not in this tree, so none of them ran;
* `nerv/` and `serv/` shipped byte-identical copies of the picorv32
  `problem.aig` / `problem_new.aig` / `input_line.json` (serv even kept
  `picorv32_input*.v` and a `constant_prop.ys` that reads them), so they did not
  describe nerv/serv at all.

They are preserved verbatim under `_legacy/` for reference.

## Per-case layout

```
<family>/<case>/
  <sources>          exact files listed in ../../<family>/<case>/ric3.toml
                     (include files too, relative paths preserved)
  description.txt    benchmark + property + decode guard (picorv32)
  gen_btor.ys        Yosys -> problem.btor2
  gen_aiger.ys       Yosys -> problem.aig
  run.sh             runs both, prints bad/constraint counts
  .gitignore         problem.btor2, problem.aig, map.txt
  preprocess.sh      only for cases needing the verilator pre-pass (below)
```

`problem.btor2` and `problem.aig` are checked in as the canonical artifacts;
they are reproducible with `./run.sh`.

## Full-property variant

`make_fullcheck_cases.py` materializes `fullcheck/<family>/<case>/` with the
same RTL, harness and entry points but full-property checkers:

* `picorv32/*` uses `riscv-formal/rvfi_insn_check_origin.sv` (20 asserts
  instead of 2, or 1 for the memory-only checker);
* `nerv/reg` and `serv/reg` use the upstream `rvfi_reg_check.sv`;
* `nerv/pc_bwd` and `serv/pc_bwd` use the upstream `rvfi_pc_bwd_check.sv`;
* the other 25 nerv/serv cases are copied unchanged.

It regenerates the reset-initialised `problem.btor2` for all 99 cases and writes
`fullcheck/manifest.csv`. `fullcheck/` is BTOR2-only by default; pass `--aiger`
or run `./run.sh` in a generated case for the legacy zero-initialised AIGER.
See `fullcheck/README.md` for the checker table and expected counts.

## Model initial state

`gen_btor.ys` starts the model from the post-reset state:

```sh
dffunmap
async2sync
sim -clock clock -reset reset -rstlen 1 -n 1 -w testbench
write_btor problem.btor2
```

`ric3.toml` declares `reset = ...`; the `sim ... -w` writeback makes the state
after one reset cycle the new initial state. Without it, only the checker's own
shadow registers have `init` lines, and BMC can start from an arbitrary,
unreachable state. The old nerv/serv/picorv32 models had 2/8/0 `init` lines and
spurious counterexamples at depth 1/9/1; the regenerated models have 55-59
(nerv), 19-20 (serv) and 75-76 (picorv32) `init` lines, with unchanged
`bad`/`constraint` counts.

`gen_aiger.ys` intentionally keeps `write_aiger -zinit` without the sim
writeback. Adding the sim before `-zinit` changes the AIGER encoding
substantially (it expands the input count), so `problem.aig` remains the legacy
zero-initialised artifact. Use `problem.btor2` for reset-initialised checks.

## Property encoding

* Every `assert` is emitted as its own `bad`, and every `assume` as its own
  `constraint` (no `write_btor -s`). BTOR2 and AIGER therefore agree exactly on
  the property set; the bad/constraint counts are equal for all 99 cases.
* `gen_aiger.ys` runs `chformal -lower` so that `$check` cells (from clocked
  assertions) become `$assert`/`$assume` before `abc`.

## The 13 nerv CSR cases

`csrc_*` and `csrw_*` checkers use a `` `quoted ``-style macro nesting
(`` `csrget(`NAME, rmask) ``) that the yosys built-in Verilog frontend cannot
expand. Those cases are preprocessed with `verilator -E -DYOSYS` into
`design_pp.v`, which Yosys then reads. The rIC3 build covers the same cases with
its `yosys_slang` frontend. `run.sh` invokes `preprocess.sh` automatically.

## What is not reproduced

The NeuroAbs tool itself produced the following, and they have no counterpart
here (the legacy copies had them only for the picorv32 ADD prototype):

* `iter/0_bx.v`, `iter_btor/1.v` — abstraction iterations;
* `design.ys`, `design_abc.ys` — per-iteration design/AIG export;
* `constant_prop.ys` — input instrumentation + constant propagation;
* `input_line.json` — input-to-source-line map.

`gen_btor.ys` / `gen_aiger.ys` are the baseline (`iter/0`) model that the tool
would start from.

## NeuroAbs tool entry points (`src/main.py`)

`baselines/neuroabs/src/main.py` takes one `.v` file and requires a matching
`<stem>_constant.v` next to it (the assert in `running_constant_propagation`),
then runs its constant-propagation Yosys templates on those two files alone.
Passing a `.sv` file does not trip that assert: `replace('.v', '_constant.v')`
is a no-op for `.sv`, so the tool silently compares the file with itself and
extracts no candidates. Every case therefore needs an explicit `.v` entry
point; pointing the tool at `wrapper.sv` or at a source file is not enough.

`make_neuroabs_entries.py` generates those entry points for `nerv/`, `serv/`
and `picorv32/`:

```
<family>/<case>/
  wrapper.v           flattened, DUT-only `rvfi_wrapper` (no testbench)
  wrapper_constant.v  same netlist, instruction/CSR environment tied
```

* `wrapper.v` is produced with `proc; flatten; delete t:$anyseq;
  setundef -undriven -expose`, so the `rvformal_rand_reg` environment signals
  (instruction/data bus, interrupts, faults) become top-level inputs. They are
  renamed to `i_<semantic>` using the `assign <sem> = <auto>;` aliases emitted
  by `setundef`; internal nets keep their `\uut.*` names.
* `wrapper_constant.v` keeps the same port order for the non-tied inputs but
  removes the tied ports and drives the corresponding internal wire with a
  constant. For serv/nerv it is a text edit of `wrapper.v`, so every name is
  identical. For picorv32 it is re-flattened from the patched source, which is
  why the design is kept otherwise untouched; `main.py` then treats signals
  that are constant in the constant netlist but not in the normal one as
  candidates (`extract.txt` is a plain set difference of the two reports).

Constant-scenario design:

* **picorv32** — the free `mem_ready`/`mem_rdata` bus stays free; instead the
  three instruction-carrying signals are patched at the source level
  (`mem_rdata_latched_noshuffle`, `mem_rdata_q`, `next_insn_opcode`), mirroring
  the legacy `picorv32_input_constant.v`. The literal is built from the case's
  `spec_valid` guard in `insn_<case>.v`: constrained fields are concrete,
  register/immediate fields stay `x`, so the scenario does not over-constrain
  operands. Compressed instructions are duplicated into both 16-bit halves so
  the core keeps executing the target. The mul/div/rem family (including
  `mulh*`, `divu`, `remu`) is generated without `RISCV_FORMAL_ALTOPS` so the
  real multiplier/divider is exercised; the other cases keep the inert define.
* **serv** — `ibus_rdt=32'h33` (ADD), `ibus_ack=1`, `dbus_ack=1`,
  `dbus_rdt=0`.
* **nerv** — `stall=0`, `dmem_rdata=0`, `irq=0`, both faults 0, and
  `imem_data` set to the case's encoding (ADD, a CSR access, `lw`, or `0` for
  `ill`). The `bus_*` cases also tie `next_dmem_rdata=0` / `next_dmem_fault=0`;
  `*_fault` cases tie the relevant fault input to 1.

Current coverage:

| family | cases | `<stem>.v` + `<stem>_constant.v` | note |
|---|---:|---:|---|
| piccolo | 15 | 15 | legacy flattened `wrapper.v` packages |
| flute | 17 | 15 | `SB` and `SH` lack `wrapper_constant.v` (upstream lacks them too) |
| nerv | 25 | 25 | generated by `make_neuroabs_entries.py` |
| serv | 4 | 4 | generated by `make_neuroabs_entries.py` |
| picorv32 | 70 | 70 | generated by `make_neuroabs_entries.py` |

`piccolo/` and `flute/` are kept in the upstream legacy layout, so their
`wrapper_constant.v` files are byte-for-byte the upstream ones rather than
outputs of `make_neuroabs_entries.py`.

### Invocations

Use the flattened wrapper as the entry point, not the behavioural harness:

```sh
cd baselines/neuroabs

# serv / nerv (free inputs tied in wrapper_constant.v)
python3 src/main.py --constant-only -t rvfi_wrapper -f uut \
  --constant-template flute -d ../../benchmarks/test4neuroabs/nerv/reg/description.txt \
  ../../benchmarks/test4neuroabs/nerv/reg/wrapper.v

# picorv32 (source-patched instruction; -l also extracts register candidates)
python3 src/main.py --constant-only -l -t rvfi_wrapper -f uut \
  --constant-template picorv32 -d ../../benchmarks/test4neuroabs/picorv32/insn_add/description.txt \
  ../../benchmarks/test4neuroabs/picorv32/insn_add/wrapper.v
```

`-f uut` is required: the flattened netlist keeps the `\uut.*` prefix, and
without it the register/constant extraction sees no case-relevant signals.
Drop `--constant-only` for the full abstraction run; keep `-l` and the
matching `--constant-template` so the constant pass uses the same encoding.
`--constant-only` stops before `lineno_extractor`; the PyVerilog dataflow
parser is exercised by the full run (`wrapper_noassert.v` is the file it
parses).

## Regenerating

```sh
cd benchmarks/test4neuroabs
python3 generate_neuroabs_cases.py          # rewrite the 70 rIC3-backed case dirs
python3 generate_neuroabs_cases.py --check  # dry run
python3 make_neuroabs_entries.py            # rewrite wrapper.v + wrapper_constant.v
python3 make_fullcheck_cases.py --jobs 8    # rewrite fullcheck/ (BTOR2 only)
```

The first script reads `../../<family>/<case>/ric3.toml`, so it follows the
active rIC3 corpus (file lists, top module, include files). It also re-detects
which cases need the verilator pre-pass.

The current tree has 99 cases: 25 nerv, 4 serv and 70 picorv32. The picorv32
set is 38 active cases plus the 32 compressed `insn_c_*` cases; the three
`_altops` variants are not materialized here. The compressed cases exist only
in this tree (`../picorv32` has no matching `ric3.toml`), so the generator
leaves them alone. When the `gen_btor.ys` template changes, patch those 32 files
too (or rebuild them from their existing scripts).

`make_neuroabs_entries.py` must be re-run after `generate_neuroabs_cases.py`:
the latter restores `defines.sv` from the rIC3 corpus, which reintroduces
`RISCV_FORMAL_ALTOPS` on the non-M picorv32 cases and re-adds the `_altops`
variants. The entry-point generator intentionally leaves ALTOPS off for
mul/div/rem so those cases exercise the real multiplier/divider. It also
formats both wrappers from the sources in each case dir, so a stale
`wrapper.v`/`wrapper_constant.v` pair would no longer match the regenerated
`defines.sv`.

To regenerate a subset, pass families or `family/case`:

```sh
python3 make_neuroabs_entries.py nerv serv
python3 make_neuroabs_entries.py picorv32/insn_add nerv/bus_dmem_fault
python3 make_neuroabs_entries.py --list
```

## Verifying

```sh
for d in nerv/*/ serv/*/ picorv32/*/; do (cd "$d" && ./run.sh) || echo "FAIL $d"; done
```

All 99 cases build with Yosys 0.60 + Verilator; `bad`/`constraint` counts match
between the BTOR2 and AIGER outputs.

`problem.btor2` starts from the post-reset state (see "Model initial state").
The shallow BMC counterexamples from the old unreachable initial state are gone:

```sh
(cd nerv/reg        && ric3 check problem.btor2 bmc --end 8)   # no cex
(cd serv/reg        && ric3 check problem.btor2 bmc --end 25)  # no cex
(cd picorv32/insn_add && ric3 check problem.btor2 bmc --end 19) # no cex
```

rIC3 1.5.2's `check bmc` prints `not yet implemented` and panics after an
inconclusive run; read the `BMC found no counterexample up to depth N` lines.
The same panic happens on the old model at `--end 0`, so it is not specific to
the regenerated model.

The generated entry points additionally re-read cleanly:

```sh
for f in */wrapper.v */wrapper_constant.v; do
  yosys -q -p "read_verilog -sv $f; hierarchy -check -top rvfi_wrapper; proc; check" \
    || echo "FAIL $f"
done
```

And `main.py --constant-only` completes on all of them: 3901 candidates for each
serv case, 2228-4379 for nerv, and 4361-4386 for picorv32 with `-l`. The
constant scenario retires the intended instruction (`rvfi_insn` matches the
per-case encoding); the `ill`/`csr_ill_*`/`bus_imem_fault` cases exercise the
trap path, and `bus_dmem_fault` exercises the faulting load.
