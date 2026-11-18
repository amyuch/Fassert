"""Structured induction checker tests.

The checker is intentionally narrow: base, consecution, and exit over an
explicit transition system.  These tests pin the positive case and two negative
controls so an unconstrained or non-inductive payload cannot pass.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from checkers import expr  # noqa: E402
from checkers import induction  # noqa: E402


def _payload() -> dict:
    return {
        "vars": [
            {"name": "m", "sort": "Int"},
            {"name": "n", "sort": "Int"},
            {"name": "d", "sort": "Int"},
            {"name": "q", "sort": "Int"},
            {"name": "msk", "sort": "Int"},
            {"name": "D", "sort": "Int"},
        ],
        "init": ["d = m", "q = 0", "msk = 2^31", "D = n * msk", "m >= 0", "n >= 0"],
        "step": [
            "D = n * msk",
            "d_next = ite(D <= d, d - D, d)",
            "q_next = ite(D <= d, q + msk, q)",
            "m_next = m",
            "n_next = n",
            "msk_next = msk / 2",
        ],
        "inv": ["d + n*q = m", "d >= 0", "q >= 0", "m >= 0", "n >= 0", "msk >= 0"],
        "exit": ["msk = 0", "n > 0", "d < n"],
        "goal": "(d + n*q = m) && (d < n)",
    }


class InductionTest(unittest.TestCase):
    def test_ite_round_trip(self) -> None:
        ast = expr.parse("ite(a < 0, -a, a)")
        self.assertEqual(expr.to_text(ast), "ite((a < 0), -a, a)")

    def test_proves_restoring_division_invariant(self) -> None:
        ok, detail = induction.check([], _payload()["goal"], _payload(), 30_000)
        self.assertTrue(ok, detail)

    def test_rejects_non_inductive_step(self) -> None:
        payload = _payload()
        payload["step"] = [s for s in payload["step"] if not s.startswith("d_next")]
        ok, detail = induction.check([], payload["goal"], payload, 30_000)
        self.assertFalse(ok)
        self.assertIn("consecution", detail)

    def test_rejects_unbound_helper_symbol(self) -> None:
        payload = _payload()
        payload["goal"] = "helper_ok"
        ok, detail = induction.check([], payload["goal"], payload, 30_000)
        self.assertFalse(ok)
        self.assertIn("undeclared variable", detail)
