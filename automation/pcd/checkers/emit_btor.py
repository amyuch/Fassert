"""Export a typed state lemma as a BTOR constraint.

This construction helper is not acceptance authority: the composition guard
independently checks the emitted constraint against the proved typed formula.
Integer expressions and temporal formulas cannot be silently exported as BV.
"""
from __future__ import annotations

from . import btor, semantics


def append_constraint(text: str, expression: dict, *, name: str = "pcd_imported_lemma") -> tuple[str, int]:
    return _append_formula(text, expression, name=name, as_property=False)


def append_property(text: str, expression: dict, *, name: str) -> tuple[str, int]:
    """Add an observation only; its predicate is negated to form a BTOR bad."""
    return _append_formula(text, expression, name=name, as_property=True)


def _append_formula(text: str, expression: dict, *, name: str, as_property: bool) -> tuple[str, int]:
    model = btor.Model("<construction>", text=text)
    context = semantics.Context(model, "construction")
    term = context.lower(expression)
    if term.sort != "Bool" or 1 in term.frames:
        raise semantics.SemanticError("only current-state Boolean lemmas can become constraints")
    ids = [int(line.split()[0]) for line in text.splitlines() if line.split(";", 1)[0].strip()]
    next_id = max(ids) + 1
    sorts = {width: nid for nid, width in model.sorts.items()}
    lines = []

    def line(body):
        nonlocal next_id
        result = next_id
        next_id += 1
        lines.append(f"{result} {body}")
        return result

    def sort(width):
        if width not in sorts:
            sorts[width] = line(f"sort bitvec {width}")
        return sorts[width]

    def emit(ast):
        op = ast["op"]
        typed = context.lower(ast)
        if op == "ref":
            if ast.get("frame", 0):
                raise semantics.SemanticError("future references cannot become state constraints")
            return ast["id"]
        if typed.sort == "Int" or op in {"uint", "sint"}:
            raise semantics.SemanticError("integer lifting requires an explicit proved BV representation")
        width = 1 if typed.sort == "Bool" else int(typed.sort[2:])
        sid = sort(width)
        if op in {"bv", "bool"}:
            value = int(ast["value"]) % (1 << width)
            return line(f"constd {sid} {value}")
        args = [emit(arg) for arg in ast["args"]]
        if op == "truth":
            return args[0]
        if op in {"and", "or"}:
            if not args:
                return line(f"constd {sid} {1 if op == 'and' else 0}")
            result = args[0]
            for arg in args[1:]:
                result = line(f"{op} {sid} {result} {arg}")
            return result
        native = {"bvadd":"add", "bvsub":"sub", "bvmul":"mul", "bvand":"and", "bvor":"or",
                  "bvxor":"xor", "bvnot":"not", "bvudiv":"udiv", "bvurem":"urem", "bvsdiv":"sdiv",
                  "bvsrem":"srem", "bvshl":"sll", "bvlshr":"srl", "bvashr":"sra", "bvult":"ult",
                  "bvule":"ulte", "bvslt":"slt", "bvsle":"slte", "extract":"slice", "zext":"uext"}.get(op, op)
        allowed = {"not", "implies", "eq", "ite", "concat", "slice", "uext", "sext"} | btor.BINARY | btor.UNARY
        if native not in allowed:
            raise semantics.SemanticError(f"cannot export typed operation {op}")
        params = [ast["hi"], ast["lo"]] if op == "extract" else [ast["amount"]] if op in {"zext", "sext"} else []
        return line(" ".join(map(str, [native, sid, *args, *params])))

    predicate = emit(expression)
    if not name or any(ch.isspace() or ch == ";" for ch in name):
        raise semantics.SemanticError("invalid constraint annotation")
    if as_property:
        predicate = line(f"not {sort(1)} {predicate}")
        line(f"bad {predicate} {name}")
    else:
        line(f"constraint {predicate} {name}")
    result = text.rstrip() + "\n" + "\n".join(lines) + "\n"
    # A construction bug must fail before an engine is invoked. Acceptance
    # later performs a separate semantic implication check under the state map.
    btor.Model("<emitted>", text=result)
    return result, predicate
