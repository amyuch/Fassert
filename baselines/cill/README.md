# CIll baseline

CIll is the CTI-guided, agent-driven helper-assertion baseline. This directory
is the runnable CIll artifact plus the procedure for running the baseline.
There is deliberately **no `run.sh`**: the baseline loop is an agent using the
CIll prompt, `ric3 cill`, and a VCD inspection tool. The agent can be any LLM
or human operator with shell access; no specific CLI or editor is required.

The baseline is not "run CIll once". The LLM proposes helper assertions, CIll
checks them, the CTI is inspected, and the loop continues until every original
property is inductive or the budget is exhausted. This is a **method baseline**;
the bare rIC3/ABC engine floor is a separate control.

## Metric order

The primary metric is:

```text
1. inductiveness of all original properties
2. time to that inductive state, T_ind
3. only for non-inductive runs: bounded BMC depth
```

A counterexample is a separate result, not a depth result. Do not compare a
BMC depth with an inductive proof time as if they were the same measurement.

## Directory contents

```text
baselines/cill/
  README.md                 this procedure
  LINKS.md                  tools, versions, and benchmark locations
  CASES.md                  baseline case scope
  PROMPT.md                 the CIll agent prompt
  UPSTREAM_README.md        original artifact README, kept for provenance
  requirements.txt          pinned Python MCP/VCD dependencies
  rIC3/                     patched rIC3 1.5.2 source and release binary
  deps/yosys/               Yosys source, reference only; already installed
  deps/yosys-slang/         yosys-slang source and built slang.so
  deps/riscv-formal/        riscv-formal library copy
  tools/analyze_stats.py    parse one saved CIll result directory
```

The benchmark cases are **not copied here**. They stay under
`benchmarks/` so the same case inputs are used by all baselines.

`UPSTREAM_README.md` is the original artifact README. Its
global-install/gen.sh instructions are superseded by this procedure.

## 1. Prerequisites

Run these checks before starting an experiment.

```sh
export FASSERT=/home/AM2/sec/cur_work/fassert
export CILL="$FASSERT/baselines/cill"
export BENCHMARKS="$FASSERT/benchmarks"
export RIC3="$CILL/rIC3/target/release/ric3"
export PATH="/usr/local/bin:$PATH"
```

An agent with shell access is required for the loop. The agent may be an
interactive coding CLI, an API-driven agent, or a human operator. Nothing in
this procedure depends on a particular agent product.

### Yosys

Yosys is already built and installed in this environment. Do not rebuild it for
each baseline run.

```sh
yosys -V
# Yosys 0.60+70 (git sha1 8101c87fa, ...)
```

The vendored `deps/yosys/` tree is a reference copy of the source; the runnable
tool is the installed `yosys` on `PATH`.

### Yosys-Slang

The plugin is already built at:

```text
baselines/cill/deps/yosys-slang/build/slang.so
```

It is also installed system-wide on this machine. Verify:

```sh
yosys -m slang -p 'help read_slang' | head
```

If a clean environment does not have the plugin installed globally, point
Yosys at the bundled build:

```sh
export YOSYS_PLUGIN_PATH="$CILL/deps/yosys-slang/build"
```

### rIC3

Use the **bundled** patched binary, not the unmodified `~/.cargo/bin/ric3`:

```sh
"$RIC3" --version
# rIC3 1.5.2
```

The patch is in `rIC3/src/cli/yosys.rs` and adds
`--allow-genblk-reference` to the `read_slang` command. That flag is required
for cases that reference generated blocks such as `genblk1.pcpi_mul.*`.

### VCD inspection tools

The CIll prompt uses two VCD operations:

- `vcd.search_signals(vcd_path, pattern)`
- `vcd.signal_values(vcd_path, signals)`

They are implemented by `rIC3/tools/vcd_mcp.py`, which can be exposed as an MCP
server when the agent supports MCP. MCP is a convenience only. An agent without
MCP can call the same functions directly:

```python
import os, sys
sys.path.insert(0, os.path.join(os.environ["CILL"], "rIC3", "tools"))
import vcd_mcp
vcd_mcp.search_signals(vcd_path, "pc_wdata")
vcd_mcp.signal_values(vcd_path, ["rvfi_pc_wdata"])
```

Check the Python environment and the server import path:

```sh
python3 -m pip install -r "$CILL/requirements.txt"
PYTHONPATH="$CILL/rIC3/tools" python3 -c 'import vcd_mcp; print("vcd tools ok")'
```

If the agent uses MCP, register the server using that agent's own MCP
configuration mechanism and point it at:

```text
python3 $CILL/rIC3/tools/vcd_mcp.py
```

Exposed tool names are `search_signals` and `signal_values` (the MCP namespace
may prefix them, for example `vcd.search_signals`). Both require an absolute
`vcd_path`, for example
`/tmp/opencode/cill/picorv32/insn_add/ric3proj/cill/cti.vcd`.

Record the agent identity and model in the result row. If a different model is
used, record the exact model ID; don't silently compare across models.

## 2. Case selection and staging

The CIll baseline is initially defined for the RVFI cases:

- `benchmarks/picorv32/` — 43 active cases;
- `benchmarks/serv/` — 4 cases;
- `benchmarks/nerv/` — 25 cases.

`benchmarks/picorv32_full/` is the 30-case preserved set and is not part of the
active baseline. `flute/` and `piccolo/` are the ILA/BMC-depth family and are
not the primary CIll baseline.  They have no `tb.sv`, but their `wrapper.v` is
the formal top containing the harness and assertions, so they can still be run
with `ric3 build` followed by `ric3 cill check`; see
`benchmarks/flute/README.md` and `benchmarks/piccolo/README.md`.
See `CASES.md` for the selection commands.

Stage one clean copy per run. Do not run in the benchmark tree and do not reuse
a `ric3proj/` directory:

```sh
export FAMILY=picorv32
export CASE=insn_add
export SB="/tmp/opencode/cill/$FAMILY/$CASE"

rm -rf "$SB"
mkdir -p "$(dirname "$SB")"
cp -rL "$BENCHMARKS/$FAMILY/$CASE" "$SB"
rm -rf "$SB/ric3proj"
cd "$SB"
```

`cp -rL` materializes the case as a normal directory. The benchmark cases are
already self-contained and should not contain active symlinks.

### Verify the empty helper set

The baseline starts with an empty helper block. The block is in `tb.sv` for the
RVFI cases:

```systemverilog
/// Helper Assertion Begin
/// Helper Assertion End
```

Check that no helper assertion is already present:

```sh
awk '
  /\/\/\/ Helper Assertion Begin/ { in_block=1; next }
  /\/\/\/ Helper Assertion End/   { in_block=0; next }
  in_block && NF                   { print; found=1 }
  END                              { exit found ? 1 : 0 }
' tb.sv
```

Also check that no `h_*` assertion is present:

```sh
grep -RInE '\bh_[A-Za-z0-9_]*[[:space:]]*:' . \
  --include='*.sv' --include='*.v' || true
```

If either check fails, the case is not a clean CIll baseline start. Do not
delete assertions from the benchmark; report the case as contaminated or make a
fresh copy from the canonical benchmark path.

### Record the original model

Build the original model and record its SHA-256 before any helper assertion is
added:

```sh
/usr/bin/time -f '%e' -o build.time "$RIC3" build
sha256sum ric3proj/dut/dut.btor | tee model.original.sha256
```

The original BTOR hash is the model ID. Helper assertions change `tb.sv`, so a
later build will have a different hash; record that separately as
`model.final.sha256`. Comparisons across methods use the **original** model ID.

If the build fails, record `BUILD_ERROR` and stop. It is not an
`UNKNOWN` proof result.

## 3. Run the CIll loop

Start the budget timer before the first `ric3 cill check`:

```sh
date +%s > start.epoch
```

Set a budget. CIll's published baseline used a 5-hour budget and CIll runs were
capped around 6 hours; local runs may use a smaller budget such as 1800 or 3600
seconds. Record whichever budget was actually used.

```sh
export CILL_BUDGET=18000
timeout "$CILL_BUDGET" "$RIC3" cill check 2>&1 | tee cill.check.log
```

`ric3 cill check` does three things:

1. BMC checks correctness and reports a counterexample if one exists;
2. checks inductiveness of every property;
3. validates a previously selected CTI if one exists.

It rebuilds the model when the input files change. The rebuild time after a
helper edit is part of `T_ind`; the initial build is recorded separately as
`T_build`.

### Reading the first result

There are four cases.

**All properties inductive.**

```text
All properties are inductive. Proof succeeded.
CIll Statistic: Total time: 123s, Correctness check: 4s, Inductiveness check: 118s
```

Record `INDUCTIVE`. `T_ind` is the wall-clock interval from `start.epoch` to the
completion of this check. Also record the `CIll Statistic` fields as a
cross-check. The statistic starts at the first CIll check, not at `ric3 build`.

**A target counterexample.**

```text
A CEX violating o_rd_wdata_match was found. VCD generated at ...
```

Record `CEX`. The counterexample is a definitive result for that target
property, not a depth result. Stop the baseline for this case.

**A helper counterexample.**

If the violating name is `h_*`, the agent's helper is wrong, not the original
property. Remove or fix the helper and continue. Do not record this as a target
`CEX`.

**At least one property is not inductive.**

The output contains a table like:

```text
ID  Property                    Result
0   o_rd_wdata_match            Not Inductive
1   o_pc_wdata_match            Not Inductive
```

Record the table, then run the agent loop. Do not switch to BMC depth yet.

### Agent loop

Start the agent in the sandbox. Any agent with shell access works; no specific
CLI is required:

```sh
cd "$SB"
# start the chosen agent here, or operate the loop directly
```

Tell the agent:

```text
Read $CILL/PROMPT.md and follow it exactly.
Work only in this directory. Do not modify the original DUT or o_* assertions.
Inspect CTIs with the VCD tools (MCP or direct Python calls; see Prerequisites).
Stop when all original properties are inductive or the budget is exhausted.
```

The loop is:

```text
ric3 cill check
    -> if all properties inductive: stop
    -> if a target CEX: stop with CEX
    -> if not inductive:
         ric3 cill select <ID>
         inspect ric3proj/cill/cti.vcd with the VCD tools
         add h_* helper assertions between the two markers
         repeat
```

Useful commands:

```sh
"$RIC3" cill select 0
"$RIC3" cill abort
```

`select` writes:

```text
ric3proj/cill/cti.vcd
```

The VCD is a trace ending in the violating step. Short k-induction traces often
have four steps, but a larger induction depth can produce a longer trace; what
matters is that all states before the final one satisfy the assertions and the
final state violates the selected assertion. Signals absent from the VCD, or
bits marked `x`, are irrelevant to that CTI.

### Hard constraints

The agent may:

- add, modify, or delete code only between
  `/// Helper Assertion Begin` and `/// Helper Assertion End`;
- name helper assertions and auxiliary registers `h_*`;
- use `$past` and `assert`.

The agent must not:

- add `assume` statements;
- modify the original DUT logic or `o_*` assertions;
- create a second helper block;
- use hand-written helpers from `automation/decomp/` or any proof graph;
- edit `ric3proj/` except by running the CIll commands;
- run other `ric3` commands during the CIll loop.

Existing harness `assume` statements in the benchmark are part of the benchmark,
not agent-added helpers. Record them in the run notes; do not remove them.

### Time accounting

Use one definition for every row:

```text
T_prepare = setup/agent bootstrap before the first `ric3 cill check`
T_build   = time for the initial `ric3 build`
T_ind     = wall clock from the first `ric3 cill check` to the final
            all-inductive check, or to the stop decision for a failed run
T_total   = T_prepare + T_build + T_ind
```

Record `T_prepare` separately; do not silently fold it into `T_ind`.

`T_ind` includes:

- agent proposal time;
- helper editing time;
- CTI selection and VCD inspection;
- every `ric3 cill check` rebuild;
- the CIll gate: BMC correctness checks and inductive checks;
- waiting time between agent commands.

It excludes environment setup and the initial build. Report the CIll statistic
as well:

```text
ci_stats_total_s
ci_stats_bmc_s
ci_stats_ind_s
```

If the wall clock and the CIll statistic disagree, report both; do not silently
choose the smaller number.

## 4. Outcome classification

Use exactly these primary outcomes:

| Status | Meaning |
|---|---|
| `INDUCTIVE` | Every original property is inductive at the end of the run. |
| `CEX` | A target `o_*` property has a counterexample. |
| `NOT_INDUCTIVE` | No target CEX, but at least one original property remains non-inductive at the budget. |
| `UNKNOWN` | The tool ended without a usable inductive/CEX verdict. |
| `TIMEOUT` | The run was stopped by the budget. |
| `BUILD_ERROR` | The model could not be built. Infrastructure result, not a proof result. |

`INDUCTIVE` is a CIll engine verdict. It is not automatically
`PROVED_CHECKED`: the model/front-end and any harness assumptions remain in the
TCB, and the project's separate vacuity/soundness gate must still be recorded.
Do not label a CIll run `PROVED_CHECKED` solely because CIll printed
"Proof succeeded".

The current `automation/ifi/vacuity_gate.py` is an AIG/SymbiYosys workdir gate,
not a BTOR CIll gate. Do not claim it was run on a CIll BTOR unless it has been
adapted and the adaptation is recorded.

## 5. BMC depth fallback

Only run this for `NOT_INDUCTIVE`; never for `CEX`, `UNKNOWN`, or `TIMEOUT`,
and never as a substitute for an inductive result. If a run is `UNKNOWN` or
`TIMEOUT`, report that status without a depth; a depth is meaningful only
after a run has established that the original properties are non-inductive.

Use the same original BTOR and the bundled rIC3:

```sh
timeout "$BMC_BUDGET" "$RIC3" check \
  ric3proj/dut/dut.btor bmc --end "$K"
```

The command prints `UNSAT` when no counterexample exists up to `K`, `SAT` when
one is found, and `UNKNOWN` if the bound/budget is exhausted.

A depth is the largest `K` for which the run returns `UNSAT` within the budget.
Use a monotone bound schedule and record the exact schedule. Do not report the
requested `--end` value as the achieved depth without checking the result.

Record:

```text
bmc_budget_s
bmc_max_depth
bmc_result          UNSAT | SAT | UNKNOWN
depth_to_cex        only when bmc_result = SAT
```

A depth is bounded coverage, not a proof. The depth is comparable only when the
engine, bound schedule, model hash, and budget are the same.

## 6. Result row

Record one row per run. A CSV header that matches the project protocol is:

```csv
family,case,status,model_sha256,helper_assertions,T_prepare_s,T_build_s,T_ind_s,T_total_s,ci_stats_total_s,ci_stats_bmc_s,ci_stats_ind_s,orig_props_total,orig_props_inductive,cti_ids,cex_property,bmc_budget_s,bmc_max_depth,bmc_result,depth_to_cex,agent,agent_model,budget_s,commands,notes
```

`model_sha256` is the **original** BTOR hash; put the final helper-bearing hash
in `notes` or a separate artifact. Minimum fields:

- `family`, `case`;
- `status`;
- original `model_sha256`;
- `T_prepare_s`, `T_build_s`, `T_ind_s`, `T_total_s`;
- CIll statistic fields;
- number of original properties and number inductive;
- selected CTI IDs;
- target CEX property, if any;
- helper count or helper line count;
- budget;
- agent/model version;
- exact tool versions and commands;
- notes about harness assumptions.

For an `INDUCTIVE` row, also record whether the separate vacuity/soundness gate
was run. If it was not, say so explicitly.

## 7. Clean-run rules

- One fresh case copy per run; never reuse `ric3proj/` across runs.
- Stage with `cp -rL`; do not run inside `benchmarks/`.
- Use the bundled patched rIC3 binary.
- Use the installed Yosys; do not rebuild it for each case.
- Set `YOSYS_PLUGIN_PATH` only when the global plugin is unavailable.
- Do not use `automation/decomp/` helpers, proof graphs, or evidence files.
- Do not use `benchmarks/test4neuroabs/` for CIll.
- Keep the original target assertions unchanged.
- Record the original model hash before adding helpers.
- Record one common budget per stage; CIll's published 5h/6h budget and local
  1800/3600s budgets are not interchangeable.
- For stochastic agent runs, repeat with recorded seeds/model settings and
  report the distribution, not only the best run.

## 8. Sanity check

A single-case smoke test, without the agent loop:

```sh
export FAMILY=picorv32
export CASE=insn_add
export SB="/tmp/opencode/cill/$FAMILY/$CASE"

rm -rf "$SB"; mkdir -p "$(dirname "$SB")"
cp -rL "$BENCHMARKS/$FAMILY/$CASE" "$SB"
rm -rf "$SB/ric3proj"
cd "$SB"

"$RIC3" build
sha256sum ric3proj/dut/dut.btor
"$RIC3" cill check
```

This verifies the front-end, Slang plugin, BTOR generation, and the CIll
command. It does not establish a baseline result; use the staged, timed, and
recorded procedure above for that.
