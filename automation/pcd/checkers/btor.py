"""Conservative BTOR2 reader for structural composition certificates.

Only single-clock, bit-vector safety models are supported. Unsupported syntax
is an error, never an uninterpreted operator. Numeric node IDs are local to a
file; fingerprints preserve operators, widths, constants and operand order.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class BtorError(ValueError):
    pass


UNARY = {"not", "neg", "inc", "dec", "redand", "redor", "redxor"}
BINARY = {
    "and", "or", "xor", "xnor", "nand", "nor", "add", "sub", "mul",
    "udiv", "sdiv", "urem", "srem", "smod", "sll", "srl", "sra",
    "rol", "ror", "eq", "neq", "ult", "ulte", "ugt", "ugte",
    "slt", "slte", "sgt", "sgte", "concat", "implies", "iff",
    "uaddo", "saddo", "usubo", "ssubo", "umulo", "smulo", "sdivo",
}
PREDICATES = {
    "eq", "neq", "ult", "ulte", "ugt", "ugte", "slt", "slte", "sgt",
    "sgte", "implies", "iff", "uaddo", "saddo", "usubo", "ssubo",
    "umulo", "smulo", "sdivo",
}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Node:
    id: int
    op: str
    width: int
    args: tuple[int, ...] = ()
    params: tuple[int, ...] = ()
    symbol: str | None = None


class Model:
    def __init__(self, path: str | Path, *, text: str | None = None):
        self.path = Path(path)
        self.nodes: dict[int, Node] = {}
        self.sorts: dict[int, int] = {}
        self.states: list[int] = []
        self.inputs: list[int] = []
        self.initial: dict[int, int] = {}
        self.next: dict[int, int] = {}
        self.properties: dict[str, int] = {}
        self.outputs: dict[str, int] = {}
        self.constraints: list[int] = []
        previous = 0
        contents = self.path.read_text(encoding="utf-8") if text is None else text
        for lineno, raw in enumerate(contents.splitlines(), 1):
            tokens = raw.split(";", 1)[0].split()
            if not tokens:
                continue
            try:
                nid = int(tokens[0])
                if nid <= previous:
                    raise BtorError("IDs must be positive and strictly increasing")
                previous = nid
                self._line(nid, tokens[1:])
            except (ValueError, KeyError, IndexError) as exc:
                raise BtorError(f"{self.path.name}:{lineno}: {exc}") from exc
        if not self.nodes:
            raise BtorError("empty BTOR model")

    def _ref(self, token: str) -> int:
        ref = int(token)
        if abs(ref) not in self.nodes:
            raise BtorError(f"unknown or forward node reference {ref}")
        return ref

    def width(self, ref: int) -> int:
        return self.nodes[abs(ref)].width

    def _line(self, nid: int, t: list[str]) -> None:
        op = t[0]
        if op == "sort":
            if len(t) != 3 or t[1] != "bitvec":
                raise BtorError("only bit-vector sorts are supported")
            width = int(t[2])
            if not 1 <= width <= 4096:
                raise BtorError("unsupported bit-vector width")
            self.sorts[nid] = width
            return
        if op in {"bad", "constraint"}:
            if len(t) not in {2, 3}:
                raise BtorError(f"bad {op} syntax")
            ref = self._ref(t[1])
            if self.width(ref) != 1:
                raise BtorError(f"{op} must be one bit")
            if op == "constraint":
                self.constraints.append(ref)
            else:
                if len(t) != 3 or t[2] in self.properties:
                    raise BtorError("properties must have unique explicit names")
                self.properties[t[2]] = ref
            return
        if op in {"output"}:
            if len(t) not in {2, 3}:
                raise BtorError("bad output syntax")
            ref = self._ref(t[1])
            if len(t) == 3:
                if t[2] in self.outputs:
                    raise BtorError("duplicate output symbol")
                self.outputs[t[2]] = ref
            return
        if op in {"fair", "justice"}:
            raise BtorError("liveness models are unsupported")
        width = self.sorts[int(t[1])]
        if op in {"state", "input"}:
            if len(t) not in {2, 3}:
                raise BtorError(f"bad {op} syntax")
            self.nodes[nid] = Node(nid, op, width, symbol=t[2] if len(t) == 3 else None)
            (self.states if op == "state" else self.inputs).append(nid)
            return
        if op in {"init", "next"}:
            if len(t) not in {4, 5}:
                raise BtorError(f"bad {op} syntax")
            state, value = self._ref(t[2]), self._ref(t[3])
            if state < 0 or self.nodes[state].op != "state":
                raise BtorError(f"{op} destination is not a state")
            if self.width(state) != width or self.width(value) != width:
                raise BtorError(f"{op} width mismatch")
            table = self.initial if op == "init" else self.next
            if state in table:
                raise BtorError(f"duplicate {op} for state {state}")
            table[state] = value
            return
        if op in {"const", "constd", "consth", "zero", "one", "ones"}:
            if len(t) != (2 if op in {"zero", "one", "ones"} else 3):
                raise BtorError("bad constant syntax")
            if op == "const" and (len(t[2]) != width or set(t[2]) - {"0", "1"}):
                raise BtorError("binary constant has the wrong width")
            value = {"zero": 0, "one": 1, "ones": (1 << width) - 1}.get(op)
            if value is None:
                value = int(t[2], {"const": 2, "constd": 10, "consth": 16}[op])
                if not -(1 << width) < value < (1 << width):
                    raise BtorError("constant does not fit its bit-vector width")
                value %= 1 << width
            self.nodes[nid] = Node(nid, "const", width, params=(value,))
            return
        count = 1 if op in UNARY or op in {"slice", "uext", "sext"} else 2 if op in BINARY else 3 if op == "ite" else None
        if count is None:
            raise BtorError(f"unsupported BTOR operator {op!r}")
        params_count = 2 if op == "slice" else 1 if op in {"uext", "sext"} else 0
        arity = 2 + count + params_count
        if len(t) not in {arity, arity + 1}:
            raise BtorError(f"bad {op} arity")
        args = tuple(self._ref(x) for x in t[2:2 + count])
        params = tuple(int(x) for x in t[2 + count:arity])
        widths = [self.width(x) for x in args]
        if op == "slice":
            hi, lo = params
            valid = 0 <= lo <= hi < widths[0] and width == hi - lo + 1
        elif op in {"uext", "sext"}:
            valid = params[0] >= 0 and width == widths[0] + params[0]
        elif op == "concat":
            valid = width == sum(widths)
        elif op == "ite":
            valid = widths[0] == 1 and widths[1] == widths[2] == width
        elif op.startswith("red"):
            valid = width == 1
        elif op in PREDICATES:
            valid = width == 1 and widths[0] == widths[1]
            if op in {"implies", "iff"}:
                valid = valid and widths[0] == 1
        else:
            valid = all(w == width for w in widths)
        if not valid:
            raise BtorError(f"{op} sort/width mismatch")
        self.nodes[nid] = Node(nid, op, width, args, params, t[arity] if len(t) > arity else None)

    def fingerprint(self, ref: int, atom: Callable[[Node], object], cache: dict[int, str] | None = None) -> str:
        memo = cache if cache is not None else {}
        # BTOR terms are topologically ordered. Iteration avoids recursion limits
        # on real synthesized cones (e.g. register-file muxes).
        pending = [ref]
        while pending:
            cur = pending[-1]
            if cur in memo:
                pending.pop()
                continue
            node = self.nodes[abs(cur)]
            if cur < 0:
                deps = [abs(cur)]
            else:
                deps = list(node.args)
            missing = [x for x in deps if x not in memo]
            if missing:
                pending.extend(missing)
                continue
            if cur < 0:
                value = ("not", node.width, memo[-cur])
            elif node.op in {"state", "input"}:
                value = (node.op, node.width, atom(node))
            else:
                value = (node.op, node.width, node.params, [memo[x] for x in node.args])
            memo[cur] = digest(value)
            pending.pop()
        return memo[ref]

    def find(self, symbol: str) -> int:
        """Resolve a proposed observation name; verification still uses IDs/hashes."""
        matches = {node.id for node in self.nodes.values() if node.symbol == symbol}
        if symbol in self.outputs:
            matches.add(self.outputs[symbol])
        if len(matches) != 1:
            raise BtorError(f"observation {symbol!r} is missing or ambiguous")
        return matches.pop()

    def bits(self, atom: Callable[[Node], object] | None = None, *,
             bit_atom: Callable[[Node, int], object] | None = None) -> dict[int, tuple[str, ...]]:
        """Canonicalize wiring without changing bit-vector arithmetic semantics.

        Bit order is least-significant first. Flattening concatenation, slices,
        and extensions makes this insensitive to frontend packing choices.
        Other word operations retain their operator and exact operand widths.

        By default ``atom`` names a whole state/input atom.  Supplying
        ``bit_atom`` instead names each state/input bit independently, which is
        needed when an atom is related to differently packed destination bits.
        """
        if (atom is None) == (bit_atom is None):
            raise BtorError("bits needs exactly one of atom or bit_atom")
        result: dict[int, tuple[str, ...]] = {}
        for nid, node in self.nodes.items():
            def value(ref: int) -> tuple[str, ...]:
                if ref not in result:
                    result[ref] = tuple(digest(("not", b)) if b not in {"0", "1"} else str(1 - int(b)) for b in result[-ref])
                return result[ref]
            args = [value(a) for a in node.args]
            if node.op in {"state", "input"}:
                if bit_atom is not None:
                    out = tuple(digest(("bit", bit_atom(node, i))) for i in range(node.width))
                else:
                    out = tuple(digest((node.op, node.width, atom(node), i)) for i in range(node.width))
            elif node.op == "const":
                out = tuple(str((node.params[0] >> i) & 1) for i in range(node.width))
            elif node.op == "concat":
                out = args[1] + args[0]
            elif node.op == "slice":
                hi, lo = node.params
                out = args[0][lo:hi + 1]
            elif node.op in {"uext", "sext"}:
                fill = "0" if node.op == "uext" else args[0][-1]
                out = args[0] + (fill,) * node.params[0]
            else:
                # Canonicalize commutative operators.  Two separately built
                # models can list the same operands in a different order; the
                # operations are still the same expression.
                if node.op in {"redor", "redand"} and len(args) == 1:
                    args = [tuple(sorted(args[0]))]
                elif node.op in {
                    "and", "or", "xor", "xnor", "nand", "nor",
                    "eq", "neq", "add", "mul", "iff",
                } and len(args) > 1:
                    args = sorted(args)
                word = digest((node.op, node.width, node.params, args))
                out = tuple(digest((word, i)) for i in range(node.width))
            result[nid] = out
        for ref in [*self.initial.values(), *self.next.values(), *self.constraints, *self.properties.values()]:
            value(ref)
        return result

    def cone(self, roots: list[int]) -> tuple[set[int], set[int]]:
        """State/input closure through both combinational terms and state updates."""
        seen: set[int] = set()
        states: set[int] = set()
        inputs: set[int] = set()
        pending = list(roots)
        while pending:
            ref = abs(pending.pop())
            if ref in seen:
                continue
            seen.add(ref)
            node = self.nodes[ref]
            pending.extend(node.args)
            if node.op == "state":
                states.add(ref)
                pending.extend(v for table in (self.initial, self.next) if (v := table.get(ref)) is not None)
            elif node.op == "input":
                inputs.add(ref)
        return states, inputs


def _structural_mapping(source: Model, destination: Model) -> dict[int, int]:
    """Align corresponding expression DAGs, starting from shared property names.

    This is only a proposal.  The independent composition checker decides
    whether every transition, constraint and observation really corresponds.
    """
    mapping: dict[int, int] = {}
    used: dict[int, int] = {}

    def map_atom(a: int, b: int) -> bool:
        if a in mapping:
            return mapping[a] == b
        if b in used:
            return False
        mapping[a] = b
        used[b] = a
        return True

    # Exact unique names are the strongest available anchors.  Frontend witness
    # numbering is not semantic, so those names are intentionally not anchors.
    for op in ("state", "input"):
        source_by_key: dict[tuple[int, str | None], list[int]] = {}
        destination_by_key: dict[tuple[int, str | None], list[int]] = {}
        for atom in getattr(source, op + "s"):
            node = source.nodes[atom]
            source_by_key.setdefault((node.width, node.symbol), []).append(atom)
        for atom in getattr(destination, op + "s"):
            node = destination.nodes[atom]
            destination_by_key.setdefault((node.width, node.symbol), []).append(atom)
        for key, atoms in source_by_key.items():
            symbol = key[1]
            if not symbol or symbol.startswith("_witness_."):
                continue
            matches = destination_by_key.get(key, [])
            if len(atoms) == 1 and len(matches) == 1:
                map_atom(atoms[0], matches[0])

    # Properties with the same name are the roots of the transfer.  When no
    # names are shared, named state anchors still give the traversal somewhere
    # to start.
    stack: list[tuple[int, int]] = [
        (ref, destination.properties[name])
        for name, ref in source.properties.items()
        if name in destination.properties
    ]
    for a, b in list(mapping.items()):
        for source_table, destination_table in (
            (source.initial, destination.initial),
            (source.next, destination.next),
        ):
            x, y = source_table.get(a), destination_table.get(b)
            if x is not None and y is not None:
                stack.append((x, y))

    seen: set[tuple[int, int]] = set()
    while stack:
        a, b = stack.pop()
        if a < 0 or b < 0:
            if (a < 0) != (b < 0):
                continue
            stack.append((-a, -b))
            continue
        if (a, b) in seen:
            continue
        seen.add((a, b))
        left, right = source.nodes[a], destination.nodes[b]
        if left.op in {"state", "input"} or right.op in {"state", "input"}:
            if left.op != right.op or left.width != right.width:
                continue
            if a in mapping:
                if mapping[a] != b:
                    continue
            elif b in used:
                continue
            else:
                mapping[a] = b
                used[b] = a
                for source_table, destination_table in (
                    (source.initial, destination.initial),
                    (source.next, destination.next),
                ):
                    x, y = source_table.get(a), destination_table.get(b)
                    if (x is None) != (y is None):
                        continue
                    if x is not None:
                        stack.append((x, y))
            continue
        if (
            left.op != right.op
            or left.width != right.width
            or left.params != right.params
            or len(left.args) != len(right.args)
        ):
            continue
        stack.extend(zip(left.args, right.args))

    # Fill remaining atoms in the observation/constraint cone.  A local-ID
    # match is a useful hint when both frontends emitted the same anonymous
    # state.  Otherwise use an unused free destination atom of the same width;
    # the checker will reject the proposal if the guess is not exact.
    roots = [source.properties[name] for name in source.properties if name in destination.properties]
    roots.extend(source.constraints)
    states, inputs = source.cone(roots)
    for atom in sorted((states | inputs) - mapping.keys()):
        node = source.nodes[atom]
        candidates = destination.states if node.op == "state" else destination.inputs
        if (
            atom in destination.nodes
            and destination.nodes[atom].op == node.op
            and destination.nodes[atom].width == node.width
            and atom not in used
        ):
            mapping[atom] = atom
            used[atom] = atom
            continue
        options = [
            candidate
            for candidate in candidates
            if candidate not in used
            and destination.nodes[candidate].width == node.width
            and candidate not in destination.initial
            and candidate not in destination.next
        ]
        if not options:
            options = [
                candidate
                for candidate in candidates
                if destination.nodes[candidate].width == node.width
                and candidate not in destination.initial
                and candidate not in destination.next
            ]
        if options:
            candidate = min(options)
            mapping[atom] = candidate
            used[candidate] = atom
    return mapping


def _color_mapping(source: Model, destination: Model) -> dict[int, int]:
    """Fallback refinement for models without named/root anchors."""
    models = [source, destination]
    keys = [(i, n) for i, model in enumerate(models) for n in model.states + model.inputs]
    labels = {}
    for key in keys:
        node = models[key[0]].nodes[key[1]]
        symbol = node.symbol
        if symbol and symbol.startswith("_witness_."):
            symbol = None  # frontend-generated numbering is not semantic identity
        labels[key] = (node.op, node.width, symbol)

    def classify(values: dict) -> dict:
        unique = {value: i for i, value in enumerate(sorted(set(values.values()), key=repr))}
        return {key: unique[value] for key, value in values.items()}

    colors = classify(labels)
    for _ in range(len(keys) + 1):
        values = {}
        for i, model in enumerate(models):
            atom = lambda node, i=i: colors[(i, node.id)]
            normalized = model.bits(atom)
            for n in model.states + model.inputs:
                if labels[(i, n)][2] is not None:
                    values[(i, n)] = ("named", labels[(i, n)])
                else:
                    values[(i, n)] = (
                        "anonymous", colors[(i, n)],
                        normalized[model.initial[n]] if n in model.initial else None,
                        normalized[model.next[n]] if n in model.next else None,
                    )
        refined = classify(values)
        if len(set(refined.values())) == len(set(colors.values())):
            colors = refined
            break
        colors = refined
    choices: dict[int, list[int]] = {}
    for n in destination.states + destination.inputs:
        choices.setdefault(colors[(1, n)], []).append(n)
    return {
        n: choices[colors[(0, n)]][0]
        for n in source.states + source.inputs
        if colors[(0, n)] in choices
    }


def propose_mapping(source: Model, destination: Model) -> dict[str, str]:
    """Propose atom correspondences by name and structural expression alignment.

    This is a heuristic. All returned correspondences must pass the independent
    composition check, so ambiguous or unsuccessful guesses cannot close a proof.
    """
    if all(destination.nodes.get(nid) == node for nid, node in source.nodes.items()):
        return {str(n): str(n) for n in source.states + source.inputs}
    mapping = _structural_mapping(source, destination)

    # Keep the old colour-refinement fallback for atoms the structural pass
    # could not place.  It is only an untrusted proposal; the checker still
    # decides whether the resulting correspondence is valid.
    roots = [source.properties[name] for name in source.properties if name in destination.properties]
    roots.extend(source.constraints)
    missing: set[int] = set()
    if roots:
        states, inputs = source.cone(roots)
        missing = (states | inputs) - mapping.keys()
    if not mapping or missing:
        for atom, target in _color_mapping(source, destination).items():
            mapping.setdefault(atom, target)
    return {str(n): str(d) for n, d in mapping.items()}
