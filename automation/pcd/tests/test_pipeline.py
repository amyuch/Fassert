"""Pipeline tests with a synthetic case and a deterministic fake engine."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import sys
import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.backends import (  # noqa: E402
    default_diagnostics,
    default_engines,
    normalize_diagnostics,
    resolve_diagnostic_command,
)
from pipeline import cti  # noqa: E402
from pipeline.core import (  # noqa: E402
    PcdError,
    canonical_hash,
    freeze_json,
    load_case,
    new_run_dir,
    stage_case,
    parse_verdict,
    run_command,
)
from pipeline.discharge import run_discharge  # noqa: E402
from pipeline.e2e import run_e2e  # noqa: E402
from pipeline.plan import load_proposals, run_plan, template_proposals  # noqa: E402
from pipeline.report import run_report  # noqa: E402
from pipeline.sketch import load_context, run_sketch  # noqa: E402
from pipeline.verify import run_check  # noqa: E402
from pipeline.audit import _diagnostics_context_ok, run_audit  # noqa: E402
from pipeline import sandbox  # noqa: E402
from checkers import expr as expr_mod  # noqa: E402


CASE = {
    "schema_version": "pcd-case/0.1",
    "case": "synthetic",
    "claim_scope": "safety",
    "inputs": {
        "files": [{"path": "input/rtl/check.sv", "role": "checker"}],
        "environment": {"top": "checker", "reset": "reset", "frontend": "other"},
    },
    "build": {
        "kind": "btor",
        "recipe": {"command": ["sh", "build/build.sh"]},
        "outputs": [{"path": "build/model.btor", "kind": "btor"}],
    },
    "targets": [
        {
            "id": "root",
            "statement": "both observations match",
            "claim_level": "root",
            "model_ref": "primary",
        }
    ],
    "budgets": {"total_seconds": 30, "max_iterations": 1, "engine_seconds": {"ric3": 5}},
    "run_policy": {
        "mode": "blind",
        "oracle_paths": ["oracle/"],
        "pre_registered": True,
    },
}


def _sandbox_usable() -> bool:
    """Namespace integration tests need working bwrap, not just a binary."""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            command = sandbox.wrap_command(["true"], cwd=Path(tmp), run_dir=Path(tmp))
            return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5).returncode == 0
        except (PcdError, OSError, subprocess.TimeoutExpired):
            return False


BWRAP_USABLE = _sandbox_usable()


class PipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.case_dir = self.base / "case"
        (self.case_dir / "input" / "rtl").mkdir(parents=True)
        (self.case_dir / "build").mkdir()
        (self.case_dir / "oracle").mkdir()
        (self.case_dir / "oracle" / "secret.txt").write_text("prior decomposition\n", encoding="utf-8")
        doc = json.loads(json.dumps(CASE))
        doc["run_policy"]["mode"] = "dev"
        (self.case_dir / "case.json").write_text(json.dumps(doc), encoding="utf-8")
        (self.case_dir / "input" / "rtl" / "check.sv").write_text(
            "module checker;\n"
            "  // observation labels are part of the legitimate checker surface\n"
            "  o_pc_wdata_match: assert (a == b);\n"
            "  o_rd_wdata_match: assert (c == d);\n"
            "endmodule\n",
            encoding="utf-8",
        )
        (self.case_dir / "build" / "build.sh").write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "root=$(CDPATH= cd -- \"$(dirname \"$0\")/..\" && pwd)\n"
            "mkdir -p \"$root/build\"\n"
            "cat > \"$root/build/model.btor\" <<'EOF'\n"
            "1 sort bitvec 1\n"
            "2 input 1 check ; check.sv:1\n"
            "66 bad 65 o_pc_wdata_match ; check.sv:3.2-3.30\n"
            "85 bad 84 o_rd_wdata_match ; check.sv:4.2-4.30\n"
            "EOF\n",
            encoding="utf-8",
        )
        os.chmod(self.case_dir / "build" / "build.sh", 0o755)
        # Keep the fake engine inside the staged case so the blind sandbox can
        # execute it without needing access to the source tree.
        self.fake = self.case_dir / "build" / "fake-engine.sh"
        self.fake.write_text("#!/bin/sh\necho UNSAT\nexit 0\n", encoding="utf-8")
        os.chmod(self.fake, 0o755)
        self.fake_cill = self.case_dir / "build" / "fake-cill.sh"
        self.fake_cill.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "phase=$1\n"
            "mkdir -p ric3proj/cill\n"
            "if [ \"$phase\" = check ]; then\n"
            "  printf '%s\\n' 'BMC found no CEX in limited steps.' \\\n"
            "    ' 0  o_pc_wdata_match  Not Inductive ' \\\n"
            "    ' 1  o_rd_wdata_match  Not Inductive '\n"
            "elif [ \"$phase\" = select ]; then\n"
            "  index=$2\n"
            "  printf '%s\\n' sat b0 '#0' '0 1' '1 0' '#1' '0 0' '1 1' '.' \\\n"
            "    > ric3proj/cill/cti\n"
            "  printf '%s\\n' '$timescale 1 ns $end' \\\n"
            "    '$scope module top $end' \\\n"
            "    '$var wire 1 ! rvfi_valid $end' \\\n"
            "    '$var wire 32 \" rvfi_insn $end' \\\n"
            "    '$upscope $end' '#0' '1 !' \\\n"
            "    'b00000000000000000000000000000001 \"' '#1' '1 !' \\\n"
            "    'b00000000000000000000000000000010 \"' \\\n"
            "    > ric3proj/cill/cti.vcd\n"
            "  if [ \"$index\" = 0 ]; then\n"
            "    printf 'Block(\"o_pc_wdata_match\")\\n' > ric3proj/cill/state.ron\n"
            "  else\n"
            "    printf 'Block(\"o_rd_wdata_match\")\\n' > ric3proj/cill/state.ron\n"
            "  fi\n"
            "  printf 'CTI VCD generated in ric3proj/cill/cti.vcd.\\n'\n"
            "fi\n",
            encoding="utf-8",
        )
        os.chmod(self.fake_cill, 0o755)
        self.engines = default_engines()
        self.engines["fake"] = {"backends": {"portfolio": ["sh", "build/fake-engine.sh"]}}
        self.diagnostics = normalize_diagnostics(
            {
                "ric3-cill": {
                    "commands": {
                        "check": ["sh", "fake-cill.sh", "check"],
                        "select": ["sh", "fake-cill.sh", "select", "{property}"],
                    }
                }
            }
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _prepare(self, engines: dict | None = None) -> tuple[Path, dict, dict, dict, dict]:
        case_dir, case = load_case(self.case_dir)
        run_dir = new_run_dir(case["case"], self.base / "runs")
        from pipeline.build import run_build

        build = run_build(run_dir, case_dir, case)
        context = run_sketch(run_dir, case, build, engines=engines)
        proposals = run_plan(run_dir, case, planner="template")
        return run_dir, case, build, context, proposals

    def _manual_proposal(self, helper: bool = False) -> Path:
        def leaf(index: int, name: str) -> dict:
            item = {
                "id": f"property.{name}",
                "role": "observe",
                "kind": "replay",
                "phase": "any",
                "statement": f"fake engine proves {name}",
                "requires": [],
                "provides": [{"name": f"G{index}", "expr": f"p_{index}", "sort": "Bool"}],
                "certificate_hint": {
                    "evidence": "REPLAY",
                    "format": "replay",
                    "goal": f"G{index}",
                    "engine": "fake",
                    "backend": "portfolio",
                    "timeout_s": 5,
                    "assertion_name": name,
                    "assertion_file": "input/rtl/check.sv",
                },
            }
            if helper and index == 0:
                item["helper"] = {"kind": "monitor"}
            return item

        reqs = [
            {"node": "property.o_pc_wdata_match", "guarantee": "G0"},
            {"node": "property.o_rd_wdata_match", "guarantee": "G1"},
        ]
        smt = expr_mod.canonical_script(["p_0", "p_1"], "(and p_0 p_1)")
        doc = {
            "schema_version": "pcd-proposal/0.1",
            "case": "synthetic",
            "planner": {"name": "manual", "version": "test"},
            "nodes": [
                leaf(0, "o_pc_wdata_match"),
                leaf(1, "o_rd_wdata_match"),
                {
                    "id": "root",
                    "role": "compose",
                    "kind": "linear",
                    "phase": "any",
                    "statement": "both observations match",
                    "requires": reqs,
                    "provides": [{"name": "GOAL", "expr": "(and p_0 p_1)", "sort": "Bool"}],
                    "certificate_hint": {
                        "evidence": "CHECKED",
                        "format": "smt-implication",
                        "checker": "z3-implication",
                        "goal": "GOAL",
                        "payload": {"premises": reqs, "goal": "GOAL", "smt2": smt},
                    },
                },
            ],
            "targets": [
                {
                    "id": "root",
                    "goal": "GOAL",
                    "requires": reqs,
                    "tcb": [],
                    "composition_hint": {
                        "mode": "CHECKED",
                        "checker": "z3-implication",
                        "payload": {"premises": reqs, "goal": "GOAL", "smt2": smt},
                    },
                }
            ],
        }
        path = self.base / "manual-proposal.json"
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def test_e2e_manual_fake_accepts(self) -> None:
        proposal_path = self._manual_proposal()
        run, run_dir = run_e2e(
            str(self.case_dir),
            planner="manual",
            manual_path=str(proposal_path),
            runs_dir=str(self.base / "runs-e2e"),
            engines=self.engines,
        )
        self.assertEqual(run.get("result"), "accepted", json.dumps(run, indent=2))
        self.assertTrue((run_dir / "report.md").is_file())
        self.assertTrue((run_dir / "audit.json").is_file())
        check = json.loads((run_dir / "check.json").read_text(encoding="utf-8"))
        self.assertTrue(check["accepted"])
        self.assertEqual(check["targets"]["root"]["composition"], "CHECKED")

    def test_e2e_planner_policy_mismatch_fails_before_engine(self) -> None:
        doc = json.loads((self.case_dir / "case.json").read_text(encoding="utf-8"))
        doc["run_policy"]["planner"] = "template"
        (self.case_dir / "case.json").write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(PcdError) as caught:
            run_e2e(
                str(self.case_dir),
                planner="manual",
                manual_path=None,
                runs_dir=str(self.base / "runs-mismatch"),
            )
        self.assertIn("declared planner", str(caught.exception))

    def test_discharge_preserves_helper_role_for_kernel_check(self) -> None:
        proposal_path = self._manual_proposal(helper=True)
        run, run_dir = run_e2e(
            str(self.case_dir),
            planner="manual",
            manual_path=str(proposal_path),
            runs_dir=str(self.base / "runs-helper"),
            engines=self.engines,
        )
        self.assertEqual(run.get("result"), "accepted", json.dumps(run, indent=2))
        proof = json.loads((run_dir / "proof.json").read_text(encoding="utf-8"))
        helper_nodes = [n for n in proof["nodes"] if n.get("helper")]
        self.assertEqual(len(helper_nodes), 1)
        self.assertEqual(helper_nodes[0]["helper"]["kind"], "monitor")
        report = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["helpers"], [{"node": helper_nodes[0]["id"], "kind": "monitor"}])

    def test_stage_does_not_copy_oracle(self) -> None:
        _, case = load_case(self.case_dir)
        staged = self.base / "staged"
        stage_case(self.case_dir, staged)
        self.assertFalse((staged / "oracle").exists())
        self.assertTrue((staged / "input" / "rtl" / "check.sv").exists())

    def test_case_input_hash_is_enforced(self) -> None:
        source = self.case_dir / "input" / "rtl" / "check.sv"
        doc = json.loads((self.case_dir / "case.json").read_text(encoding="utf-8"))
        doc["inputs"]["files"][0]["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
        (self.case_dir / "case.json").write_text(json.dumps(doc), encoding="utf-8")
        _, loaded = load_case(self.case_dir)
        self.assertEqual(loaded["case"], "synthetic")
        source.write_text("module checker; endmodule\n", encoding="utf-8")
        with self.assertRaises(PcdError):
            load_case(self.case_dir)

    def test_template_is_generic_and_frozen(self) -> None:
        run_dir, case, build, context, proposals = self._prepare()
        self.assertEqual(len(context["model"]["properties"]), 2)
        self.assertEqual(len(proposals["nodes"]), 3)
        self.assertNotIn("synthetic", json.dumps(proposals["nodes"]))
        loaded, digest = load_proposals(run_dir)
        self.assertEqual(digest, canonical_hash(loaded))
        self.assertEqual(loaded["planner"]["context_sha256"], canonical_hash(context))

    def test_template_backend_is_case_data(self) -> None:
        run_dir, case, build, context, proposals = self._prepare()
        context["case"]["run_policy"]["template_backend"] = "cill"
        doc = template_proposals(context, canonical_hash(context))
        replay = [
            node["certificate_hint"]
            for node in doc["nodes"]
            if node["certificate_hint"]["evidence"] == "REPLAY"
        ]
        self.assertTrue(replay)
        self.assertEqual({hint["backend"] for hint in replay}, {"cill"})
        self.assertTrue(all("cill" in hint["note"] for hint in replay))

    def test_discharge_check_report_accepts_fake_replay(self) -> None:
        run_dir, case, build, context, proposals = self._prepare(engines=self.engines)
        # Select a trusted test backend; no command comes from the proposal.
        for node in proposals["nodes"]:
            if node["certificate_hint"]["evidence"] == "REPLAY":
                node["certificate_hint"]["engine"] = "fake"
                node["certificate_hint"]["backend"] = "portfolio"
                node["certificate_hint"]["timeout_s"] = 5
        freeze_json(run_dir / "proposals.json", proposals)
        run_discharge(run_dir, case, build=build, proposals=proposals, engines=self.engines)
        check = run_check(run_dir, case)
        self.assertTrue(check["accepted"], json.dumps(check, indent=2))
        self.assertEqual(check["targets"]["root"]["evidence"], "REPLAY")
        self.assertEqual(check["targets"]["root"]["composition"], "CHECKED")
        audit = run_audit(run_dir, case)
        self.assertTrue(audit["blind_ok"], json.dumps(audit, indent=2))
        report = run_report(run_dir, case)
        self.assertTrue(report["accepted"])
        self.assertTrue((run_dir / "report.md").is_file())

    def test_rejects_proposal_command_outside_catalog(self) -> None:
        run_dir, case, build, context, proposals = self._prepare(engines=self.engines)
        injected = self.base / "injected"
        for node in proposals["nodes"]:
            if node["certificate_hint"]["evidence"] == "REPLAY":
                node["certificate_hint"]["engine"] = "fake"
                node["certificate_hint"]["backend"] = "portfolio"
                node["certificate_hint"]["command"] = ["sh", "-c", f"touch {injected}"]
        freeze_json(run_dir / "proposals.json", proposals)
        with self.assertRaises(PcdError):
            run_discharge(run_dir, case, build=build, proposals=proposals, engines=self.engines)
        self.assertFalse(injected.exists())

    def test_blind_sandbox_fails_closed_without_bwrap(self) -> None:
        run_dir, case, build, context, proposals = self._prepare(engines=self.engines)
        with mock.patch("pipeline.sandbox.shutil.which", return_value=None):
            with self.assertRaises(PcdError):
                sandbox.wrap_command(
                    ["true"],
                    cwd=run_dir / "case",
                    run_dir=run_dir,
                )

    @unittest.skipUnless(BWRAP_USABLE, "bubblewrap namespaces are unavailable")
    def test_blind_llm_planner_is_sandboxed(self) -> None:
        doc = json.loads((self.case_dir / "case.json").read_text())
        doc["run_policy"]["mode"] = "blind"
        (self.case_dir / "case.json").write_text(json.dumps(doc))
        run_dir, case, build, context, proposals = self._prepare(engines=self.engines)
        # The external planner only needs to emit a valid proposal.  It runs
        # inside the sandbox and reads the output from the rebound run dir.
        output = run_dir / "llm-output.json"
        output.write_text(json.dumps(proposals), encoding="utf-8")
        rerun = run_plan(
            run_dir,
            case,
            planner="llm",
            llm_command=["sh", "-c", f"cat {shlex.quote(str(output))}"],
        )
        self.assertEqual(rerun["case"], "synthetic")
        self.assertIn("# sandbox: bwrap", (run_dir / "logs" / "plan.log").read_text(encoding="utf-8"))

    @unittest.skipUnless(BWRAP_USABLE, "bubblewrap namespaces are unavailable")
    def test_blind_sandbox_hides_source_oracle(self) -> None:
        doc = json.loads((self.case_dir / "case.json").read_text())
        doc["run_policy"]["mode"] = "blind"
        (self.case_dir / "case.json").write_text(json.dumps(doc))
        run_dir, case, build, context, proposals = self._prepare(engines=self.engines)
        sentinel = self.case_dir / "oracle" / "secret.txt"
        self.assertTrue(sentinel.is_file())
        log_path = run_dir / "logs" / "sandbox-check.log"
        result = run_command(
            [
                "sh",
                "-c",
                f"if test -e {shlex.quote(str(sentinel))}; then echo LEAK; else echo BLOCKED; fi",
            ],
            cwd=run_dir / "case",
            log_path=log_path,
            timeout_s=5,
            sandbox=True,
            sandbox_root=run_dir,
        )
        self.assertEqual(result["returncode"], 0, result)
        self.assertIn("BLOCKED", log_path.read_text(encoding="utf-8"))

    def test_cti_parsers_preserve_diagnostic_boundary(self) -> None:
        parsed = cti.parse_cti_file("sat\nb0\n#0\n0 0\n1 1\n@0\n2 0\n#1\n0 1\n.\n")
        self.assertEqual(parsed["status"], "sat")
        self.assertEqual(parsed["bad"], "0")
        self.assertEqual(parsed["state_frames"][0]["assignments"], {"0": "0", "1": "1"})
        self.assertEqual(parsed["input_frames"][0]["assignments"], {"2": "0"})
        self.assertEqual(len(parsed["state_frames"]), 2)

        vcd = cti.parse_vcd(
            "$timescale 1 ns $end\n"
            "$scope module wrapper $end\n"
            "$var wire 32 ! rvfi_insn $end\n"
            "$var wire 1 \" reset $end\n"
            "$upscope $end\n"
            "#0\n"
            "b0001 !\n"
            "0 \"\n"
            "#1\n"
            "b0010 !\n"
            "1 \"\n"
        )
        self.assertEqual(vcd["frames"], [0, 1])
        self.assertEqual(vcd["final"]["wrapper.rvfi_insn"]["value"], "0010")
        self.assertEqual(vcd["final"]["wrapper.reset"]["value"], "1")
        self.assertEqual(len(vcd["changes"]), 2)

    def test_cill_parse_never_turns_unknown_into_cti(self) -> None:
        parsed = cti.parse_cill_check_log("BMC: Checking correctness of all properties.\nUNKNOWN\n")
        self.assertEqual(parsed["bmc"], "unknown")
        self.assertEqual(parsed["properties"], [])
        self.assertEqual(cti.parse_select_log("Error: timeout\n")["ok"], False)
        self.assertEqual(cti.parse_select_log("CTI VCD generated.\n")["ok"], True)

    def test_cill_property_counterexample_is_not_unknown(self) -> None:
        # Actual CIll wording from the imported Piccolo LB case.
        parsed = cti.parse_cill_check_log(
            "[14:55:54 INFO] BMC: Checking correctness of all properties.\n"
            "\x1b[mA CEX violating normalassert was found. "
            "VCD generated at ric3proj/cill/cex.vcd.\x1b[m\n"
        )
        self.assertEqual(parsed["bmc"], "cex")
        self.assertEqual(parsed["properties"], [])
        from pipeline.discharge import _cill_verdict

        self.assertEqual(_cill_verdict(parsed, {"assertion_name": "normalassert"}), "cex")

    def test_diagnostic_commands_are_catalog_only(self) -> None:
        catalog = normalize_diagnostics(default_diagnostics())
        command = resolve_diagnostic_command(catalog, "ric3-cill", "select", {"property": "3"})
        self.assertEqual(command, ["ric3", "cill", "select", "3"])
        with self.assertRaises(PcdError):
            resolve_diagnostic_command(catalog, "not-registered", "check", {})
        with mock.patch("pipeline.sandbox.shutil.which", return_value=None):
            with self.assertRaises(PcdError):
                run_command(
                    ["true"],
                    cwd=self.base,
                    log_path=self.base / "sandbox.log",
                    timeout_s=1,
                    sandbox=True,
                    sandbox_root=self.base,
                )

    def test_cti_diagnosis_captures_fake_cill_artifacts(self) -> None:
        run_dir, case, build, context, proposals = self._prepare()
        diagnostics = cti.run_cti_diagnosis(
            run_dir,
            case,
            build=build,
            context=context,
            diagnostics=self.diagnostics,
            project_dir=run_dir / "case" / "build",
        )
        self.assertEqual(diagnostics["status"], "cti", json.dumps(diagnostics, indent=2))
        self.assertFalse(diagnostics["proof"])
        self.assertEqual(diagnostics["evidence"], "DIAGNOSTIC")
        self.assertEqual(len(diagnostics["ctis"]), 2)
        self.assertTrue(all(item["status"] == "cti" for item in diagnostics["ctis"]))
        self.assertTrue(all(call["sandboxed"] == (case["run_policy"]["mode"] == "blind") for call in diagnostics["calls"]))
        self.assertTrue((run_dir / "diagnostics.json").is_file())
        self.assertTrue((run_dir / "diagnostics.json.sha256").is_file())
        self.assertTrue((run_dir / "diagnostics" / "cti-000" / "cti.vcd").is_file())
        self.assertIn("top.rvfi_insn", diagnostics["ctis"][0]["vcd"]["final"])

    def test_diagnostics_context_is_bound_and_diagnostic_only(self) -> None:
        run_dir, case, build, context, proposals = self._prepare()
        cti.run_cti_diagnosis(
            run_dir,
            case,
            build=build,
            context=context,
            diagnostics=self.diagnostics,
            project_dir=run_dir / "case" / "build",
        )
        context = run_sketch(
            run_dir,
            case,
            build,
            engines=self.engines,
            diagnostics_path=run_dir / "diagnostics.json",
        )
        self.assertEqual(context["diagnostics"]["status"], "cti")
        self.assertTrue((run_dir / "diagnostics-context.json").is_file())
        self.assertTrue(_diagnostics_context_ok(run_dir, context, "dev"))
        self.assertFalse(_diagnostics_context_ok(run_dir, context, "blind"))
        (run_dir / "diagnostics-context.json").write_text("{}\n", encoding="utf-8")
        self.assertFalse(_diagnostics_context_ok(run_dir, context, "dev"))

    def test_diagnostics_context_rejects_oracle_markers(self) -> None:
        run_dir, case, build, context, proposals = self._prepare()
        cti.run_cti_diagnosis(
            run_dir,
            case,
            build=build,
            context=context,
            diagnostics=self.diagnostics,
            project_dir=run_dir / "case" / "build",
        )
        doc = json.loads((run_dir / "diagnostics.json").read_text(encoding="utf-8"))
        doc["notes"].append("see oracle/secret")
        bad = self.base / "bad-diagnostics.json"
        bad.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaises(PcdError):
            run_sketch(run_dir, case, build, engines=self.engines, diagnostics_path=bad)

    def test_verdict_parser_is_conservative(self) -> None:
        self.assertEqual(parse_verdict("info\nUNSAT\n", backend="portfolio"), "proved")
        self.assertEqual(parse_verdict("info\nUNSAT\n", backend="bmc"), "bmc_clean")
        self.assertEqual(parse_verdict("info\nUNKNOWN\n", backend="portfolio"), "unknown")
        self.assertEqual(parse_verdict("Terminated by timeout.\n", backend="portfolio"), "unknown")
        self.assertEqual(parse_verdict("counter-example found\n", backend="ic3"), "cex")


if __name__ == "__main__":
    unittest.main()
