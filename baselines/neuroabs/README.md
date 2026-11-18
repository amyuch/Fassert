# NeuroAbs

This repository contains Python scripts for NeuroAbs RTL abstraction and
benchmark data.

## Citation

If you use NeuroAbs in your research, please cite our
[ICCAD 2026 paper](https://iccad.com/2026):

```bibtex
@inproceedings{yan2026neuroabs,
  title={NeuroAbs: A Neuro-Symbolic RTL Abstraction Framework for Property Checking Acceleration},
  author={Yan, Zhiyuan and Zhou, Xiaofeng and Zheng, Ziyue and Yang, Ziyi and Che, Wenbin and Zhang, Wei and Lyu, Yangdi and Zhang, Hongce},
  booktitle={Proceedings of the 2026 IEEE/ACM International Conference on Computer-Aided Design (ICCAD)},
  year={2026},
  url={https://iccad.com/2026}
}
```

## Layout

- `src/`: Python scripts and command-line entry points.
- `Flute_verification_done/`: Flute benchmarks.
- `Piccolo_verification_done/`: Piccolo benchmarks.
- `i2c/`: I2C benchmarks.
- `riscv_formal/`: Picorv32/riscv-formal benchmarks.
- `*.ys`: Yosys scripts used by the benchmark flows.

The benchmark directories keep the inputs and scripts needed to reproduce the
flows. Keep `description.txt` files because they describe the target property.
Generated artifacts such as extra `.txt` files, `input_line.json`,
`statement.json`, `.smt2` files, and `iter*` directories are intentionally not
tracked.

## Requirements

Use Python 3 and make sure the following tools and packages are available:

- Yosys
- Pono, for BTOR2/word-level CEGAR refinement
- rIC3 with kissat support, for the final BMC checks. A standalone `kissat`
  executable is not required when using rIC3's `--bmc-kissat` mode.
- z3, used by the Python abstraction scripts
- LLM API credentials/configuration

ABC and `.sby`/SymbiYosys are not required for the final experiments described
below. Some older logs and scripts in the repository use `gen_aiger.ys` and
ABC/BMC3, but the reproducible path in this README uses only BTOR2 models and
`rIC3 --bmc-kissat`.

This project uses the patched PyVerilog fork in `Pyverilog_NeuroAbs`.
It is part of this repository as a git submodule; use this fork rather than
upstream PyVerilog. After cloning the repository, initialize the submodule
before running the Python scripts:

```bash
git submodule update --init --recursive
```

The Python scripts default to local tool paths used during development. For a
portable setup, override them with environment variables:

```bash
export YOSYS_BIN=/path/to/yosys
export PONO_BIN=/path/to/ponocca/build/pono
export RIC3_BIN=/path/to/rIC3
export RIC3_TMP_DIR=$PWD/.tmp/rIC3
export PYTHONPATH=$PWD/Pyverilog_NeuroAbs:$PWD/src:$PYTHONPATH
mkdir -p "$RIC3_TMP_DIR"
```

Make sure `RIC3_BIN` points to the executable itself. If it is empty, shell
expansion turns the checker command into `-v 3 ...`, which fails with
`-v: not found`.

Yosys can be installed from a standard Yosys build or from oss-cad-suite.

Build the expected ponocca version:

```bash
git clone --branch tacas-2024 --single-branch git@github.com:ZhiyuanYan/ponocca.git
cd ponocca
./contrib/setup-smt-switch.sh
./contrib/setup-btor2tools.sh
./configure.sh
cd build
make -j64
export PONO_BIN=$PWD/pono
```

If you already have a local CoSA2/Pono dependency tree, you can reuse its
`deps/` directory before running `./configure.sh`.

`src/main.py` calls an LLM through one of the API wrappers, such as
`gpt_api.py`, `gemini_api.py`, `deepseek_api.py`, or `llama_api.py`. Configure
the API key and endpoint before running abstraction:

```bash
export API_KEY=<your-api-key>
export API_URL=<your-chat-completions-url>
```

## Common Commands

Generate an RTL abstraction wrapper:

```bash
python3 src/main.py -t <top_module> -d <description.txt> -f <prefix> <rtl_file.v>
```

The RTL file passed to `src/main.py` should be the original wrapper, such as
`wrapper.v`, `tst_bench_top.v`, or `picorv32_input.v`. The script compares it
against the corresponding constant-constrained file, such as
`wrapper_constant.v`, `tst_bench_top_constant.v`, or
`picorv32_input_constant.v`. It also creates a `*_noassert.v` copy for the
PyVerilog line-number analysis because PyVerilog does not parse the assertion
blocks used in these wrappers. Generated `problem_*.v` files are Yosys
intermediate outputs, not flow inputs.

`src/main.py` chooses a constant-propagation Yosys template automatically from
the benchmark path/top module. Use `--constant-template {flute,piccolo,i2c,picorv32}`
to override auto-detection. The Picorv32/register-aware flow is also selected
when `--use_register` is used with `--constant-template picorv32`.

Choose the LLM wrapper with `--api-backend`; the default is `gpt`.

To run the abstraction stage without any API quota, use the offline `authored`
backend added in `src/authored_api.py` (the same file as
`patches/official-flow/authored_api.py`), in two passes:

```bash
# 1. record every prompt; answers are the identity abstraction
NEUROABS_LLM_MODE=collect NEUROABS_LLM_PROMPTS=$PWD/llm_prompts.jsonl \
  python3 -u src/main.py --api-backend authored ... 

# 2. replay hand-authored answers (missing keys fall back to identity)
NEUROABS_LLM_MODE=replay NEUROABS_LLM_PROMPTS=$PWD/llm_prompts.jsonl \
  NEUROABS_LLM_ANSWERS=$PWD/llm_answers.json \
  python3 -u src/main.py --api-backend authored ...
```

`patches/official-flow/author_answers.py` is an example policy that turns a
prompt log into `llm_answers.json`. A statement the Eq. 2 gate cannot parse is
skipped (the same behaviour as the HTTP backends) instead of aborting the run.

Run a final kissat BMC check:

```bash
# rIC3 >= 1.5.2
python3 src/run_checker.py "$RIC3_BIN check <file.btor2> bmc --kissat --time-limit 120"

# older builds that use the flag-style CLI
python3 src/run_checker.py "$RIC3_BIN -v 3 --bmc-kissat --engine bmc <file.btor2>"
```

`src/run_checker.py` can wrap the same command when you want long-running depth
logging. Set `RIC3_TMP_DIR` to a directory you own before running rIC3; otherwise
a stale shared `/tmp/rIC3` directory can make rIC3 fail during ABC/kissat
preprocessing. If ABC preprocessing itself fails after the temporary directory
is writable, rerun with `--no-abc`; the BMC engine is still selected by
`--engine bmc --bmc-kissat`.

Run CEGAR:

```bash
python3 src/cegar.py -f <iter_output_dir> -y <yosys_script.ys> <wrapper_abstract_llm_new.v>
```

Pass the abstracted wrapper RTL to CEGAR. The script writes refined wrappers
under the directory given by `-f` and converts those wrappers with a temporary
Yosys script, leaving the original Yosys script unchanged. Use `gen_btor.ys` for
Flute/Piccolo/I2C cases and `gen_btor.ys` for Picorv32/riscv-formal cases; both
routes produce BTOR2 models, and `cegar.py` uses Pono with dynamic COI to decide
which abstracted inputs to refine.

## Examples

### Full Pipeline Examples

The correct experiment order is:

1. Run `src/main.py` on the original RTL input. The original input has a matching
   `*_constant.v`, and `main.py` writes or refreshes the matching
   `*_noassert.v`, `wrapper_abstract_llm_new.v`, `statement.json`, and
   `input_line.json`.
2. Run `src/cegar.py` on `wrapper_abstract_llm_new.v` using the case's BTOR2
   Yosys script.
3. Run rIC3 kissat BMC on the final BTOR2 produced by CEGAR.

Set tool paths once from the repository root:

```bash
export YOSYS_BIN=/path/to/yosys
export PONO_BIN=/path/to/ponocca_tacas2024_worktree/build/pono
export RIC3_BIN=/path/to/rIC3
export RIC3_TMP_DIR=$PWD/.tmp/rIC3
export PYTHONPATH=$PWD/Pyverilog_NeuroAbs:$PWD/src:$PYTHONPATH
mkdir -p "$RIC3_TMP_DIR"
```

Flute example:

```bash
python3 -u src/main.py -t wrapper --constant-template flute \
  -f RTL -d Flute_verification_done/BGE/description.txt \
  Flute_verification_done/BGE/wrapper.v

python3 src/cegar.py --timeout 30 \
  -f readme_iter_btor \
  -y Flute_verification_done/BGE/gen_btor.ys \
  Flute_verification_done/BGE/wrapper_abstract_llm_new.v

python3 src/run_checker.py "$RIC3_BIN -v 3 --bmc-kissat --engine bmc \
  Flute_verification_done/BGE/readme_iter_btor/1.btor2"
```

Piccolo example:

```bash
python3 -u src/main.py -t wrapper --constant-template piccolo \
   -f RTL \
  -d Piccolo_verification_done/ANDI/description.txt \
  Piccolo_verification_done/ANDI/wrapper.v

python3 src/cegar.py --timeout 30 \
  -f readme_iter_btor \
  -y Piccolo_verification_done/ANDI/gen_btor.ys \
  Piccolo_verification_done/ANDI/wrapper_abstract_llm_new.v

python3 src/run_checker.py "$RIC3_BIN -v 3 --bmc-kissat --engine bmc \
  Piccolo_verification_done/ANDI/readme_iter_btor/3.btor2"
```

I2C example:

```bash
python3 -u src/main.py -t tst_bench_top --constant-template i2c \
   -f RTL \
  -d i2c/i2c_assert1/description.txt \
  i2c/i2c_assert1/tst_bench_top.v

python3 src/cegar.py --timeout 60 \
  -f readme_iter_btor \
  -y i2c/i2c_assert1/gen_btor.ys \
  i2c/i2c_assert1/wrapper_abstract_llm_new.v

python3 src/run_checker.py "$RIC3_BIN -v 3 \
  i2c/i2c_assert1/readme_iter_btor/0.btor2"
```

Picorv32/riscv-formal example:

```bash
python3 -u src/main.py -t picorv32 --constant-template picorv32 \
  --use_register  -f RTL \
  -d riscv_formal/riscv_formal_add/description.txt \
  riscv_formal/riscv_formal_add/picorv32_input.v

python3 src/cegar.py --timeout 30 \
  -f readme_iter_btor \
  -y riscv_formal/riscv_formal_add/design.ys \
  riscv_formal/riscv_formal_add/wrapper_abstract_llm_new.v

python3 src/run_checker.py "$RIC3_BIN -v 3 \
  riscv_formal/riscv_formal_add/readme_iter_btor/1.btor2"
```

If you want to avoid spending LLM API quota while checking the CEGAR and BMC
steps, use the already tracked `wrapper_abstract_llm_new.v`, `statement.json`,
and `input_line.json` in each case directory and start from the `cegar.py`
command. The `main.py` command above is still the first step for regenerating
those files from the original RTL.

## Compatibility Notes (Yosys 0.60, rIC3 1.5.2)

These changes make the flow work with current tool versions; they are already
applied in `src/`. The equivalent historical patches under
`patches/official-flow/` are merged as well, so do not re-apply them.

- **Constant-propagation logs.** Yosys >= 0.5x no longer prints bare
  `\RTL.<wire>` lines after `opt_expr`/`opt_clean`; it emits debug messages of
  the form `Replacing $eq cell ... \RTL.foo ...`. `src/main.py` therefore runs
  Yosys with `-g`, and `src/extract_signal.py` keeps the legacy parser but falls
  back to a regex over the debug log. Without both pieces the candidate list is
  empty and the run silently abstracts nothing. Be aware that `-g` produces
  large `normal_extract.txt`/`constant_extract.txt` logs (hundreds of MB on
  Flute-scale designs).
- **Mixed-width assignments.** `src/z3_gen.py` now resizes operands following
  Verilog's implicit extension instead of asserting that both sides are
  literals (fixes e.g. `count_instr <= 0;`).
- **`$print` cells.** The picorv32 constant-propagation template drops `$print`
  before `write_aiger`, which otherwise fails with
  `Unsupported cell type: $print`.
- **CEGAR + clocked assertions.** On Yosys 0.60 the BTOR2 script passed to
  `cegar.py` must lower `$check` cells before `sim`, e.g. add `async2sync;`
  immediately before `sim -clock ...`. Without it CEGAR stops with
  `ERROR: Unsupported cell type: $check`.
- **Pono.** `cegar.py` needs the Pono-CCA build (tacas24) because it calls
  `--dynamic_coi_up_cex` and reads `coi-check-rev.txt`; stock Pono does not
  provide these.
- **rIC3 CLI.** rIC3 1.5.2 uses `ric3 check <model> bmc --kissat`; the older
  `-v 3 --bmc-kissat --engine bmc` form only works on earlier builds.

## Sample Offline Run

Five representative corpus cases were run end to end **after the
reset-initialisation fix** (28 Oct 2026) with the offline `authored` backend
(a generic `'bx` policy, not a real model), Yosys 0.60, Pono-CCA bound 25
(90 s per query unless noted) and rIC3 1.5.2 BMC (`--end 25`).

| case | const. candidates | abstractable | prompts | statements | CEGAR refinements | CEGAR time | verdict | model bad/constraints | baseline BMC | refined BMC |
|---|---:|---:|---:|---:|---:|---:|---|---|---|---|
| `nerv/reg` | 4,379 | 125 | 125 | 125 | 1 | 0.99 s + 90 s timeout | unknown (Pono timeout) | 2 / 1 | no cex ≤11 | no cex ≤4 |
| `serv/reg` | 3,901 | 120 | 116 | 109 | 2 | 6.1 s | unknown (Pono `bmc` returned unknown) | 2 / 5 | no cex ≤25 | no cex ≤25 |
| `picorv32/insn_add` | 4,350 | 12 | 12 | 12 | 1 | 0.59 s + 129 s bound check | unknown (Pono `bmc` returned unknown) | 2 / 1 | no cex ≤25 | no cex ≤25 |
| `piccolo/ANDI` | 136 | 99 | 228 | 221 | 7 | 16.9 s + 90 s timeout | unknown (Pono timeout) | 1 / 1 | no cex ≤19 | no cex ≤21 |
| `flute/BGE` | 347,414 | 210 | 354 | 340 | 0 | 0.00 s + 16 s bound check | unknown (Pono `bmc` returned unknown) | 1 / 1 | no cex ≤14 | no cex ≤25 |

* `no cex ≤N` is an rIC3 BMC result: the tool reached depth N without a
  counterexample and then returned `UNKNOWN` because BMC is not a proof.
  Batches were run with `--end 25 --time-limit 300`; `nerv/reg` (both models)
  and `piccolo/ANDI` (both models) self-stopped at the listed depth. The
  `flute/BGE` baseline was still checking depth 15 when the 420 s outer
  timeout fired, hence depth 14. The `serv/reg`, `picorv32/insn_add` and
  `flute/BGE` abstract models all reached depth 25.
* `nerv/reg`, `serv/reg` and `picorv32/insn_add` are the cases that were SAT
  before the corpus reset-initialisation fix. After the fix no case is SAT:
  the refinements remove the spurious counterexamples. For `serv/reg` and
  `picorv32/insn_add` Pono's `bmc` engine reaches its bound and returns
  `unknown` (bounded no-cex); `nerv/reg` and `piccolo/ANDI` hit the per-query
  timeout, so their verdict remains unknown.
* `CEGAR time` is the value in `cegar_time.txt`, which only sums successful
  counterexample queries. `picorv32/insn_add` was rerun with a 240 s
  per-query timeout: its final query returned engine-level `unknown` after
  129 s. `nerv/reg` and `piccolo/ANDI` still time out with a 240 s budget, so
  their table entries use the default 90 s timeout.
* Pono's `bmc` engine does not report bounded `unsat`; on a safe model it
  returns `unknown` once it has exhausted the bound. `cegar.py` therefore
  distinguishes a process timeout (`backend timeout`) from an engine-level
  `unknown` (`backend returned unknown; no counterexample within bound`).
* `piccolo/ANDI`: the final (8th) Pono query hit the 90 s per-query timeout.
  `cegar_time.txt` only sums successful counterexample queries, so the 16.9 s
  excludes it.
* `flute/BGE`: no refinement is needed — Pono returns `unknown` on the 1.4 MB
  abstract model on the first query, and rIC3 independently finds no cex
  through depth 25 on that model. The "refined" BMC column is therefore the
  abstract model itself. The baseline only reaches depth 14 in 420 s because
  it is larger and harder for BMC than the abstracted model.
* `flute/SB` and `flute/SH` were the only corpus cases missing
  `wrapper_constant.v`. Both were generated by tying the `imem_instr`
  assignment to the S-type instruction literal
  (`{12'bx,5'bx,3'b000,5'bx,7'b0100011}` for `SB`,
  `3'b001` for `SH`), matching the existing Flute constant variants. Both
  entry points completed `main.py --constant-only` (`SB` 210,339 candidates,
  348 s; `SH` 210,342, 336 s). All 131 case directories now have `wrapper.v`,
  `wrapper_constant.v` and `gen_btor.ys`.
* `picorv32/insn_add` has only 12 abstractable signals in the **flattened**
  `wrapper.v` flow because the 4,350 constant-propagation candidates are
  almost all Yosys-internal `cpuregs$wrmux[...]` / `cpuregs$wren[...]` nets
  with no PyVerilog `update_map` entry (memory-expansion artifacts, not
  source-level assignments). The 12 source-level signals come from the
  register-aware AIG comparison enabled by
  `--constant-template picorv32 --use_register`. The unflattened DUT entry
  point described below raises this to 90–103 candidate signals (224
  abstracted statements) and exposes the missing ALU/decode/writeback signals.
* The `flute/BGE` abstract wrapper is byte-identical to the previously
  validated artifact (md5 `a6a80e69...`). The `piccolo/ANDI` wrapper differs
  from the earlier run (md5 `88753801...`) because this run used the generic
  authoring policy, which accepted three more statements (221 vs 218); its
  md5 is now `5c9761...`.

### Unflattened picorv32 DUT flow

The flattened `picorv32/<case>/wrapper.v` entry point has 4,350
constant-propagation candidates, but almost all of them are Yosys-internal
`cpuregs$wrmux[...]` / `cpuregs$wren[...]` nets with no PyVerilog
`update_map` entry. Only 12 source-level statements are abstractable, and
`alu_out`, `decoded_imm`, `reg_op1/2`, `cpuregs_wrdata` and `current_pc` are
missing entirely. This is the same granularity problem the official
`riscv_formal_add` flow avoids by abstracting the **unflattened** core.

`src/make_picorv32_dut_entries.py` generates that second entry point:

```sh
cd baselines/neuroabs
# all 70 picorv32 cases: entry points + shared abstraction + BTOR2 build
PONO_BIN=/path/to/pono python3 src/make_picorv32_dut_entries.py \
  --jobs 6 --abstract --build

# one case, including a CEGAR run
PONO_BIN=/path/to/pono python3 src/make_picorv32_dut_entries.py \
  --abstract --build --cegar --pono-timeout 120 picorv32/insn_add
```

For each case it writes:

* `picorv32_input.v` — `verilator -E -I. picorv32.sv`, with the
  `32'h 0000_0000` lexical spacing fixed and the
  `regindex_bits`/`irqregs_offset`/`regfile_size` localparams replaced by the
  default-configuration literals the dataflow pass can resolve;
* `picorv32_input_constant.v` — the same core with the case's instruction word
  written into `mem_rdata_latched_noshuffle`, `mem_rdata_q` and
  `next_insn_opcode` (the same three sites as the flattened constant variant);
* `dut/wrapper_abstract_llm_new.v` — the abstracted core (224 `'bx`
  statements in the shared generic-policy run), plus `statement.json` and
  `input_line.json`;
* `dut_cegar.ys` — a Yosys script that reads the checker, `insn_<case>.v`,
  the behavioural `wrapper.sv`, the abstracted core and `tb.sv`, then copies
  the `prep ... sim ... write_btor` pipeline from `gen_btor.ys`.

The shared abstraction is bundled at `src/picorv32_dut_shared/` (generated
once from `insn_add` with the generic authored policy). It is valid for the
62 ALTOPS cases: for those, only `defines.sv`'s
`RISCV_FORMAL_INSN_MODEL` changes, and that macro is used by the harness, not
the core. The eight non-ALTOPS mul/div/rem cases (`insn_mul`, `insn_mulh`,
`insn_mulhsu`, `insn_mulhu`, `insn_div`, `insn_divu`, `insn_rem`,
`insn_remu`) preprocess to a *different* core without the ALTOPS fast-mul
branch. They need the non-ALTOPS abstraction generated from `insn_mul/dut`
(224 statements, md5 `41ab66ac6dbe9223b492f6390b347f39` for the raw
preprocessed core); `insn_mul` and `insn_mulh` were rebuilt this way on
1 Nov 2026. `--reuse` can point at a different abstraction directory.

The current `src/make_picorv32_dut_entries.py` still calls
`preprocess_core(cases[0])` once and writes that text to every case. Do not run
it with `--force` across a mixed ALTOPS/non-ALTOPS set until that helper is
changed to group by `defines.sv`; otherwise the non-ALTOPS cases silently get
the ALTOPS core again.

The extra `inputN` ports are left unconnected by `wrapper.sv`; Yosys reports
them undriven and `setundef -anyseq` turns them into free inputs, which is
exactly the abstraction point CEGAR refines. `src/cegar.py` substitutes the
refined core for the `read_verilog -sv wrapper.v` placeholder in
`dut_cegar.ys`, so no per-iteration script regeneration is needed.

**Results (all 70 picorv32 cases, 29 Oct 2026).** Every case generates
`picorv32_input.v` + `picorv32_input_constant.v`, completes
`main.py --constant-only` with rc 0, and builds
`dut/wrapper_abstract_llm_new.btor2`:

| scope | constant candidates | abstracted statements | constant-only | BTOR2 build |
|---|---:|---:|---:|---:|
| all 70 picorv32 cases | 90–103 (median 96) | 224 | 70/70 | 70/70 |

The number of abstractable source-level signals is 90–103 per case (224
abstracted statements), versus 12 signals in the flattened wrapper; the DUT
set includes the core decode/ALU/writeback signals listed earlier.
Representative CEGAR runs with the generic `'bx` policy and Pono bound 25
(120 s per query):

| case | refinements | CEGAR time | Pono verdict | wall clock | rIC3 BMC on final model |
|---|---:|---:|---|---:|---|
| `insn_add` | 10 | 2.34 s | unknown (bounded no-cex) | 122.8 s | no cex ≤25 |
| `insn_addi` | 2 | 0.24 s | unknown (120 s backend timeout) | 122.5 s | no cex ≤23 |
| `insn_sub` | 10 | 2.10 s | unknown (120 s backend timeout) | 132.5 s | no cex ≤23 |
| `insn_and` | 10 | 2.24 s | unknown (bounded no-cex) | 56.7 s | no cex ≤25 |
| `insn_c_addi4spn` | 2 | 0.25 s | unknown (bounded no-cex) | 72.7 s | no cex ≤25 |

The DUT BTOR2 models have 2 bad properties and 1 constraint. On `insn_add`,
rIC3 BMC finds a counterexample in the **initial** abstraction at depth 7
(SAT), while the final `dut/iter/9.btor2` has no counterexample up to depth 25;
the model shrinks from 259 to 69 BTOR2 inputs as CEGAR restores the statements
feeding the cone of influence. No case is SAT after refinement. `CEGAR time`
is the `cegar_time.txt` sum and excludes the final Pono query, which either
reaches the bound and returns
engine-level `unknown` or exceeds the 120 s per-query budget. The
bounded-no-cex and backend-timeout verdicts are both "unknown"; they are
distinguished in `cegar.py` as before. The BMC column is rIC3 1.5.2
(`--kissat --end 25 --time-limit 300`) on the last refined
`dut/iter/*.btor2`; `insn_addi`/`insn_sub` hit the 300 s time limit at depth 23,
the other three reached bound 25. All runs are UNKNOWN, no counterexample.

A separate 3-hour stress test on `insn_add` did not change the picture. The
CEGAR was rerun with 10,800 s for the wall clock and for each Pono query; it
still stopped after 123 s with the same `unknown (bounded no-cex)` verdict,
because Pono's BMC returns engine-level `unknown` at about 120 s regardless of
the larger budget. rIC3 IC3 was then run for 10,500 s on the final
`dut/iter/9.btor2` and returned `UNKNOWN` with no counterexample (after
preprocessing: 2,134 latches, 988 inputs, 1 constraint).

**Why the DUT abstraction is broader than the official 21 sites.** The
official `riscv_formal_add` snapshot uses 21 hand-placed `add_inputN` ports
(ALU, decode, writeback and debug signals). The generic authored policy used
here replaces every candidate assignment with `'bx`, producing 224 statements
from the 90–103 candidate signals. That is sound (`'bx` is the Verilog top
value) but gives CEGAR more freedom than the official subset, which is why
several runs end at the bound/timeout instead of a proof. A future tightening
can restrict the authored answers to the official 21 signal names; the DUT
entry-point generation and CEGAR plumbing are independent of that policy.

The Verilator-preprocessed core keeps inline attributes and `` `line ``
directives that PyVerilog rejects. `src/main.py` therefore sanitizes only the
`*_noassert.v` copy used for the dataflow map (attributes/`` `line `` blanked,
line numbers preserved) while Yosys still sees the original attributes. The
same change also handles a top module with a parameter list
(`module picorv32 #( ... ) ( ... );`) by inserting the fresh inputs into the
port list, not into `#(...)`. `src/check.py` short-circuits an exact `'bx`
successor (the implication is trivially true), so source-level statements
with bit selects, concatenations and function calls do not need the small Z3
parser.

**Comparison with the previous `riscv_formal_add` test.** The instantiated DUT
is the same `picorv32` core with the same parameters (`.COMPRESSED_ISA(1)`,
`.ENABLE_FAST_MUL(1)`, `.ENABLE_DIV(1)`, `.BARREL_SHIFTER(1)`), and
`insn_add.v` has the same ADD semantics (`rd = rs1 + rs2`, `pc + 4`). The
differences are in the source revision/harness and, more importantly, in the
properties:

| item | previous `riscv_formal_add` | new `picorv32/insn_add` |
|---|---|---|
| core source | `picorv32.v` (3,059 lines), plus the official 21-site `picorv32_input.v`; has a stray `input1` and an `ifdef FORMAL` block with internal restrictions/assertions | `picorv32.sv` (2,494 lines), pristine, `default_nettype none`; the `FORMAL` block is commented out |
| abstraction | official 21 `add_inputN` sites; the old `input_line.json` has 147 entries but is stale (it does not line up with the present `wrapper_new.v`) | 12 statements in the flat `wrapper.v`; 224 statements in `dut/wrapper_abstract_llm_new.v` |
| checker | full riscv-formal checker: `assume(spec_valid)`; checks rs/rd addresses, rd/pc data, trap, memory address/masks/data, zero-register reads, CSR `misa`, PMA; checks combinationally (`always @*`) | reduced checker: no `assume(spec_valid)`; asserts only `rd_wdata` and `pc_wdata` when `!spec_trap` and the PC/memory access is valid; samples at `posedge clock` |
| check timing | `RISCV_FORMAL_RESET_CYCLES 1`, `RISCV_FORMAL_CHECK_CYCLE 20`; `rvfi_testbench.sv` has an internal cycle counter and checks at cycle 20 | `RISCV_FORMAL_UNBOUNDED`; top-level `check` input; `gen_btor.ys` starts from the post-reset state; `rvfi_order` loopback assumption |
| defines | `RISCV_FORMAL_COMPRESSED`, `PICORV32_CSR_RESTRICT` | neither macro |

The old `assume(spec_valid)` forces the checked cycle to be the target ADD
instruction, while the new checker only guards its two assertions with
`spec_valid`, so non-ADD cycles are vacuous and the instruction stream is not
constrained. The old `PICORV32_CSR_RESTRICT` and the core's internal `FORMAL`
restrictions also remove behaviours that the new model leaves free. The two
result sets are therefore not directly comparable: the new property checks
less, but the new DUT abstraction (224 statements versus 21) and the
unbounded/free-check harness give the solver more freedom. The original
`design.ys`/`gen_aiger.ys` still cannot be rerun unchanged because
`iter/0_bx.v` and `iter_btor/1.v` are missing, but the official 21-site
baseline can be rebuilt directly from `picorv32_input.v`; the next subsection
does that and compares the two flows under controlled checker/core
substitutions.

#### Official 21-site ADD rebuild and controlled comparison

The old snapshot's `picorv32_input.v` is the complete 21-site core. Reading
`insn_add_ch0.sv` + `wrapper.sv` + `picorv32_input.v` through the old
`design.ys` pipeline gives a BTOR2 model with 81 inputs, 225 states,
**33 bad / 9 constraints**; reading the core with `-formal` instead gives 81
inputs, 232 states, **56 bad / 11 constraints**. These counts exactly match
the headers of the old AIGs: `problem_new.aig` has 33 bad / 9 constraints
(3,877 input bits, 2,577 latches) and `problem.aig` has 56 bad / 11
constraints (3,982 input bits, 2,651 latches). So the two old AIGs are the
21-site baseline without/with the core's internal `FORMAL` block; the
147-entry `input_line.json` is a stale experiment, not the source of these
AIGs.

I also built two hybrids to separate the core from the checker:

* old 21-site `picorv32_input.v` + new reduced checker/harness: 82 inputs,
  224 states, **2 bad / 1 constraint**;
* new concrete core + old full checker/harness: 68 inputs, 254 states,
  **33 bad / 9 constraints**.

The table uses rIC3 1.5.2. `BMC <=25` is
`bmc --end 25 --time-limit 300 --kissat`; except for the initial-abstraction
row (which has a depth-7 counterexample), every entry reached bound 25 with
`UNKNOWN`, i.e. no counterexample. `IC3 600 s` means the engine hit the
600 s limit and returned `UNKNOWN`; no proof and no counterexample. Old
property 9 is `spec_rd_wdata` and 10 is `spec_pc_wdata`; new property 0 is
`o_pc_wdata_match` and 1 is `o_rd_wdata_match`.

| model | core / checker / abstraction | bad / constraints | BMC <=25 | IC3 600 s |
|---|---|---:|---|---|
| `problem_new.aig` (direct) | old / old full / 21-site, no core `FORMAL` | 33 / 9 | no cex | prop 9 (rd) UNKNOWN |
| `problem.aig` (direct) | old + core `FORMAL` / old full / 21-site | 56 / 11 | no cex | prop 9 (rd) UNKNOWN |
| official 21-site BTOR2, no `FORMAL` | old / old full / 21-site | 33 / 9 | no cex | props 9 (rd), 10 (pc) UNKNOWN |
| official 21-site BTOR2, `-formal` | old + core `FORMAL` / old full / 21-site | 56 / 11 | no cex | prop 9 (rd) UNKNOWN |
| hybrid: old core + new checker | old / new reduced / 21-site | 2 / 1 | no cex | props 0 (pc), 1 (rd) UNKNOWN |
| hybrid: new core + old checker | new / old full / concrete | 33 / 9 | no cex | props 9 (rd), 10 (pc) UNKNOWN |
| new DUT initial abstraction | new / new reduced / 224 sites | 2 / 1 | cex at depth 7 | not run |
| new DUT final `dut/iter/9.btor2` | new / new reduced / concrete | 2 / 1 | no cex | props 0 (pc), 1 (rd) UNKNOWN; all-property 10,500 s run UNKNOWN |

The 2x2 comparison is consistent: holding the checker fixed, the old and new
cores both give 2 bad / 1 constraint under the reduced checker and 33 bad /
9 constraints under the old full checker. The large drop from 33/56 to 2 is
therefore caused by the checker/harness, not by a change in the ADD design.
The remaining difference is abstraction: the official baseline still has 21
free `add_inputN` sites, while `dut/iter/9.v` has zero remaining
`<= inputN` assignments, so the new final BTOR2 is concrete. Neither flow
proves the result: every selected IC3 query is UNKNOWN and BMC finds no
counterexample through depth 25. The earlier 3-hour run on the concrete new
model is also UNKNOWN after 10,500 s.

One qualification: the initial 224-site abstraction includes fetch-path
signals (`mem_rdata_q <= input211`, `next_insn_opcode <= input135`, and
several `cached_insn_*`/`q_insn_*` sites), even though the ADD description
says fetch signals such as `mem_rdata_q` and `mem_rdata_latched` must not be
abstracted. The old 21-site map also abstracts `mem_rdata_latched` (two
sites), but it leaves `mem_rdata_q`/`next_insn_opcode` concrete. By
`iter/9.v` all `<= inputN` assignments are gone, so the final model is
concrete; the early depth-7 CEGAR counterexample is not evidence against the
intended benchmark property. A tighter authored policy should exclude the
fetch path from the candidate set.

Generated models and logs are under `/tmp/opencode/official_add_run/` and
`/tmp/opencode/hybrid_*`; no benchmark source or test file was modified.

### Building the CEGAR model

`gen_btor.ys` reads the behavioural RTL, so it cannot be reused unchanged
after `wrapper.v` has been abstracted. For the generated
`nerv`/`serv`/`picorv32` entries derive a replacement script with:

```sh
python3 src/make_cegar_script.py ../../benchmarks/test4neuroabs/serv/reg \
  --clock clock --reset reset -o /tmp/serv_reg_cegar.ys
PONO_BIN=/path/to/pono python3 src/cegar.py -f iter -y /tmp/serv_reg_cegar.ys \
  ../../benchmarks/test4neuroabs/serv/reg/wrapper_abstract_llm_new.v
```

For the unflattened picorv32 DUT, `make_cegar_script.py --dut` (or the
`dut_cegar.ys` written by `make_picorv32_dut_entries.py`) emits a script that
keeps `wrapper.sv` and uses a `read_verilog -sv wrapper.v` placeholder for the
abstracted core:

```sh
python3 src/make_cegar_script.py \
  ../../benchmarks/test4neuroabs/picorv32/insn_add --dut \
  -o ../../benchmarks/test4neuroabs/picorv32/insn_add/dut_cegar.ys
PONO_BIN=/path/to/pono python3 src/cegar.py -f iter \
  -y ../../benchmarks/test4neuroabs/picorv32/insn_add/dut_cegar.ys \
  ../../benchmarks/test4neuroabs/picorv32/insn_add/dut/wrapper_abstract_llm_new.v
```

`cegar.py` replaces the placeholder with the refined core in every iteration;
the unconnected abstraction ports become `setundef -anyseq` free inputs.

The generated script keeps the checker and `tb.sv`, substitutes the flat
`wrapper.v` for the behavioural DUT, and copies the `prep ... write_btor`
pipeline from `gen_btor.ys`, including its reset-initialising `sim ... -w`
line. The `--clock`/`--reset` options override that line and are only needed
for an older `gen_btor.ys` that predates the corpus fix. The legacy
`piccolo`/`flute` cases already read `wrapper.v` in their shipped
`gen_btor.ys`; add `async2sync` before `sim` on Yosys >= 0.60 and pass that
script to `cegar.py`.

**Initial state.** The generated `nerv`/`serv`/`picorv32` `gen_btor.ys`
scripts now include the same `sim -clock ... -reset ... -rstlen 1 -n 1 -w`
writeback as the legacy `piccolo`/`flute` scripts, using the `reset` named in
`ric3.toml`. `problem.btor2` therefore starts from the post-reset state: nerv 57 `init`
lines, serv 20, picorv32 75 (previously 2, 8 and 0). BMC no longer finds the
old shallow counterexamples: with rIC3 BMC (300 s) there is no cex through
depth 11 (`nerv/reg`), 25 (`serv/reg`) or 25 (`picorv32/insn_add`); for
reference, the pre-fix models were SAT at depths 1, 9 and 1. Those old
counterexamples were an under-constrained-model artifact: the refined NeuroAbs
models were SAT at exactly the same depth as the baseline, so abstraction
itself did not cause the failure. After the fix, CEGAR no longer reports a
counterexample for these three cases either (see the sample table below).

When deriving a CEGAR script for a case whose `gen_btor.ys` still predates this
fix, pass `--clock clock --reset reset` to `make_cegar_script.py` to insert the
same writeback; the generated script then matches the baseline initial state.

## Runtime Notes

`src/main.py` first parses the RTL, runs constant propagation, extracts
candidate signals, and then calls the configured LLM to generate abstracted
RTL. A full run can take a long time and consumes LLM API quota.

For CEGAR debugging, set `CEGAR_VERBOSE=1` to print every refined signal. The
Pono/BTOR2 backend uses bound 25 in `src/cegar.py`; use
`src/cegar.py --timeout <seconds>` to cap each Pono query.

Pono may return `unknown` on a refined BTOR2 model. In that case the script
stops cleanly and writes the CEGAR timing seen so far. For the final rIC3 BMC
experiment, use the last refined BTOR2 model listed in the table above.

`iter_btor` directories are generated by `src/cegar.py` or related
Yosys/checker flows. They are not tracked in git. Generate them locally before
checking a specific `iter_btor/*.btor2` file.

`src/run_checker.py` prints checker output as it runs. If the checker output
contains `bmc depth:`, the script also writes a `bmc_depth_*.csv` report; this
CSV is a generated artifact and is not tracked.

If `rIC3` reports a permission error under `/tmp/rIC3`, set `RIC3_TMP_DIR` to a
directory owned by the current user and rerun the checker.

## Full Testlist Coverage (1 Nov 2026)

All **106/106** rows were exercised through the `benchmarks/test4neuroabs`
entry points: 101 rows from `benchmarks/testlist.csv` (10 smoke, 30 core,
61 extended) plus 5 rows from `benchmarks/testlist_full.csv`.  Full per-row
data is in [`RESULTS.md`](RESULTS.md) and
[`results_all.csv`](results_all.csv); the latter includes the final model path,
CEGAR wall time, model bad/constraint/remaining counts, and baseline status.

### 5-hour smoke/core/full follow-up (3 Nov 2026)

The 1 Nov tables below use a **300 s** rIC3 limit and are a broad-coverage
screen, not a depth comparison.  For the 45 smoke/core/full cases, a separate
**18,000 s total per case** run has now been completed: CEGAR wall time is
charged first, and the remainder goes to the final-model rIC3 BMC with **no
`--end 25` cap**.  Extended cases are not part of this run.

* **39 `TIMEOUT`, 5 `SAT`, 1 engine-level `UNKNOWN`, 0 proofs.**
* Four SAT results are trusted because a concrete baseline has the same depth:
  `nerv/bus_dmem`@2, `piccolo/LB`@12, and the two new picorv32 SATs
  `insn_div`@43 and `insn_rem`@43.  The new SATs were confirmed with separate
  5-hour concrete baselines: SAT@43 in 3,034.6 s and 3,308.4 s respectively.
* `nerv/csrw_mstatus` SAT@1 remains untrusted (flattened-wrapper entry-flow
  discrepancy).
* `serv/causal` reached depth 453 but returned engine-level `UNKNOWN`; it is
  not a proof.  The other `serv` cases timed out at depths 122–274.
* Average completed depth: overall 77.7 (84.9 excluding SAT cases); flute
  117.6, serv 264.8, piccolo 70.0, picorv32 53.9, fullcheck 48.6.
* Concrete 5-hour baselines were run only for `insn_div`/`insn_rem`; the other
  43 baseline fields are deliberately `not run`, not missing.

Per-case data: [`RESULTS_5H.md`](RESULTS_5H.md) and
[`results_5h_smoke_core_full.csv`](results_5h_smoke_core_full.csv).

### Headline result (300 s screen)

* **No case produced an inductive proof.**  CEGAR never printed
  `property holds`.
* CEGAR outcomes: 45 bounded/no-counterexample, 41 backend-timeout, 19
  `property fail`, and 1 backend error (`flute/BNE_new`,
  Pono exit code 2: `Only defined for a bit-vector sort`).
* Final-model rIC3 BMC: 81 `UNKNOWN`, 19 `SAT`, and 6 timeout (last completed
  depth recorded).
* In this 300 s screen, only **four** SAT results are trusted as concrete
  counterexamples: `nerv/bus_dmem` at depth 2,
  `nerv/csrc_inc_mhpmcounter5` at depth 4, `nerv/unique` at depth 1, and
  `piccolo/LB` at depth 12.  Each matches its concrete `problem.btor2` baseline
  at the same depth.  The 5-hour follow-up additionally confirms
  `picorv32/insn_div`@43 and `insn_rem`@43.
* The other 15 SAT results are either abstract-model counterexamples with a
  concrete baseline that is UNKNOWN through depth 25, or, for
  `piccolo/SB`/`piccolo/SH`, still leave 50/51 abstract assignments.  They
  are marked `trusted_sat=no` in `results_all.csv`.

### Coverage notes

* `piccolo/ADD` maps to `piccolo/ADD_Flatten`; `piccolo/BNE` maps to
  `piccolo/BNE_new`.  Both were run under those names.
* The five fullcheck rows use `fullcheck/picorv32/insn_{addi,beq,c_j,jal,mulh}`
  with the unflattened core abstraction and the full-property checker.  Their
  final BMC depths are 22, 20, 23, 22 and 10 respectively, all `UNKNOWN`.
* picorv32 uses the unflattened `dut`/`dut_cegar.ys` flow.  The earlier
  `insn_mul` SAT@9 was an ALTOPS-core/non-ALTOPS-model mismatch; after
  regenerating the core from its own `picorv32.sv` the final model is
  `UNKNOWN` through depth 11, matching the baseline.  `insn_mulh` was
  corrected the same way.
* The earlier smoke `insn_c_j` SAT@23 and fullcheck `insn_c_j` SAT@23 were
  spurious.  With a 600 s Pono budget and further refinement both end in
  `unknown (no counterexample within bound)`: smoke BMC `UNKNOWN` through 24
  (9 abstracts left), fullcheck BMC `UNKNOWN` through 23 (9 abstracts left).
* `flute/BNE_new` is the one backend failure; its last model is BMC timeout at
  depth 9.  `flute/SB` needed a local PyVerilog fix for a missing width
  `msb`/`lsb` in an unsized integer parameter; after that it produced 274
  statements and a CEGAR result.

### nerv CSR entry-flow caveat

For the `nerv/csrw_*`, `csr_ill_*`, and `csrc_upcnt_*` families, the flattened
`wrapper.v` CEGAR flow reports SAT at depth 1 or 3 while the concrete
`design_pp.v` baseline is UNKNOWN through depth 25.  A direct model built from
the flattened wrapper (without any abstraction) is also SAT at depth 1 for
`csrw_mstatus`; this is therefore an entry-flow/model-construction
discrepancy, not evidence against the RTL property.  Those SATs are reported
as untrusted.  `nerv/bus_dmem` is different: its concrete baseline is SAT at
depth 2 as well, so its counterexample is trusted.

### Reproduction settings

* Yosys 0.60+70, Pono-CCA bound 25, 120 s per CEGAR query (600 s for the two
  `c_j` cases), rIC3 1.5.2 BMC with `--end 25 --time-limit 300 --kissat`.
* `CEGAR s` in the tables is the `cegar_time.txt` sum and excludes the final
  Pono query; wall time is separately recorded in `results_all.csv`.
* A BMC depth printed as `UNKNOWN≤N` means the native BMC completed depth `N`
  and returned engine-level `UNKNOWN`; `TIMEOUT@N` means the 300 s rIC3 limit
  was hit after completing depth `N`.
