"""Propose bit-level free-witness projections between two BTOR models.

A source model can contain free state bits (states with no initial value and
no next-state function).  When the same design is compiled with a helper
monitor, those free bits can be packed differently: a 32-bit source free state
may correspond to 32 separate destination free bits, or two source bits may
share one destination bit.  The whole-state projection checker cannot express
that relation.

This module proposes a per-source-bit map.  The proposal is untrusted: the
composition checker independently verifies the resulting bit projection.  A
proposal is only useful when every source free bit has exactly one destination
free bit and no source bit is forced to equal two different destination bits
(the latter would constrain the destination's freedom).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from . import btor


class BitProjectionError(ValueError):
    pass


@dataclass(frozen=True)
class FreeBit:
    ref: int
    bit: int


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict[object, object] = {}

    def find(self, item: object) -> object:
        parent = self.parent.setdefault(item, item)
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: object, right: object) -> None:
        lroot, rroot = self.find(left), self.find(right)
        if lroot != rroot:
            self.parent[rroot] = lroot


def _free_states(model: btor.Model) -> set[int]:
    return {
        node.id
        for node in model.nodes.values()
        if node.op == "state"
        and model.initial.get(node.id) is None
        and model.next.get(node.id) is None
    }


_COMMUTATIVE_WORD_OPS = {
    "and",
    "or",
    "xor",
    "xnor",
    "nand",
    "nor",
    "eq",
    "neq",
    "add",
    "mul",
    "iff",
}
_REDUCE_WORD_OPS = {"redor", "redand"}


class _BitTable:
    """Normalize a BTOR model to one expression per output bit.

    The structure intentionally mirrors ``btor.Model.bits``: concatenation,
    slices and extensions are wiring and disappear; other word operations stay
    whole and expose all of their operand bits.  Interning keeps the graph
    linear in the number of distinct bit expressions.

    Commutative word operations are canonicalized by a model-independent
    structural key.  This is sound (the operation is unchanged) and keeps the
    projection stable when Yosys emits the same commutative operands in a
    different order in two separately built models.
    """

    def __init__(self, model: btor.Model, side: str):
        self.model = model
        self.side = side
        self.table: dict[tuple, int] = {}
        self.expr: list[tuple] = []
        self.memo: dict[tuple[int, int], int] = {}
        self._key: dict[int, tuple] = {}

    def intern(self, key: tuple) -> int:
        value = self.table.get(key)
        if value is None:
            value = len(self.expr)
            self.table[key] = value
            self.expr.append(key)
        return value

    def bit(self, ref: int, bit: int) -> int:
        key = (ref, bit)
        if key in self.memo:
            return self.memo[key]
        node = self.model.nodes[abs(ref)]
        if ref < 0:
            child = self.bit(-ref, bit)
            child_expr = self.expr[child]
            if child_expr[0] == "const":
                value = self.intern(("const", 1 - child_expr[1]))
            else:
                value = self.intern(("not_bit", child))
        elif node.op in {"state", "input"}:
            value = self.intern(("atom", self.side, ref, bit))
        elif node.op == "const":
            value = self.intern(("const", (node.params[0] >> bit) & 1))
        elif node.op == "concat":
            # ``Model.bits`` puts args[1] at the low end and args[0] at the
            # high end, matching BTOR's concatenation convention.
            low_width = self.model.nodes[abs(node.args[1])].width
            if bit < low_width:
                value = self.bit(node.args[1], bit)
            else:
                value = self.bit(node.args[0], bit - low_width)
        elif node.op == "slice":
            value = self.bit(node.args[0], bit + node.params[1])
        elif node.op in {"uext", "sext"}:
            width = self.model.nodes[abs(node.args[0])].width
            if bit < width:
                value = self.bit(node.args[0], bit)
            elif node.op == "uext":
                value = self.intern(("const", 0))
            else:
                value = self.bit(node.args[0], width - 1)
        else:
            args = tuple(
                tuple(self.bit(arg, index) for index in range(self.model.nodes[abs(arg)].width))
                for arg in node.args
            )
            if node.op in _REDUCE_WORD_OPS and len(args) == 1:
                args = (tuple(sorted(args[0], key=self.bit_key)),)
            elif node.op in _COMMUTATIVE_WORD_OPS and len(args) > 1:
                args = tuple(
                    sorted(
                        args,
                        key=lambda bits: tuple(self.bit_key(child) for child in bits),
                    )
                )
            word = self.intern(("word", node.op, node.width, node.params, args))
            value = self.intern(("bit", word, bit))
        self.memo[key] = value
        return value

    def bit_key(self, ref: int) -> tuple:
        """A structural key for a normalized bit expression.

        Atom node numbers are deliberately omitted from the primary key so two
        separately numbered models can canonicalize the same expression into
        the same operand order.  The symbol/op/width identify named atoms; an
        anonymous atom falls back to its local reference as a tie-breaker.
        """
        cached = self._key.get(ref)
        if cached is not None:
            return cached
        node = self.expr[ref]
        kind = node[0]
        if kind == "atom":
            _, _side, atom, bit = node
            atom_node = self.model.nodes[atom]
            key = (
                "atom",
                atom_node.op,
                atom_node.width,
                atom_node.symbol or "",
                atom if not atom_node.symbol else 0,
                bit,
            )
        elif kind == "const":
            key = ("const", node[1])
        elif kind == "not_bit":
            key = ("not_bit", self.bit_key(node[1]))
        elif kind == "word":
            _, op, width, params, args = node
            arg_keys = tuple(tuple(self.bit_key(child) for child in arg) for arg in args)
            if op in _REDUCE_WORD_OPS and len(arg_keys) == 1:
                arg_keys = (tuple(sorted(arg_keys[0])),)
            elif op in _COMMUTATIVE_WORD_OPS and len(arg_keys) > 1:
                arg_keys = tuple(sorted(arg_keys))
            key = ("word", op, width, params, arg_keys)
        elif kind == "bit":
            key = ("bit", self.bit_key(node[1]), node[2])
        else:
            key = node
        self._key[ref] = key
        return key


def _unify(
    source: _BitTable,
    destination: _BitTable,
    source_free: set[int],
    destination_free: set[int],
    mapping: dict[int, int],
    uf: _UnionFind,
    source_expr: int,
    destination_expr: int,
) -> None:
    pending = [(source_expr, destination_expr)]
    seen: set[tuple[int, int]] = set()
    while pending:
        sref, dref = pending.pop()
        if (sref, dref) in seen:
            continue
        seen.add((sref, dref))
        snode, dnode = source.expr[sref], destination.expr[dref]
        if snode[0] == "atom" or dnode[0] == "atom":
            if snode[0] != "atom" or dnode[0] != "atom":
                raise BitProjectionError("an atom is matched to an expression")
            _, _, source_atom, source_bit = snode
            _, _, destination_atom, destination_bit = dnode
            source_is_free = source_atom in source_free
            destination_is_free = destination_atom in destination_free
            if source_is_free and destination_is_free:
                uf.union(
                    ("source", source_atom, source_bit),
                    ("destination", destination_atom, destination_bit),
                )
            elif source_is_free or destination_is_free:
                raise BitProjectionError(
                    f"free/non-free atom mismatch: {source_atom}:{source_bit} vs "
                    f"{destination_atom}:{destination_bit}"
                )
            elif mapping.get(source_atom) != destination_atom:
                raise BitProjectionError(
                    f"non-free source atom {source_atom} maps to the wrong destination atom"
                )
            continue
        if snode[0] != dnode[0]:
            raise BitProjectionError("normalized expression kinds differ")
        if snode[0] == "const":
            if snode[1] != dnode[1]:
                raise BitProjectionError(
                    f"constant bits differ: {snode[1]} vs {dnode[1]} "
                    f"(expressions {sref} and {dref})"
                )
            continue
        if snode[0] == "not_bit":
            pending.append((snode[1], dnode[1]))
            continue
        if snode[0] == "word":
            if snode[1:4] != dnode[1:4]:
                raise BitProjectionError("word operation shapes differ")
            if len(snode[4]) != len(dnode[4]):
                raise BitProjectionError("word operation arity differs")
            for left, right in zip(snode[4], dnode[4]):
                if len(left) != len(right):
                    raise BitProjectionError("word operation operand widths differ")
                pending.extend(zip(left, right))
            continue
        if snode[0] == "bit":
            if snode[2] != dnode[2]:
                raise BitProjectionError("word bit indices differ")
            pending.append((snode[1], dnode[1]))
            continue
        raise BitProjectionError("unknown normalized expression")


def propose_free_map(
    source: btor.Model,
    destination: btor.Model,
    mapping: dict[int, int],
    *,
    source_property: int,
    destination_property: int,
    source_states: Iterable[int],
    max_steps: int = 2_000_000,
) -> dict[int, list[tuple[int, int]]]:
    """Propose a map from each source free bit to one destination free bit.

    ``mapping`` maps non-free source state/input atoms to destination atoms.
    The returned map has one entry for every source free state that appears in
    the checked cone.  A conflict means the source model shares a free value
    where the destination model has independent free values; no sound
    deterministic relation exists, so checking must fail closed.
    """
    source_free = _free_states(source)
    destination_free = _free_states(destination)
    source_states = set(source_states)
    source_table = _BitTable(source, "S")
    destination_table = _BitTable(destination, "D")
    uf = _UnionFind()
    work = 0

    def unify(source_expr: int, destination_expr: int) -> None:
        nonlocal work
        work += 1
        if work > max_steps:
            raise BitProjectionError("bit projection unification exceeded its work limit")
        _unify(
            source_table,
            destination_table,
            source_free,
            destination_free,
            mapping,
            uf,
            source_expr,
            destination_expr,
        )

    unify(source_table.bit(source_property, 0), destination_table.bit(destination_property, 0))
    for state in sorted(source_states):
        if state in source_free:
            continue
        dest_state = mapping.get(state)
        if dest_state is None:
            raise BitProjectionError(f"source state {state} has no destination mapping")
        if source.nodes[state].width != destination.nodes[dest_state].width:
            raise BitProjectionError(f"source state {state} maps to a different width")
        source_initial = source.initial.get(state)
        destination_initial = destination.initial.get(dest_state)
        if source_initial is not None:
            if destination_initial is None:
                raise BitProjectionError(f"destination omits initial state {state}")
            for bit in range(source.nodes[state].width):
                unify(source_table.bit(source_initial, bit), destination_table.bit(destination_initial, bit))
        source_next = source.next.get(state)
        destination_next = destination.next.get(dest_state)
        if (source_next is None) != (destination_next is None):
            raise BitProjectionError(f"transition presence differs for state {state}")
        if source_next is not None:
            for bit in range(source.nodes[state].width):
                unify(source_table.bit(source_next, bit), destination_table.bit(destination_next, bit))

    components: dict[object, dict[str, set[tuple[int, int]]]] = defaultdict(
        lambda: {"source": set(), "destination": set()}
    )
    for item in uf.parent:
        kind, ref, bit = item  # type: ignore[misc]
        components[uf.find(item)][kind].add((ref, bit))

    free_map: dict[int, list[tuple[int, int] | None]] = {
        ref: [None] * source.nodes[ref].width for ref in source_free if ref in source_states
    }
    for component in components.values():
        sources = component["source"]
        destinations = component["destination"]
        if len(destinations) > 1:
            raise BitProjectionError(
                "one source free bit is forced to equal multiple destination free bits"
            )
        if not sources or not destinations:
            continue
        destination_bit = next(iter(destinations))
        for ref, bit in sources:
            if ref not in free_map:
                continue
            if free_map[ref][bit] is not None:
                raise BitProjectionError("a source free bit has two proposed destinations")
            free_map[ref][bit] = destination_bit

    missing = [
        (ref, bit)
        for ref, bits in free_map.items()
        for bit, value in enumerate(bits)
        if value is None
    ]
    if missing:
        raise BitProjectionError(f"source free bits remain unmapped: {missing[:8]}")

    return {ref: [value for value in bits if value is not None] for ref, bits in free_map.items()}
