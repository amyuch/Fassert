# serv benchmarks

Four self-contained serv cases:

| Case | Property |
|---|---|
| `causal` | causal instruction/commit behavior |
| `pc_bwd` | backward program-counter behavior |
| `pc_fwd` | forward program-counter behavior |
| `reg` | register-file/commit behavior |

Each case has its own `rtl/`, `wrapper.sv`, `tb.sv`, `defines.sv`, checker,
`rvfi_macros.vh`, and `ric3.toml`. The family-level `rtl/` and `wrapper.sv` are
canonical snapshots; `../riscv-formal/` supplies the canonical checkers and
macros.

```sh
cd causal
./run.sh
```
