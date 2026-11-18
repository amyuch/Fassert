"""Negative and positive controls for the untrusted bit-projection proposal."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT.parent)]
from checkers import bitproj, btor  # noqa: E402


def model(text: str) -> btor.Model:
    return btor.Model("<test>", text=text)


SOURCE_TWO_FREE_BITS = """1 sort bitvec 1
2 sort bitvec 2
3 state 2 free
4 slice 1 3 0 0
5 slice 1 3 1 1
6 or 1 4 5
7 bad 6 p
"""

DEST_TWO_FREE_BITS = """1 sort bitvec 1
2 state 1 a
3 state 1 b
4 or 1 2 3
5 bad 4 p
"""


class BitProjectionProposalTest(unittest.TestCase):
    def test_cross_packing_proposes_each_source_bit(self) -> None:
        source = model(SOURCE_TWO_FREE_BITS)
        destination = model(DEST_TWO_FREE_BITS)
        result = bitproj.propose_free_map(
            source,
            destination,
            {},
            source_property=source.properties["p"],
            destination_property=destination.properties["p"],
            source_states=source.states,
        )
        self.assertEqual(result[3], [(2, 0), (3, 0)])

    def test_shared_destination_bit_is_allowed(self) -> None:
        source = model(SOURCE_TWO_FREE_BITS)
        destination = model("""1 sort bitvec 1
2 state 1 a
3 or 1 2 2
4 bad 3 p
""")
        result = bitproj.propose_free_map(
            source,
            destination,
            {},
            source_property=source.properties["p"],
            destination_property=destination.properties["p"],
            source_states=source.states,
        )
        self.assertEqual(result[3], [(2, 0), (2, 0)])

    def test_one_source_bit_cannot_force_two_destination_bits(self) -> None:
        source = model("""1 sort bitvec 1
2 state 1 free
3 or 1 2 2
4 bad 3 p
""")
        destination = model(DEST_TWO_FREE_BITS)
        with self.assertRaisesRegex(bitproj.BitProjectionError, "multiple destination"):
            bitproj.propose_free_map(
                source,
                destination,
                {},
                source_property=source.properties["p"],
                destination_property=destination.properties["p"],
                source_states=source.states,
            )

    def test_unused_free_bit_is_a_missing_premise_not_an_arbitrary_guess(self) -> None:
        source = model("""1 sort bitvec 1
2 sort bitvec 2
3 state 2 free
4 slice 1 3 0 0
5 bad 4 p
""")
        destination = model("""1 sort bitvec 1
2 state 1 a
3 bad 2 p
""")
        with self.assertRaisesRegex(bitproj.BitProjectionError, "remain unmapped"):
            bitproj.propose_free_map(
                source,
                destination,
                {},
                source_property=source.properties["p"],
                destination_property=destination.properties["p"],
                source_states=source.states,
            )

    def test_non_free_wrong_mapping_is_rejected(self) -> None:
        source = model("""1 sort bitvec 1
2 input 1 x
3 bad 2 p
""")
        destination = model("""1 sort bitvec 1
2 input 1 y
3 input 1 x
4 bad 3 p
""")
        with self.assertRaisesRegex(bitproj.BitProjectionError, "wrong destination"):
            bitproj.propose_free_map(
                source,
                destination,
                {2: 2},
                source_property=source.properties["p"],
                destination_property=destination.properties["p"],
                source_states=set(),
            )

    def test_concat_wiring_matches_authoritative_model_bits(self) -> None:
        source = model("""1 sort bitvec 1
2 sort bitvec 2
3 state 1 low
4 state 1 high
5 concat 2 4 3
6 slice 1 5 0 0
7 bad 6 p
""")
        table = bitproj._BitTable(source, "S")
        # Model.bits uses args[1] as the low half and args[0] as the high half.
        self.assertEqual(table.expr[table.bit(5, 0)], ("atom", "S", 3, 0))
        self.assertEqual(table.expr[table.bit(5, 1)], ("atom", "S", 4, 0))
        bits = source.bits(bit_atom=lambda n, bit: ("S", n.id, bit))
        self.assertEqual(bits[5][0], btor.digest(("bit", ("S", 3, 0))))
        self.assertEqual(bits[5][1], btor.digest(("bit", ("S", 4, 0))))


if __name__ == "__main__":
    unittest.main()
