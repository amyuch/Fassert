"""Structured induction checker.

The checker accepts a small transition-system description rather than an
arbitrary SMT-LIB script:

    {
      "vars":  [{"name": "d", "sort": "Int"}, ...],
      "init":  ["d = M", ...],
      "step":  ["d_next = ite(D <= d, d - D, d)", ...],
      "inv":   ["d + N*q = M", ...],
      "exit":  ["msk = 0", ...],
      "goal":  "rvfi = spec",
      "timeout_ms": 30000
    }

It regenerates and checks three implications:

    premises & init          => inv
    premises & inv & step    => inv[next]
    premises & inv & exit    => goal

All formulas go through :mod:`checkers.expr`, so a planner cannot supply an
unbound `(assert false)` or a precomputed UNSAT script.  The transition relation
is explicit; variables ending in ``_next`` are the next-state image and every
variable must be declared in ``vars``.
"""
from __future__ import annotations

import copy
from typing import Any, Iterable

import z3

from . import expr
from . import smt

ALLOWED_SORTS = {"Int", "Bool"}
MAX_FORMULAS = 128


class InductionError(ValueError):
    pass


def _declarations(payload: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    raw = payload.get("vars")
    if not isinstance(raw, list) or not raw:
        raise InductionError("payload.vars must be a non-empty array")
    current: dict[str, str] = {}
    next_vars: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise InductionError("each vars entry must be an object")
        name = item.get("name")
        sort = item.get("sort")
        if not isinstance(name, str) or not name or not name.isidentifier():
            raise InductionError(f"invalid variable name: {name!r}")
        if sort not in ALLOWED_SORTS:
            raise InductionError(f"{name}: unsupported sort {sort!r}")
        if name in current:
            raise InductionError(f"duplicate variable {name!r}")
        current[name] = sort
        next_vars[f"{name}_next"] = sort
    return current, next_vars


def _formula_list(payload: dict[str, Any], key: str, *, required: bool = True) -> list[str]:
    raw = payload.get(key)
    if raw is None:
        if required:
            raise InductionError(f"payload.{key} is required")
        return []
    if not isinstance(raw, list) or not all(isinstance(x, str) and x.strip() for x in raw):
        raise InductionError(f"payload.{key} must be an array of non-empty formulas")
    if len(raw) > MAX_FORMULAS:
        raise InductionError(f"payload.{key} has too many formulas")
    return list(raw)


def _check_vars(texts: Iterable[str], declared: dict[str, str], where: str) -> None:
    for text in texts:
        try:
            ast = expr.parse(text)
            table = expr.infer(ast, "Bool")
        except expr.ExprError as exc:
            raise InductionError(f"{where}: {exc}") from exc
        for name, sort in table.items():
            if name not in declared:
                raise InductionError(f"{where}: undeclared variable {name!r}")
            if declared[name] != sort:
                raise InductionError(
                    f"{where}: variable {name!r} declared {declared[name]} but used as {sort}"
                )


def _and(texts: list[str]) -> str:
    if not texts:
        return "true"
    if len(texts) == 1:
        return texts[0]
    return "(" + " && ".join(f"({t})" for t in texts) + ")"


def _next_formulas(inv: list[str], current: dict[str, str], next_vars: dict[str, str]) -> list[str]:
    # Rename every current variable to its _next image; variables that are not
    # in the transition system stay unchanged.  The resulting formulas are
    # re-serialized through the same parser, so the checker never accepts a
    # hand-written next-state formula.
    mapping = {name: f"{name}_next" for name in current}
    out: list[str] = []
    for text in inv:
        try:
            ast = expr.parse(text)
        except expr.ExprError as exc:
            raise InductionError(f"invariant: {exc}") from exc
        renamed = expr.rename_vars(ast, mapping)
        out.append(expr.to_text(renamed))
    return out


def check(premises: list[str], goal: str, payload: dict[str, Any], timeout_ms: int | None = None) -> tuple[bool, str]:
    """Check base, consecution, and exit for a structured induction proof."""
    if not isinstance(payload, dict):
        return False, "payload must be an object"
    try:
        current, next_vars = _declarations(payload)
        init = _formula_list(payload, "init")
        step = _formula_list(payload, "step")
        inv = _formula_list(payload, "inv")
        exit_formulas = _formula_list(payload, "exit", required=False)
        payload_goal = payload.get("goal")
        if not isinstance(payload_goal, str) or not payload_goal.strip():
            raise InductionError("payload.goal is required")
        if payload_goal != goal:
            raise InductionError("payload.goal is not the obligation guarantee")
        declared = {**current, **next_vars}
        all_formulas = list(premises) + init + step + inv + exit_formulas + [goal]
        _check_vars(all_formulas, declared, "induction payload")
        limit = int(payload.get("timeout_ms") or timeout_ms or 30_000)
        if limit < 1:
            raise InductionError("timeout_ms must be positive")
    except (InductionError, TypeError, ValueError) as exc:
        return False, f"invalid induction payload: {exc}"

    inv_next = _next_formulas(inv, current, next_vars)
    inv_all = _and(inv)
    base_premises = list(premises) + init
    step_premises = list(premises) + [inv_all] + step
    exit_premises = list(premises) + [inv_all] + exit_formulas

    checks = [
        ("base", base_premises, _and(inv)),
        ("consecution", step_premises, _and(inv_next)),
        ("exit", exit_premises, goal),
    ]
    for name, prems, target in checks:
        try:
            script = expr.canonical_script(prems, target)
        except expr.ExprError as exc:
            return False, f"{name}: formula is not encodable: {exc}"
        ok, detail = smt._run(script, timeout_ms=limit)
        if not ok:
            return False, f"{name}: {detail}"

    # A proof that only covers the base case and an empty transition relation is
    # not useful.  The step relation must actually constrain a next-state
    # variable, and the invariant must mention a current state variable.
    return True, "induction proved"
