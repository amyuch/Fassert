"""Typed formulas and exact bit-vector semantics shared by model-bound checks.

All variables come from a frozen BTOR node at frame 0 or 1. There are no free
planner variables, implicit signed conversions, or supplied transition systems.
Unsupported operators and ill-typed terms are rejected.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import z3

from .btor import Model


class SemanticError(ValueError):
    pass


@dataclass(frozen=True)
class Term:
    value: Any
    sort: str
    frames: frozenset[int] = frozenset()
    unsigned_bv: Any = None


def _bvbool(value):
    return z3.If(value, z3.BitVecVal(1, 1), z3.BitVecVal(0, 1))


def unsigned_value(value):
    """Exact unsigned interpretation with a checked-in bitwise identity.

    U(x|y) = U(x)+U(y)-U(x&y), independently at every bit. Keeping the overlap
    term is essential: disjointness is a separate proved premise, never assumed.
    This avoids asking the solver to rediscover a 32-bit mixed-theory identity.
    """
    if z3.is_bv_value(value):
        return z3.IntVal(value.as_long())
    if value.decl().kind() == z3.Z3_OP_BOR and value.num_args() == 2:
        left, right = value.children()
        return unsigned_value(left) + unsigned_value(right) - z3.BV2Int(left & right)
    if value.decl().kind() == z3.Z3_OP_ITE:
        condition, yes, no = value.children()
        return z3.If(condition, unsigned_value(yes), unsigned_value(no))
    if value.decl().kind() == z3.Z3_OP_ZERO_EXT:
        return unsigned_value(value.arg(0))
    if value.decl().kind() == z3.Z3_OP_EXTRACT:
        hi, lo = value.params()
        return (unsigned_value(value.arg(0)) / (1 << lo)) % (1 << (hi - lo + 1))
    if value.decl().kind() in {z3.Z3_OP_BADD, z3.Z3_OP_BSUB} and value.num_args() == 2:
        left, right = [unsigned_value(arg) for arg in value.children()]
        total = left + right if value.decl().kind() == z3.Z3_OP_BADD else left - right
        return total % (1 << value.size())
    return z3.BV2Int(value)


class Context:
    """Actual initial/transition/constraint semantics of one frozen model."""

    def __init__(self, model: Model, model_id: str, *, atoms=None, inline_next: bool = False):
        self.model = model
        self.model_id = model_id
        self.cache: dict[tuple[int, int], Any] = {}
        self.atoms = atoms
        self.inline_next = inline_next

    def ref(self, ref: int, frame: int = 0):
        if type(ref) is not int or abs(ref) not in self.model.nodes or frame not in {0, 1}:
            raise SemanticError("invalid frozen model reference or frame")
        pending = [ref]
        while pending:
            cur = pending[-1]
            if (cur, frame) in self.cache:
                pending.pop()
                continue
            node = self.model.nodes[abs(cur)]
            deps = [abs(cur)] if cur < 0 else list(node.args)
            missing = [arg for arg in deps if (arg, frame) not in self.cache]
            if missing:
                pending.extend(missing)
                continue
            args = [self.cache[(arg, frame)] for arg in node.args]
            if cur < 0:
                value = ~self.cache[(-cur, frame)]
            elif node.op in {"state", "input"}:
                if self.inline_next and frame == 1 and node.op == "state" and cur in self.model.next:
                    value = self.ref(self.model.next[cur], 0)
                else:
                    value = self.atoms(node, frame) if self.atoms else z3.BitVec(f"{self.model_id}:{frame}:{cur}", node.width)
            elif node.op == "const":
                value = z3.BitVecVal(node.params[0], node.width)
            else:
                value = self._operator(node.op, args, node.width, node.params)
            self.cache[(cur, frame)] = value
            pending.pop()
        return self.cache[(ref, frame)]

    @staticmethod
    def _operator(op: str, a: list, width: int, params: tuple[int, ...]):
        unary = {"not": lambda x: ~x, "neg": lambda x: -x,
                 "inc": lambda x: x + 1, "dec": lambda x: x - 1}
        binary = {
            "and": lambda x, y: x & y, "or": lambda x, y: x | y,
            "xor": lambda x, y: x ^ y, "xnor": lambda x, y: ~(x ^ y),
            "nand": lambda x, y: ~(x & y), "nor": lambda x, y: ~(x | y),
            "add": lambda x, y: x + y, "sub": lambda x, y: x - y,
            "mul": lambda x, y: x * y, "udiv": z3.UDiv, "urem": z3.URem,
            "sdiv": lambda x, y: x / y, "srem": z3.SRem, "smod": lambda x, y: x % y,
            "sll": lambda x, y: x << y, "srl": z3.LShR, "sra": lambda x, y: x >> y,
            "rol": z3.RotateLeft, "ror": z3.RotateRight,
            "concat": z3.Concat,
        }
        comparisons = {
            "eq": lambda x, y: x == y, "neq": lambda x, y: x != y,
            "ult": z3.ULT, "ulte": z3.ULE, "ugt": z3.UGT, "ugte": z3.UGE,
            "slt": lambda x, y: x < y, "slte": lambda x, y: x <= y,
            "sgt": lambda x, y: x > y, "sgte": lambda x, y: x >= y,
            "implies": lambda x, y: z3.Implies(x == 1, y == 1),
            "iff": lambda x, y: (x == 1) == (y == 1),
        }
        if op in unary:
            return unary[op](*a)
        if op in binary:
            return binary[op](*a)
        if op in comparisons:
            return _bvbool(comparisons[op](*a))
        if op == "ite":
            return z3.If(a[0] == 1, a[1], a[2])
        if op == "slice":
            return z3.Extract(params[0], params[1], a[0])
        if op in {"uext", "sext"}:
            return (z3.ZeroExt if op == "uext" else z3.SignExt)(params[0], a[0])
        if op == "redand":
            return _bvbool(a[0] == (1 << a[0].size()) - 1)
        if op == "redor":
            return _bvbool(a[0] != 0)
        if op == "redxor":
            bits = [z3.Extract(i, i, a[0]) for i in range(a[0].size())]
            value = bits[0]
            for bit in bits[1:]:
                value = value ^ bit
            return value
        if op in {"uaddo", "saddo", "usubo", "ssubo", "umulo", "smulo", "sdivo"}:
            x, y = a
            n = x.size()
            if op == "usubo":
                condition = z3.ULT(x, y)
            elif op == "sdivo":
                condition = z3.And(x == 1 << (n - 1), y == (1 << n) - 1)
            else:
                signed = op.startswith("s")
                ext = z3.SignExt if signed else z3.ZeroExt
                extra = n if "mul" in op else 1
                xx, yy = ext(extra, x), ext(extra, y)
                full = xx * yy if "mul" in op else xx + yy if "add" in op else xx - yy
                low = z3.Extract(n - 1, 0, full)
                condition = full != ext(extra, low)
            return _bvbool(condition)
        raise SemanticError(f"unsupported semantic operator {op!r}")

    def constraints(self, frame: int = 0):
        return [self.ref(ref, frame) == 1 for ref in self.model.constraints]

    def initial(self):
        return [self.ref(state) == self.ref(value) for state, value in self.model.initial.items()]

    def transition(self):
        # Frame 1 is the post-state.  ``value`` is the transition expression in
        # the current state, so it must be read at frame 0 even when frame-1
        # state references are inlined as next functions.  Reading both sides
        # at frame 1 would compare next(value) with next(state) and silently
        # drop constraints such as ``x' = x + 1``.
        # Missing next-state assignments are left unconstrained, a conservative
        # interpretation even for a frontend that might hold such state.
        return [self.ref(state, 1) == self.ref(value) for state, value in self.model.next.items()]

    def lower(self, ast: dict, frame: int = 0) -> Term:
        count = [0]
        def visit(node, depth=0):
            count[0] += 1
            if depth > 64 or count[0] > 20000 or not isinstance(node, dict) or not isinstance(node.get("op"), str):
                raise SemanticError("invalid or excessive typed expression")
            op = node["op"]
            if op == "ref":
                if set(node) - {"op", "id", "frame"} or "id" not in node:
                    raise SemanticError("ref needs exactly a model node ID and optional frame")
                offset = node.get("frame", 0)
                if type(offset) is not int or offset not in {0, 1} or frame + offset not in {0, 1}:
                    raise SemanticError("only current/next sampling is supported")
                ref = node["id"]
                value = self.ref(ref, frame + offset)
                return Term(value, f"BV{value.size()}", frozenset({frame + offset}))
            if op in {"bv", "int", "bool"}:
                keys = {"op", "value", "width"} if op == "bv" else {"op", "value"}
                if set(node) != keys:
                    raise SemanticError("invalid typed constant")
                value = node["value"]
                if op == "bool":
                    if type(value) is not bool:
                        raise SemanticError("Bool constants require a Boolean value")
                    return Term(z3.BoolVal(value), "Bool")
                if not isinstance(value, (str, int)) or isinstance(value, bool) or len(str(value)) > 1300:
                    raise SemanticError("numeric constants require bounded decimal integers")
                try:
                    number = int(value)
                except ValueError as exc:
                    raise SemanticError("invalid integer literal") from exc
                if str(number) != str(value):
                    raise SemanticError("numeric literals must be canonical decimal integers")
                if op == "int":
                    return Term(z3.IntVal(number), "Int")
                width = node["width"]
                if type(width) is not int or not 1 <= width <= 4096 or not -(1 << width) < number < 1 << width:
                    raise SemanticError("bit-vector constant width/range mismatch")
                return Term(z3.BitVecVal(number, width), f"BV{width}")
            extra = {"hi", "lo"} if op == "extract" else {"amount"} if op in {"zext", "sext"} else set()
            if set(node) != {"op", "args"} | extra or not isinstance(node.get("args"), list):
                raise SemanticError(f"invalid fields for typed operator {op}")
            args = [visit(arg, depth + 1) for arg in node["args"]]
            frames = frozenset().union(*(arg.frames for arg in args))
            sorts, values = [arg.sort for arg in args], [arg.value for arg in args]
            arities = {"not": 1, "truth": 1, "uint": 1, "sint": 1, "bvnot": 1,
                       "extract": 1, "zext": 1, "sext": 1, "ite": 3}
            if op not in {"and", "or"} and len(args) != arities.get(op, 2):
                raise SemanticError(f"wrong arity for {op}")
            if op in {"not", "and", "or", "implies"}:
                if any(sort != "Bool" for sort in sorts):
                    raise SemanticError("logical operations require Bool operands")
                fn = {"not": z3.Not, "and": z3.And, "or": z3.Or, "implies": z3.Implies}[op]
                return Term(fn(*values), "Bool", frames)
            if op == "truth":
                if sorts != ["BV1"]:
                    raise SemanticError("truth requires exactly one bit")
                return Term(values[0] == 1, "Bool", frames)
            if op in {"uint", "sint"}:
                if not sorts[0].startswith("BV"):
                    raise SemanticError("integer lifting requires an explicit bit-vector operand")
                value = unsigned_value(values[0]) if op == "uint" else z3.BV2Int(values[0], is_signed=True)
                return Term(value, "Int", frames, values[0] if op == "uint" else None)
            if op == "eq":
                if sorts[0] != sorts[1]:
                    raise SemanticError("equality operands must have identical sorts")
                if all(arg.unsigned_bv is not None for arg in args):
                    x, y = [arg.unsigned_bv for arg in args]
                    width = max(x.size(), y.size())
                    return Term(z3.ZeroExt(width-x.size(), x) == z3.ZeroExt(width-y.size(), y), "Bool", frames)
                return Term(values[0] == values[1], "Bool", frames)
            if op == "ite":
                if sorts[0] != "Bool" or sorts[1] != sorts[2]:
                    raise SemanticError("ite needs a Bool guard and identically typed branches")
                return Term(z3.If(*values), sorts[1], frames)
            if op in {"add", "sub", "mul", "div", "mod", "lt", "le", "gt", "ge"}:
                if sorts != ["Int", "Int"]:
                    raise SemanticError("integer operators require explicit Int operands")
                if op in {"lt", "le", "gt", "ge"} and all(arg.unsigned_bv is not None for arg in args):
                    x, y = [arg.unsigned_bv for arg in args]
                    width = max(x.size(), y.size())
                    x, y = z3.ZeroExt(width-x.size(), x), z3.ZeroExt(width-y.size(), y)
                    fn = {"lt": z3.ULT, "le": z3.ULE, "gt": z3.UGT, "ge": z3.UGE}[op]
                    return Term(fn(x, y), "Bool", frames)
                fn = {"add": lambda x,y:x+y, "sub":lambda x,y:x-y, "mul":lambda x,y:x*y,
                      "div":lambda x,y:x/y, "mod":lambda x,y:x%y, "lt":lambda x,y:x<y,
                      "le":lambda x,y:x<=y, "gt":lambda x,y:x>y, "ge":lambda x,y:x>=y}[op]
                return Term(fn(*values), "Bool" if op in {"lt", "le", "gt", "ge"} else "Int", frames)
            if not sorts or any(not sort.startswith("BV") for sort in sorts):
                raise SemanticError(f"{op} requires bit-vector operands")
            if op == "extract":
                hi, lo = node["hi"], node["lo"]
                if type(hi) is not int or type(lo) is not int or not 0 <= lo <= hi < values[0].size():
                    raise SemanticError("invalid extraction bounds")
                return Term(z3.Extract(hi, lo, values[0]), f"BV{hi-lo+1}", frames)
            if op in {"zext", "sext"}:
                amount = node["amount"]
                if type(amount) is not int or amount < 0 or amount + values[0].size() > 4096:
                    raise SemanticError("invalid extension width")
                fn = z3.ZeroExt if op == "zext" else z3.SignExt
                return Term(fn(amount, values[0]), f"BV{amount+values[0].size()}", frames)
            if op == "concat":
                if sum(v.size() for v in values) > 4096:
                    raise SemanticError("concatenation exceeds the supported width")
                return Term(z3.Concat(*values), f"BV{sum(v.size() for v in values)}", frames)
            if any(sort != sorts[0] for sort in sorts):
                raise SemanticError("bit-vector operand widths disagree")
            operations = {"bvadd":"add", "bvsub":"sub", "bvmul":"mul", "bvand":"and",
                          "bvor":"or", "bvxor":"xor", "bvnot":"not", "bvudiv":"udiv",
                          "bvurem":"urem", "bvsdiv":"sdiv", "bvsrem":"srem", "bvshl":"sll",
                          "bvlshr":"srl", "bvashr":"sra", "bvult":"ult", "bvule":"ulte",
                          "bvslt":"slt", "bvsle":"slte"}
            if op not in operations:
                raise SemanticError(f"unsupported typed operator {op!r}")
            native = operations[op]
            value = self._operator(native, values, values[0].size(), ())
            if native in {"ult", "ulte", "slt", "slte"}:
                return Term(value == 1, "Bool", frames)
            return Term(value, sorts[0], frames)
        return visit(ast)


def ref(nid: int, frame: int = 0) -> dict:
    return {"op": "ref", "id": nid, **({"frame": frame} if frame else {})}


def operation(op: str, *args: dict, **params) -> dict:
    return {"op": op, "args": list(args), **params}
