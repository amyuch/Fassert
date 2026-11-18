# CIll baseline links and provenance

This file records where the CIll toolchain and the benchmark inputs come from,
which local copies are authoritative, and which external copies are only
reference material.

## Toolchain

| Component | Version / identity | Local path | Upstream |
|---|---|---|---|
| CIll artifact | CIll paper artifact | `baselines/cill/` | https://arxiv.org/abs/2602.23389 |
| rIC3 | 1.5.2, local patched build | `baselines/cill/rIC3/` | https://github.com/gipsyh/rIC3 |
| rIC3 binary | release build | `baselines/cill/rIC3/target/release/ric3` | built from the local tree |
| Yosys | 0.60+70, git sha `8101c87fa` | `/usr/local/bin/yosys` (installed) | https://github.com/YosysHQ/yosys |
| Yosys source | 0.60+70 | `baselines/cill/deps/yosys/` | reference copy; do not rebuild for each run |
| Yosys-Slang | built plugin | `baselines/cill/deps/yosys-slang/build/slang.so` | https://github.com/povik/yosys-slang |
| Yosys-Slang install | installed plugin | `/usr/local/share/yosys/plugins/slang.so` | use the installed one by default |
| riscv-formal | shared library copy | `baselines/cill/deps/riscv-formal/` | https://github.com/SymbioticEDA/riscv-formal |
| VCD tools | `search_signals`, `signal_values` (MCP server optional) | `baselines/cill/rIC3/tools/vcd_mcp.py` | local artifact |
| Python MCP SDK | `mcp==2.2.0` | `baselines/cill/requirements.txt` | https://pypi.org/project/mcp/ |
| VCD parser | `vcdvcd==2.6.0` | `baselines/cill/requirements.txt` | https://pypi.org/project/vcdvcd/ |

### Important rIC3 patch

Use the bundled rIC3 binary, not the global unmodified one:

```text
baselines/cill/rIC3/target/release/ric3
```

The local source changes the Yosys frontend command in
`rIC3/src/cli/yosys.rs` to:

```text
read_slang -Wnone -D FORMAL -D YOSYS_SLANG --allow-genblk-reference
```

`--allow-genblk-reference` is required for cases that reference generated
blocks such as `genblk1.pcpi_mul.*`. The global
`~/.cargo/bin/ric3` is unmodified and should not be used for the baseline.

### Yosys

Yosys is already built and installed at `/usr/local/bin/yosys`. The
`deps/yosys/` tree is a vendored source reference; rebuilding it is not part of
a baseline run.

The installed version can be checked with:

```sh
yosys -V
```

### Yosys-Slang

The built plugin is:

```text
baselines/cill/deps/yosys-slang/build/slang.so
```

If the installed copy under `/usr/local/share/yosys/plugins/` is present, no
environment variable is needed. Otherwise:

```sh
export YOSYS_PLUGIN_PATH="/home/AM2/sec/cur_work/fassert/baselines/cill/deps/yosys-slang/build"
```

Verify with:

```sh
yosys -m slang -p 'help read_slang' | head
```

## CIll prompt and agent

The upstream CIll prompt is:

```text
./PROMPT.md
```

CIll is agent-driven, not tied to a particular CLI. Any agent with shell access
can run the loop; the upstream artifact used Codex, but that is only one
possible driver. The VCD tools are also interface-agnostic: an MCP server is
provided for agents that support MCP, and the same functions can be called
directly from Python otherwise.

It defines the loop:

1. `ric3 cill check` checks BMC correctness and inductiveness;
2. `ric3 cill select <ID>` produces a CTI for a non-inductive property;
3. the agent inspects `ric3proj/cill/cti.vcd` with the VCD tools (MCP server or
   direct Python calls are equivalent);
4. the agent adds `h_*` assertions between the helper markers;
5. repeat until all properties are inductive.


## Benchmarks

Read CASES.md.

Every runnable case is a directory with `ric3.toml`; `picorv32`, `serv`, and
`nerv` list their local RTL and checker files explicitly. The case directories
are materialized, not symlink farms.


