"""Tests for the shared, oracle-independent PCD utilities."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

PCD = Path(__file__).resolve().parents[1]
AUTOMATION = PCD.parent
if str(AUTOMATION) not in sys.path:
    sys.path.insert(0, str(AUTOMATION))

from common.pcd_util import canonical_json, load_json_or_yaml, resolve_path, sha256_json  # noqa: E402


class PcdUtilTest(unittest.TestCase):
    def test_canonical_json_is_order_independent(self) -> None:
        self.assertEqual(canonical_json({"b": 2, "a": 1}), canonical_json({"a": 1, "b": 2}))
        self.assertEqual(sha256_json({"a": 1, "b": 2}), sha256_json({"b": 2, "a": 1}))

    def test_resolve_path(self) -> None:
        self.assertEqual(resolve_path("/tmp/base", "logs/a.log"), "/tmp/base/logs/a.log")
        self.assertEqual(resolve_path("/tmp/base", "/abs/a.log"), "/abs/a.log")

    def test_load_json_or_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.json"
            path.write_text(json.dumps({"a": 1}), encoding="utf-8")
            self.assertEqual(load_json_or_yaml(str(path)), {"a": 1})
            bad = Path(tmp) / "bad.json"
            bad.write_text("[1, 2]", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_json_or_yaml(str(bad))


if __name__ == "__main__":
    unittest.main()
