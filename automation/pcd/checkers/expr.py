"""Restricted, typed expression language used to bind CHECKED certificates.

The kernel must not trust an arbitrary SMT-LIB script or polynomial payload.  A
certificate is CHECKED only when the evidence is regenerated from the *obligation
formula* stored in the proof graph.  This module is the small, auditable bridge
between those formulas and the independent checkers.

Supported grammar (deliberately small):

    expr    ::= or
    or      ::= and (("or" | "||") and)*
    and     ::= not (("and" | "&&") not)*
    not     ::= ("not" | "!") not | cmp
    cmp     ::= add (("=" | "==" | "!=" | "<" | "<=" | ">" | ">=") add)?
    add     ::= mul (("+" | "-") mul)*
    mul     ::= unary (("*" | "/" | "%") unary)*
    unary   ::= ("-" | "+") unary | power
    power   ::= atom ("^" power)?
    atom    ::= integer | identifier | "true" | "false" | "(" expr ")"
              | "ite" "(" expr "," expr "," expr ")"

Multiplication is explicit; write ``2*x`` rather than ``2x``.

Variables are integers or Booleans according to their use.  A bare variable in a
Boolean position is Boolean; a variable in arithmetic or a comparison is an
integer.  The same name cannot be used with both sorts in one obligation.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

MAX_POWER = 64
MAX_TERMS = 10_000
MAX_ATOMS = 128
MAX_TOKENS = 20_000
MAX_TEXT = 100_000


class ExprError(ValueError):
    """A malformed or unsupported expression."""


@dataclass(frozen=True)
class Token:
    kind: str
    text: str


_TOKEN_RE = re.compile(
    r"\s*(?:"
    r"(?P<num>[0-9]+)"
    r"|(?P<id>[A-Za-z_][A-Za-z0-9_.]*)"
    r"|(?P<op><=|>=|==|!=|&&|\|\||[(),+\-*/%^=<>!])"
    r")"
)
def tokenize(text: str) -> list[Token]:
    if not isinstance(text, str) or not text.strip():
        raise ExprError("empty expression")
    if len(text) > MAX_TEXT:
        raise ExprError("expression is too large")
    pos = 0
    out: list[Token] = []
    while pos < len(text):
        if len(out) > MAX_TOKENS:
            raise ExprError("expression has too many tokens")
        match = _TOKEN_RE.match(text, pos)
        if match is None:
            if text[pos:].strip() == "":
                break
            raise ExprError(f"unexpected character at offset {pos}: {text[pos:pos + 20]!r}")
        pos = match.end()
        if match.group("num") is not None:
            out.append(Token("num", match.group("num")))
        elif match.group("id") is not None:
            word = match.group("id")
            out.append(Token("id", word))
        else:
            out.append(Token("op", match.group("op")))
    out.append(Token("eof", ""))
    return out


class _Parser:
    def __init__(self, text: str) -> None:
        self.tokens = tokenize(text)
        self.i = 0

    def peek(self) -> Token:
        return self.tokens[self.i]

    def take(self) -> Token:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def accept_op(self, *ops: str) -> str | None:
        tok = self.peek()
        if tok.kind == "op" and tok.text in ops:
            self.i += 1
            return tok.text
        return None

    def accept_word(self, *words: str) -> str | None:
        tok = self.peek()
        if tok.kind == "id" and tok.text.lower() in words:
            self.i += 1
            return tok.text.lower()
        return None

    def expect_op(self, op: str) -> None:
        if self.accept_op(op) is None:
            tok = self.peek()
            raise ExprError(f"expected {op!r}, got {tok.text!r}")

    def parse(self) -> Any:
        node = self.parse_or()
        tok = self.peek()
        if tok.kind != "eof":
            raise ExprError(f"unexpected trailing token {tok.text!r}")
        return node

    def _at_end(self) -> bool:
        tok = self.peek()
        return tok.kind == "eof" or (tok.kind == "op" and tok.text in {")", ","})

    def parse_or(self) -> Any:
        # Accept both S-expression style "(or p q)" and infix "p or q".
        if self.accept_word("or") or self.accept_op("||"):
            items = []
            while not self._at_end():
                items.append(self.parse_and())
            if not items:
                raise ExprError("empty 'or' expression")
            return ("or", items)
        node = self.parse_and()
        items = [node]
        while self.accept_word("or") or self.accept_op("||"):
            items.append(self.parse_and())
        return items[0] if len(items) == 1 else ("or", items)

    def parse_and(self) -> Any:
        # Accept both S-expression style "(and p q)" and infix "p and q".
        if self.accept_word("and") or self.accept_op("&&"):
            items = []
            while not self._at_end():
                items.append(self.parse_not())
            if not items:
                raise ExprError("empty 'and' expression")
            return ("and", items)
        node = self.parse_not()
        items = [node]
        while self.accept_word("and") or self.accept_op("&&"):
            items.append(self.parse_not())
        return items[0] if len(items) == 1 else ("and", items)

    def parse_not(self) -> Any:
        if self.accept_word("not") or self.accept_op("!"):
            return ("not", self.parse_not())
        return self.parse_cmp()

    def parse_cmp(self) -> Any:
        left = self.parse_add()
        op = self.accept_op("=", "==", "!=", "<", "<=", ">", ">=")
        if op is None:
            return left
        if op == "==":
            op = "="
        right = self.parse_add()
        return ("cmp", op, left, right)

    def parse_add(self) -> Any:
        node = self.parse_mul()
        while True:
            op = self.accept_op("+", "-")
            if op is None:
                return node
            node = ("arith", op, node, self.parse_mul())

    def parse_mul(self) -> Any:
        node = self.parse_unary()
        while True:
            op = self.accept_op("*", "/", "%")
            if op is not None:
                node = ("arith", op, node, self.parse_unary())
                continue
            return node

    def parse_unary(self) -> Any:
        if self.accept_op("-"):
            return ("neg", self.parse_unary())
        if self.accept_op("+"):
            return self.parse_unary()
        return self.parse_power()

    def parse_power(self) -> Any:
        node = self.parse_atom()
        if self.accept_op("^"):
            return ("pow", node, self.parse_power())
        return node

    def parse_atom(self) -> Any:
        tok = self.take()
        if tok.kind == "num":
            return ("num", int(tok.text))
        if tok.kind == "id":
            word = tok.text.lower()
            if word == "true":
                return ("bool", True)
            if word == "false":
                return ("bool", False)
            if word == "ite":
                if self.accept_op("(") is None:
                    raise ExprError("ite must be used as ite(cond, value, value)")
                cond = self.parse_or()
                self.expect_op(",")
                when_true = self.parse_or()
                self.expect_op(",")
                when_false = self.parse_or()
                self.expect_op(")")
                return ("ite", cond, when_true, when_false)
            if word in {"and", "or", "not"}:
                raise ExprError(f"unexpected keyword {tok.text!r}")
            return ("var", tok.text)
        if tok.kind == "op" and tok.text == "(":
            node = self.parse_or()
            self.expect_op(")")
            return node
        raise ExprError(f"unexpected token {tok.text!r}")


def parse(text: str) -> Any:
    try:
        return _Parser(text).parse()
    except RecursionError as exc:
        raise ExprError("expression is too deeply nested") from exc


def _set_sort(vars: dict[str, str], name: str, sort: str, where: str) -> None:
    old = vars.get(name)
    if old is not None and old != sort:
        raise ExprError(f"variable {name!r} is used as both {old} and {sort} ({where})")
    vars[name] = sort


def _infer(ast: Any, expected: str, vars: dict[str, str]) -> None:
    kind = ast[0]
    if expected == "Bool":
        if kind == "bool":
            return
        if kind == "var":
            _set_sort(vars, ast[1], "Bool", "boolean position")
            return
        if kind == "not":
            _infer(ast[1], "Bool", vars)
            return
        if kind in {"and", "or"}:
            for item in ast[1]:
                _infer(item, "Bool", vars)
            return
        if kind == "cmp":
            _infer(ast[2], "Int", vars)
            _infer(ast[3], "Int", vars)
            return
        if kind == "ite":
            _infer(ast[1], "Bool", vars)
            _infer(ast[2], expected, vars)
            _infer(ast[3], expected, vars)
            return
        raise ExprError(f"{kind} is not a Boolean expression")
    if expected == "Int":
        if kind == "num":
            return
        if kind == "var":
            _set_sort(vars, ast[1], "Int", "integer position")
            return
        if kind == "neg":
            _infer(ast[1], "Int", vars)
            return
        if kind == "arith":
            _infer(ast[2], "Int", vars)
            _infer(ast[3], "Int", vars)
            return
        if kind == "pow":
            _infer(ast[1], "Int", vars)
            exponent = _constant_int(ast[2])
            if exponent is None or exponent < 0 or exponent > MAX_POWER:
                raise ExprError(f"unsupported exponent {_pretty(ast[2])!r}")
            return
        if kind == "ite":
            _infer(ast[1], "Bool", vars)
            _infer(ast[2], "Int", vars)
            _infer(ast[3], "Int", vars)
            return
        raise ExprError(f"{kind} is not an integer expression")
    raise ExprError(f"unsupported expected sort {expected!r}")


def infer(ast: Any, expected: str = "Bool", vars: dict[str, str] | None = None) -> dict[str, str]:
    table: dict[str, str] = {} if vars is None else vars
    _infer(ast, expected, table)
    return table


def _constant_int(ast: Any) -> int | None:
    if ast[0] == "num":
        return int(ast[1])
    if ast[0] == "neg":
        value = _constant_int(ast[1])
        return -value if value is not None else None
    return None


def _pretty(ast: Any) -> str:
    kind = ast[0]
    if kind in {"num", "var"}:
        return str(ast[1])
    if kind == "bool":
        return "true" if ast[1] else "false"
    if kind == "neg":
        return f"-{_pretty(ast[1])}"
    if kind == "not":
        return f"not {_pretty(ast[1])}"
    if kind in {"and", "or"}:
        return "(" + f" {kind} ".join(_pretty(x) for x in ast[1]) + ")"
    if kind == "cmp":
        return f"({_pretty(ast[2])} {ast[1]} {_pretty(ast[3])})"
    if kind == "arith":
        return f"({_pretty(ast[2])} {ast[1]} {_pretty(ast[3])})"
    if kind == "pow":
        return f"({_pretty(ast[1])} ^ {_pretty(ast[2])})"
    if kind == "ite":
        return f"ite({_pretty(ast[1])}, {_pretty(ast[2])}, {_pretty(ast[3])})"
    return str(ast)


def rename_vars(ast: Any, mapping: dict[str, str]) -> Any:
    """Return a structural copy with variable identifiers renamed.

    Only variable atoms are rewritten.  Induction checkers use this to derive
    the next-state copy of an invariant without accepting a second unchecked
    formula from the planner.
    """
    kind = ast[0]
    if kind == "var":
        return ("var", mapping.get(ast[1], ast[1]))
    if kind in {"num", "bool"}:
        return ast
    if kind in {"neg", "not"}:
        return (kind, rename_vars(ast[1], mapping))
    if kind in {"and", "or"}:
        return (kind, [rename_vars(x, mapping) for x in ast[1]])
    if kind == "cmp":
        return (kind, ast[1], rename_vars(ast[2], mapping), rename_vars(ast[3], mapping))
    if kind == "arith":
        return (kind, ast[1], rename_vars(ast[2], mapping), rename_vars(ast[3], mapping))
    if kind == "pow":
        return (kind, rename_vars(ast[1], mapping), rename_vars(ast[2], mapping))
    if kind == "ite":
        return (
            kind,
            rename_vars(ast[1], mapping),
            rename_vars(ast[2], mapping),
            rename_vars(ast[3], mapping),
        )
    raise ExprError(f"cannot rename {kind}")


def to_text(ast: Any) -> str:
    """Serialize an AST back to the accepted surface syntax."""
    return _pretty(ast)


def to_smt(ast: Any, vars: dict[str, str]) -> str:
    kind = ast[0]
    if kind == "var":
        if ast[1] not in vars:
            raise ExprError(f"untyped variable {ast[1]!r}")
        return ast[1]
    if kind == "num":
        return str(ast[1])
    if kind == "bool":
        return "true" if ast[1] else "false"
    if kind == "neg":
        return f"(- {to_smt(ast[1], vars)})"
    if kind == "not":
        return f"(not {to_smt(ast[1], vars)})"
    if kind in {"and", "or"}:
        args = " ".join(to_smt(x, vars) for x in ast[1])
        return f"({kind} {args})"
    if kind == "cmp":
        op = ast[1]
        left = to_smt(ast[2], vars)
        right = to_smt(ast[3], vars)
        if op == "!=":
            return f"(not (= {left} {right}))"
        return f"({op} {left} {right})"
    if kind == "arith":
        op = ast[1]
        left = to_smt(ast[2], vars)
        right = to_smt(ast[3], vars)
        smt_op = {"/": "div", "%": "mod"}.get(op, op)
        return f"({smt_op} {left} {right})"
    if kind == "pow":
        base = to_smt(ast[1], vars)
        exponent = _constant_int(ast[2])
        if exponent is None or exponent < 0 or exponent > MAX_POWER:
            raise ExprError(f"unsupported exponent {_pretty(ast[2])!r}")
        if exponent == 0:
            return "1"
        if exponent == 1:
            return base
        return "(* " + " ".join([base] * exponent) + ")"
    if kind == "ite":
        cond = to_smt(ast[1], vars)
        when_true = to_smt(ast[2], vars)
        when_false = to_smt(ast[3], vars)
        return f"(ite {cond} {when_true} {when_false})"
    raise ExprError(f"cannot serialize {kind}")


def canonical_script(premises: Iterable[str], goal: str) -> str:
    """Return the exact canonical SMT-LIB script for ``premises -> goal``."""
    premise_exprs = list(premises)
    vars: dict[str, str] = {}
    parsed_premises = []
    for text in premise_exprs:
        ast = parse(text)
        infer(ast, "Bool", vars)
        parsed_premises.append(ast)
    goal_ast = parse(goal)
    infer(goal_ast, "Bool", vars)

    lines = ["(set-logic ALL)"]
    for name in sorted(vars):
        lines.append(f"(declare-const {name} {vars[name]})")
    for ast in parsed_premises:
        lines.append(f"(assert {to_smt(ast, vars)})")
    lines.append(f"(assert (not {to_smt(goal_ast, vars)}))")
    lines.append("(check-sat)")
    return "\n".join(lines) + "\n"


def normalize_script(script: str) -> str:
    """Whitespace-insensitive comparison form; comments are not accepted."""
    lines = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(";"):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def script_matches(script: str, premises: Iterable[str], goal: str) -> tuple[bool, str, str]:
    try:
        expected = canonical_script(premises, goal)
    except ExprError as exc:
        return False, "", f"obligation formula is not encodable: {exc}"
    except RecursionError:
        return False, "", "obligation formula is too deeply nested"
    if not isinstance(script, str) or not script.strip():
        return False, expected, "payload.smt2 is required"
    if normalize_script(script) != normalize_script(expected):
        return False, expected, "script is not the canonical encoding of the obligation"
    return True, expected, "canonical"


# ---------------------------------------------------------------------------
# Polynomial normal forms
# ---------------------------------------------------------------------------


def _poly_add(p: dict[tuple[str, ...], int], q: dict[tuple[str, ...], int], W: int) -> dict[tuple[str, ...], int]:
    mod = 1 << W
    out: dict[tuple[str, ...], int] = {}
    for monomial, coeff in p.items():
        out[monomial] = (out.get(monomial, 0) + coeff) % mod
    for monomial, coeff in q.items():
        out[monomial] = (out.get(monomial, 0) + coeff) % mod
    return {m: c for m, c in out.items() if c % mod}


def _poly_mul(p: dict[tuple[str, ...], int], q: dict[tuple[str, ...], int], W: int) -> dict[tuple[str, ...], int]:
    mod = 1 << W
    out: dict[tuple[str, ...], int] = {}
    for m1, c1 in p.items():
        for m2, c2 in q.items():
            monomial = tuple(sorted(m1 + m2))
            if len(monomial) > MAX_ATOMS:
                raise ExprError("polynomial monomial exceeds atom limit")
            out[monomial] = (out.get(monomial, 0) + c1 * c2) % mod
        if len(out) > MAX_TERMS:
            raise ExprError("polynomial exceeds term limit")
    return {m: c for m, c in out.items() if c % mod}


def _poly(ast: Any, W: int) -> dict[tuple[str, ...], int]:
    kind = ast[0]
    if kind == "num":
        mod = 1 << W
        return {(): int(ast[1]) % mod} if int(ast[1]) % mod else {}
    if kind == "var":
        return {(ast[1],): 1}
    if kind == "neg":
        return _poly_mul(_poly(("num", -1), W), _poly(ast[1], W), W)
    if kind == "arith":
        op = ast[1]
        left = _poly(ast[2], W)
        right = _poly(ast[3], W)
        if op == "+":
            return _poly_add(left, right, W)
        if op == "-":
            return _poly_add(left, _poly_mul(_poly(("num", -1), W), right, W), W)
        if op == "*":
            return _poly_mul(left, right, W)
        raise ExprError(f"operator {op!r} is not polynomial")
    if kind == "pow":
        base = _poly(ast[1], W)
        exponent = _constant_int(ast[2])
        if exponent is None or exponent < 0 or exponent > MAX_POWER:
            raise ExprError(f"unsupported polynomial exponent {_pretty(ast[2])!r}")
        out: dict[tuple[str, ...], int] = {(): 1}
        for _ in range(exponent):
            out = _poly_mul(out, base, W)
        return out
    raise ExprError(f"{kind} is not a polynomial expression")


def poly_identity(expr: str, W: int = 32) -> tuple[bool, str]:
    """Check a polynomial equality expression over Z/2^W."""
    if W < 1 or W > 4096:
        return False, f"unsupported width {W}"
    try:
        ast = parse(expr)
    except ExprError as exc:
        return False, f"parse error: {exc}"
    if ast[0] != "cmp" or ast[1] not in {"="}:
        return False, "poly obligation must be an equality"
    lhs_ast, rhs_ast = ast[2], ast[3]
    if lhs_ast == rhs_ast:
        return False, "identity is syntactically trivial (vacuous)"
    try:
        lhs = _poly(lhs_ast, W)
        rhs = _poly(rhs_ast, W)
    except ExprError as exc:
        return False, f"polynomial error: {exc}"
    except RecursionError:
        return False, "polynomial is too deeply nested"
    if not lhs and not rhs:
        return False, "identity is empty (vacuous)"
    diff = _poly_add(lhs, _poly_mul(_poly(("num", -1), W), rhs, W), W)
    return (not diff), ("zero" if not diff else f"non-zero: {dict(diff)}")
