"""Tests for importing official riscv-formal benchmark directories."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.core import PcdError, read_json, load_case  # noqa: E402
from pipeline.import_case import import_benchmark  # noqa: E402


TOML = """\
[ric3]
version = "1.6.0"

[dut]
files = ["insn_demo.v", "rvfi_insn_check.sv", "picorv32.sv", "wrapper.sv", "tb.sv"]
include_files = ["defines.sv", "rvfi_macros.vh"]
reset = "reset"
top = "testbench"

[modeling]
parser = "yosys_slang"
"""


class ImportBenchmarkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.bench = self.base / "bench" / "insn_demo"
        self.bench.mkdir(parents=True)
        (self.bench / "ric3.toml").write_text(TOML, encoding="utf-8")
        for name, body in {
            "insn_demo.v": "module insn_demo; endmodule\n",
            "rvfi_insn_check.sv": "module rvfi_insn_check; endmodule\n",
            "picorv32.sv": "module picorv32; endmodule\n",
            "wrapper.sv": "module rvfi_wrapper; endmodule\n",
            "tb.sv": "module testbench; endmodule\n",
            "defines.sv": "`define RISCV_FORMAL\n",
            "rvfi_macros.vh": "`define RVFI_INPUTS\n",
        }.items():
            (self.bench / name).write_text(body, encoding="utf-8")

        # These are exactly the things an importer must not carry into a clean
        # case: a prior run, an oracle, and an unrelated script.
        (self.bench / "run.sh").write_text("#!/bin/sh\nric3 build\n", encoding="utf-8")
        (self.bench / "notes.txt").write_text("not a source\n", encoding="utf-8")
        (self.bench / "oracle").mkdir()
        (self.bench / "oracle" / "proof.json").write_text("{}", encoding="utf-8")
        (self.bench / "ric3proj" / "dut").mkdir(parents=True)
        (self.bench / "ric3proj" / "dut" / "dut.btor").write_text("stale\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_imports_only_declared_sources_and_builds_clean_case(self) -> None:
        dest = self.base / "cases" / "demo"
        result = import_benchmark(self.bench, dest)

        self.assertEqual(result["case"], "picorv32_insn_demo")
        self.assertEqual(result["mode"], "blind")
        self.assertEqual(
            sorted(result["sources"]),
            [
                "defines.sv",
                "insn_demo.v",
                "picorv32.sv",
                "rvfi_insn_check.sv",
                "rvfi_macros.vh",
                "tb.sv",
                "wrapper.sv",
            ],
        )
        self.assertTrue((dest / "build" / "ric3.toml").is_file())
        self.assertTrue((dest / "build" / "build.sh").is_file())
        self.assertFalse((dest / "oracle").exists())
        self.assertFalse((dest / "ric3proj").exists())
        self.assertFalse((dest / "input" / "rtl" / "run.sh").exists())
        self.assertFalse((dest / "input" / "rtl" / "notes.txt").exists())

        case_dir, case = load_case(dest)
        self.assertEqual(case_dir, dest.resolve())
        self.assertEqual(case["case"], "picorv32_insn_demo")
        self.assertEqual(case["acceptance"], "complete")
        self.assertEqual(case["build"]["recipe"]["command"], ["sh", "build/build.sh"])
        self.assertEqual(case["build"]["outputs"][0]["path"], ".pcd-build/ric3proj/dut/dut.btor")
        self.assertEqual(case["targets"][0]["claim_level"], "root")
        self.assertEqual(case["run_policy"]["planner"], "template")
        self.assertEqual(case["run_policy"]["template_backend"], "cill")
        self.assertEqual({item["role"] for item in case["inputs"]["files"]}, {
            "checker",
            "defines",
            "harness",
            "include",
            "rtl",
            "spec",
        })
        for item in case["inputs"]["files"]:
            self.assertTrue((dest / item["path"]).is_file(), item["path"])
            self.assertEqual(len(item["sha256"]), 64)

    def test_imports_nested_sources_and_family_qualified_name(self) -> None:
        bench = self.base / "bench2" / "serv" / "causal"
        (bench / "rtl").mkdir(parents=True)
        (bench / "ric3.toml").write_text(
            """\
[ric3]
version = "1.6.0"

[dut]
files = ["rtl/serv_top.v", "wrapper.sv", "tb.sv"]
include_files = ["defines.sv"]
reset = "reset"
top = "testbench"

[modeling]
parser = "yosys_slang"
""",
            encoding="utf-8",
        )
        for rel, body in {
            "rtl/serv_top.v": "module serv_top; endmodule\n",
            "wrapper.sv": "module wrapper; endmodule\n",
            "tb.sv": "module testbench; endmodule\n",
            "defines.sv": "`define RISCV_FORMAL\n",
        }.items():
            path = bench / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")

        dest = self.base / "cases" / "serv_causal"
        result = import_benchmark(bench, dest, family="serv")

        self.assertEqual(result["case"], "serv_causal")
        self.assertEqual(
            sorted(result["sources"]),
            ["defines.sv", "rtl/serv_top.v", "tb.sv", "wrapper.sv"],
        )
        self.assertTrue((dest / "input" / "rtl" / "rtl" / "serv_top.v").is_file())
        self.assertIn("cp -R", (dest / "build" / "build.sh").read_text(encoding="utf-8"))
        _, case = load_case(dest)
        self.assertEqual(case["case"], "serv_causal")

    def test_rejects_source_paths_that_escape_the_benchmark(self) -> None:
        (self.base / "outside.v").write_text("module outside; endmodule\n", encoding="utf-8")
        nested = self.base / "bench" / "escape"
        nested.mkdir()
        (nested / "ric3.toml").write_text(
            """\
[dut]
files = ["../outside.v"]
top = "testbench"
""",
            encoding="utf-8",
        )
        dest = self.base / "cases" / "escape"
        with self.assertRaises(PcdError):
            import_benchmark(nested, dest)
        self.assertFalse(dest.exists())

    def test_refuses_to_overwrite_without_force(self) -> None:
        dest = self.base / "cases" / "demo"
        import_benchmark(self.bench, dest)
        with self.assertRaises(PcdError):
            import_benchmark(self.bench, dest)
        # --force is explicit and produces the same clean package again.
        import_benchmark(self.bench, dest, force=True)
        _, case = load_case(dest)
        self.assertEqual(case["case"], "picorv32_insn_demo")

    def test_rejects_missing_declared_source_before_creating_destination(self) -> None:
        (self.bench / "wrapper.sv").unlink()
        dest = self.base / "cases" / "broken"
        with self.assertRaises(PcdError):
            import_benchmark(self.bench, dest)
        self.assertFalse(dest.exists())

    def test_case_name_and_mode_are_configurable(self) -> None:
        dest = self.base / "cases" / "dev"
        result = import_benchmark(self.bench, dest, case_name="isa_demo_dev", mode="dev")
        self.assertEqual(result["case"], "isa_demo_dev")
        _, case = load_case(dest)
        self.assertEqual(case["run_policy"]["mode"], "dev")
        self.assertEqual(case["run_policy"]["oracle_paths"], [])
        self.assertEqual(json.loads((dest / "case.json").read_text(encoding="utf-8"))["case"], "isa_demo_dev")


    def test_official_isa_suite_is_clean_and_loadable(self) -> None:
        suite = read_json(ROOT / "suites" / "official_isa.json")
        expected = {
            "picorv32_addi_official",
            "picorv32_jal_official",
            "picorv32_divu_official",
        }
        self.assertEqual(set(suite["cases"]), expected)
        for ref in suite["cases"]:
            _, case = load_case(ref)
            self.assertEqual(case["run_policy"]["planner"], "template")
            self.assertEqual(case["run_policy"]["template_backend"], "cill")
            self.assertEqual(case["run_policy"]["oracle_paths"], [])
            self.assertFalse((ROOT / "cases" / ref / "oracle").exists())
            self.assertFalse((ROOT / "cases" / ref / "ric3proj").exists())


if __name__ == "__main__":
    unittest.main()
