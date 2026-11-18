"""Tests for engine timing parsing and the cross-case summary table."""
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.summary import write_summary  # noqa: E402
from pipeline.timing import parse_statistic_ron  # noqa: E402


class TimingTest(unittest.TestCase):
    def test_parses_ric3_statistic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "statistic.ron"
            path.write_text(
                '(start:"2026-11-01T04:00:00Z",bmc_time:(17,250000000),'
                'ind_time:(82,750000000))\n',
                encoding="utf-8",
            )
            timing = parse_statistic_ron(path)
            self.assertIsNotNone(timing)
            assert timing is not None
            self.assertEqual(timing["bmc_seconds"], 17.25)
            self.assertEqual(timing["ind_seconds"], 82.75)
            self.assertEqual(timing["engine_seconds"], 100.0)
            self.assertEqual(timing["start"], "2026-11-01T04:00:00Z")

    def test_missing_statistic_is_not_invented(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(parse_statistic_ron(Path(tmp) / "missing.ron"))


class SummaryTest(unittest.TestCase):
    def _run(self, base: Path, case_id: str, run_id: str, **overrides) -> None:
        run = base / case_id / run_id
        run.mkdir(parents=True)
        report = {
            "accepted": False,
            "verdict": "REJECT",
            "inv": 2,
            "tcb_count": 0,
            "engine_included": True,
            "engine_calls": [{"log": f"logs/{run_id}.log"}],
            "timing": {
                "wall_seconds": 10.0,
                "engine_seconds": 9.0,
                "engine_runs": 1,
                "sources": ["statistic.ron"],
            },
        }
        report.update(overrides)
        (run / "report.json").write_text(json.dumps(report), encoding="utf-8")
        (run / "run.json").write_text(json.dumps({"wall_seconds": 10.0}), encoding="utf-8")


    def test_missing_report_is_counted_as_error_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            run = base / "smoke_machine_core" / "run-build-fail"
            run.mkdir(parents=True)
            (run / "run.json").write_text(
                json.dumps(
                    {
                        "result": "error",
                        "wall_seconds": 1.5,
                        "engine_included": True,
                    }
                ),
                encoding="utf-8",
            )
            self._run(
                base,
                "smoke_machine_core",
                "run-ok",
                accepted=True,
                verdict="ACCEPT",
                inv=1,
                timing={
                    "wall_seconds": 10.0,
                    "engine_seconds": 9.0,
                    "engine_runs": 1,
                    "sources": ["statistic.ron"],
                },
            )
            out = base / "SUMMARY.csv"
            write_summary(runs_dir=str(base), output_csv=str(out))
            with out.open(encoding="utf-8", newline="") as fh:
                row = list(csv.DictReader(fh))[0]
            self.assertEqual(row["verdict"], "ACCEPT")
            self.assertEqual(row["time_s"], "11.50")
            self.assertEqual(row["tried"], "1")
            self.assertEqual(row["engine_s"], "9.00")

    def test_csv_uses_all_attempts_and_final_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._run(base, "smoke_machine_core", "run-a")
            self._run(
                base,
                "smoke_machine_core",
                "run-b",
                accepted=True,
                verdict="ACCEPT",
                inv=3,
                timing={
                    "wall_seconds": 20.0,
                    "engine_seconds": 18.0,
                    "engine_runs": 1,
                    "sources": ["statistic.ron"],
                },
            )
            out = base / "SUMMARY.csv"
            result = write_summary(runs_dir=str(base), output_csv=str(out))
            self.assertTrue(Path(result["csv"]).is_file())
            with out.open(encoding="utf-8", newline="") as fh:
                rows = list(csv.DictReader(fh))
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["case"], "machine/core")
            self.assertEqual(row["verdict"], "ACCEPT")
            self.assertEqual(row["time_s"], "30.00")
            self.assertEqual(row["tried"], "2")
            self.assertEqual(row["engine_s"], "27.00")
            self.assertEqual(row["engine_over_total"], "0.900")
            self.assertEqual(row["inv"], "3")
            self.assertEqual(row["engine_included"], "yes")
            self.assertEqual(row["tcb"], "0")


if __name__ == "__main__":
    unittest.main()
