"""Discharge typed lemmas using the actual frozen model's SMT semantics.

The planner supplies predicates and optional strengthening invariants. Initial
states, transitions, constraints and primitive bit-vector meanings are always
regenerated from BTOR. No supplied recurrence or SMT-LIB script is trusted.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

import z3

from . import expr, semantics

FORMAT = "btor-smt"
CHECKER = "pcd-btor-smt/0.1"

try:  # Optional QF_BV backend; Z3 remains the portable fallback.
    import bitwuzla as _bitwuzla

    try:
        from importlib.metadata import version as _package_version

        _BITWUZLA_VERSION = _package_version("bitwuzla")
    except Exception:
        _BITWUZLA_VERSION = "unknown"
except Exception:  # pragma: no cover - exercised where the wheel is absent
    _bitwuzla = None
    _BITWUZLA_VERSION = None

try:  # Optional integer-lifting backend for the restoring-division invariants.
    import cvc5 as _cvc5

    _CVC5_VERSION = getattr(_cvc5, "__version__", "unknown")
except Exception:  # pragma: no cover - exercised where the wheel is absent
    _cvc5 = None
    _CVC5_VERSION = None


class _Unsupported(Exception):
    """The optional backend cannot parse this query (e.g. integer lifting)."""


def _smt2_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == ";":
            while i < n and text[i] != "\n":
                i += 1
        elif c in "()":
            tokens.append(c)
            i += 1
        elif c == "|":
            j = i + 1
            while j < n and text[j] != "|":
                j += 1
            tokens.append(text[i:j + 1])
            i = j + 1
        elif c == '"':
            j = i + 1
            while j < n:
                if text[j] == '"':
                    if j + 1 < n and text[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            tokens.append(text[i:j + 1])
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "();":
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def _smt2_parse(tokens: list[str]) -> list:
    pos = 0

    def term():
        nonlocal pos
        if tokens[pos] != "(":
            value = tokens[pos]
            pos += 1
            return value
        pos += 1
        values = []
        while tokens[pos] != ")":
            values.append(term())
        pos += 1
        return values

    result = []
    while pos < len(tokens):
        result.append(term())
    return result


def _smt2_normalize_term(value):
    if isinstance(value, list):
        normalized = [_smt2_normalize_term(v) for v in value]
        if normalized and normalized[0] in ("and", "or") and len(normalized) == 2:
            # SMT-LIB allows unary conjunctions/disjunctions; Bitwuzla's parser
            # rejects them, so remove the wrapper (semantics are unchanged).
            return normalized[1]
        if normalized == ["and"]:
            return "true"
        if normalized == ["or"]:
            return "false"
        if normalized and normalized[0] == "distinct" and len(normalized) == 2:
            return "true"
        return normalized
    return value


def _smt2_serialize(value) -> str:
    # Use an explicit stack: large model queries can nest more deeply than
    # Python's recursion limit, and failing to serialize them must not turn a
    # semantic property into a checker error.
    out: list[str] = []
    stack: list[tuple[bool, object]] = [(False, value)]
    while stack:
        is_space, item = stack.pop()
        if is_space:
            out.append(item)  # type: ignore[arg-type]
            continue
        if not isinstance(item, list):
            out.append(item)  # type: ignore[arg-type]
            continue
        out.append("(")
        stack.append((True, ")"))
        for index, child in enumerate(reversed(item)):
            stack.append((False, child))
            if index != len(item) - 1:
                stack.append((True, " "))
    return "".join(out)


_SMT2_COMMANDS = {"check-sat", "get-model", "get-value", "get-unsat-core", "exit"}


def _smt2_normalize(text: str) -> str:
    # Drop solver commands: the backend is driven explicitly via check_sat().
    values = [v for v in _smt2_parse(_smt2_tokens(text))
              if not (isinstance(v, list) and v and v[0] in _SMT2_COMMANDS)]
    return "\n".join(_smt2_serialize(_smt2_normalize_term(v)) for v in values)


def _bitwuzla_check(text: str, timeout_ms: int) -> tuple[str, float]:
    manager = _bitwuzla.TermManager()
    options = _bitwuzla.Options()
    options.set(_bitwuzla.Option.TIME_LIMIT_PER, timeout_ms)
    parser = _bitwuzla.Parser(manager, options)
    try:
        parser.parse(text, parse_only=True, parse_file=False)
    except Exception as exc:  # unsupported logic/operator, not a semantic result
        raise _Unsupported(str(exc)) from exc
    start = time.monotonic()
    result = parser.bitwuzla().check_sat()
    return str(result), time.monotonic() - start


def _cvc5_check(text: str, timeout_ms: int) -> tuple[str, float]:
    """Check an SMT-LIB query with CVC5's bounded bit-vector integer lift.

    ``solve-bv-as-int=sum`` is a sound preprocessing step for QF_BV: CVC5
    translates bit-vector arithmetic to bounded integers and lifts back.  The
    text is parsed exactly as emitted by the model semantics; only the trailing
    query commands are removed so the solver runs one bounded check.
    """
    if _cvc5 is None:
        raise _Unsupported("CVC5 is not installed")
    text = text.replace("(get-model)", "").replace("(check-sat)", "")
    manager = _cvc5.TermManager()
    solver = _cvc5.Solver(manager)
    try:
        solver.setOption("solve-bv-as-int", "sum")
        solver.setOption("tlimit-per", str(timeout_ms))
    except Exception as exc:  # unsupported option/version, not a semantic result
        raise _Unsupported(str(exc)) from exc
    parser = _cvc5.InputParser(solver)
    symbols = parser.getSymbolManager()
    try:
        parser.setStringInput(_cvc5.InputLanguage.SMT_LIB_2_6, text, "query")
        while not parser.done():
            command = parser.nextCommand()
            if command.isNull():
                continue
            command.invoke(solver, symbols)
    except Exception as exc:  # parser rejects a construct, not a SAT verdict
        raise _Unsupported(str(exc)) from exc
    start = time.monotonic()
    result = str(solver.checkSat()).strip()
    return result, time.monotonic() - start


def context(store, model_id: str) -> semantics.Context:
    if not hasattr(store, "semantic_contexts"):
        store.semantic_contexts = {}
    if model_id not in store.semantic_contexts:
        # Substitution of actual deterministic next functions is an exact
        # transition normalization. Unassigned next state remains free.
        store.semantic_contexts[model_id] = semantics.Context(store.get(model_id), model_id, inline_next=True)
    return store.semantic_contexts[model_id]


def binding_term(node: dict, guarantee: dict, store, frame: int = 0) -> semantics.Term:
    from . import composition  # local import keeps the checker modules acyclic

    if guarantee.get("sort") != "Bool" or expr.parse(guarantee["expr"])[0] != "var":
        raise semantics.SemanticError("model-bound guarantees require distinct Boolean atoms")
    cert, binding = node["certificate"], guarantee.get("binding") or {}
    if cert.get("goal") != guarantee.get("name"):
        raise semantics.SemanticError("semantic premise is not the guarantee established by its certificate")
    if cert.get("evidence") not in {"CHECKED", "REPLAY"} or cert.get("verdict") != "proved":
        raise semantics.SemanticError("a semantic premise needs proved CHECKED/REPLAY evidence")
    ctx = context(store, node["model"])
    if binding.get("kind") == "btor-bad":
        model, name = composition.bound_property(node, guarantee, store)
        return semantics.Term(ctx.ref(model.properties[name], frame) == 0, "Bool", frozenset({frame}))
    if binding.get("kind") != "btor-expression" or set(binding) != {"kind", "expression"}:
        raise semantics.SemanticError("missing exact model-expression binding")
    if cert.get("format") != FORMAT or cert.get("checker") != CHECKER:
        raise semantics.SemanticError("an expression binding requires a model-bound SMT certificate")
    term = ctx.lower(binding["expression"], frame)
    if term.sort != "Bool":
        raise semantics.SemanticError("a bound theorem must have Bool sort")
    return term


def _elapsed_ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


def _sat_error(label: str, query_hash: str) -> semantics.SemanticError:
    # A SAT induction step is a CTI for the chosen invariant, not a design
    # counterexample: the property may still hold with a stronger invariant.
    # Keep it as an open obligation instead of a refutation.  A SAT base,
    # combinational implication or explicit step theorem is a real
    # counterexample to the stated claim.
    if "induction step" in label:
        return semantics.SemanticError(
            f"{label}: sat (induction CTI; invariant needs strengthening); query={query_hash}"
        )
    return semantics.SemanticError(f"{label}: sat (counterexample); query={query_hash}")


def _multiplication_abstraction(formula):
    """A conservative congruence query after exact low-product truncation.

    For w-bit products, low k bits depend only on the low k operand bits.
    After that identity, replacing every same-width multiplication by one
    shared arbitrary function over-approximates BV multiplication. Only UNSAT
    is useful; SAT/UNKNOWN must fall back to the actual arithmetic query.
    """
    def rewrite(root, replace):
        memo = {}
        pending = [(root, False)]
        while pending:
            term, ready = pending.pop()
            key = term.get_id()
            if key in memo:
                continue
            if z3.is_quantifier(term):
                raise _Unsupported("multiplication abstraction is quantifier-free")
            if not ready:
                pending.append((term, True))
                pending.extend((child, False) for child in term.children())
            else:
                children = [memo[child.get_id()] for child in term.children()]
                value = term.decl()(*children) if children else term
                memo[key] = replace(value)
        return memo[root.get_id()]

    def truncate(term):
        if term.decl().kind() == z3.Z3_OP_EXTRACT:
            hi, lo = term.params()
            product = term.arg(0)
            if lo == 0 and product.decl().kind() == z3.Z3_OP_BMUL:
                args = [z3.simplify(z3.Extract(hi, 0, value)) for value in product.children()]
                value = args[0]
                for operand in args[1:]:
                    value = value * operand
                return value
        return term

    functions = {}
    def abstract(term):
        if term.decl().kind() != z3.Z3_OP_BMUL:
            return term
        width = term.size()
        if width not in functions:
            sort = z3.BitVecSort(width)
            functions[width] = z3.Function(f"pcd_abstract_bvmul_{width}", sort, sort, sort)
        args = term.children()
        value = args[0]
        for operand in args[1:]:
            value = functions[width](value, operand)
        return value

    exact = z3.simplify(rewrite(formula, truncate))
    approximate = rewrite(exact, abstract)
    return approximate if functions else None


def prove(premises: list, goal, label: str, timeout_ms: int) -> dict[str, Any]:
    solver = z3.Solver()
    solver.add(*premises)
    solver.add(z3.Not(goal))
    query_hash = hashlib.sha256(solver.sexpr().encode()).hexdigest()
    # Serialize before any check: Z3 rewrites checked formulas and can emit
    # internal helpers such as ``bvurem_i`` that other parsers reject.
    raw_text = solver.to_smt2()
    start = time.monotonic()

    approximate = _multiplication_abstraction(z3.And(*solver.assertions()))
    if approximate is not None:
        congruence = z3.Solver()
        congruence.set(timeout=min(2000, max(1, timeout_ms // 2)))
        congruence.add(approximate)
        abstract_hash = hashlib.sha256(congruence.sexpr().encode()).hexdigest()
        if congruence.check() == z3.unsat:
            return {"result": "unsat", "query_sha256": query_hash,
                    "seconds": round(time.monotonic() - start, 6),
                    "solver": "z3-multiplication-congruence",
                    "backend_query_sha256": abstract_hash,
                    "normalization": "exact low-product truncation; shared multiplication over-approximation"}

    def z3_result() -> dict[str, Any] | None:
        verdict = solver.check()
        if verdict == z3.unsat:
            return {"result": "unsat", "query_sha256": query_hash,
                    "seconds": round(time.monotonic() - start, 6), "solver": "z3"}
        if verdict == z3.sat:
            raise _sat_error(label, query_hash)
        return None

    # Portfolio: a short Z3 slice handles most queries, Bitwuzla often cracks
    # wide-multiplier goals that Z3 cannot bit-blast in time, and a final Z3
    # slice keeps slow-but-solvable Z3 cases from being starved by a bad
    # Bitwuzla attempt. Every backend returns a sound SAT/UNSAT verdict.
    solver.set(timeout=min(timeout_ms, 1000))
    result = z3_result()
    if result is not None:
        return result
    if _bitwuzla is not None:
        slice_ms = min(max(1, timeout_ms - _elapsed_ms(start)), 5000)
        try:
            text = _smt2_normalize("(set-logic QF_BV)\n" + raw_text)
            verdict, seconds = _bitwuzla_check(text, slice_ms)
        except _Unsupported:
            verdict, seconds = None, 0.0
        if verdict == "unsat":
            return {"result": "unsat", "query_sha256": query_hash,
                    "seconds": round(seconds, 6),
                    "solver": f"bitwuzla-{_BITWUZLA_VERSION}",
                    # Exact SMT-LIB text handed to the second backend.  The
                    # canonical query hash above is backend-independent; this
                    # hash makes the (semantics-preserving) normalization
                    # auditable instead of implicit.
                    "backend_query_sha256": hashlib.sha256(text.encode()).hexdigest()}
        if verdict == "sat":
            raise _sat_error(label, query_hash)
    if _cvc5 is not None:
        slice_ms = min(max(1, timeout_ms - _elapsed_ms(start)), 20000)
        try:
            # Do not pin CVC5 to QF_BV here.  Its ``solve-bv-as-int`` lift is
            # substantially stronger when the parser has the default
            # all-theories context; a QF_BV logic pin makes the same bounded
            # arithmetic query time out.
            text = raw_text
            verdict, seconds = _cvc5_check(text, slice_ms)
        except _Unsupported:
            verdict, seconds = None, 0.0
        if verdict == "unsat":
            return {"result": "unsat", "query_sha256": query_hash,
                    "seconds": round(seconds, 6),
                    "solver": f"cvc5-{_CVC5_VERSION}",
                    "backend_query_sha256": hashlib.sha256(text.encode()).hexdigest()}
        if verdict == "sat":
            raise _sat_error(label, query_hash)
    remaining = max(1, timeout_ms - _elapsed_ms(start))
    solver.set(timeout=remaining)
    result = z3_result()
    if result is not None:
        return result
    reason = solver.reason_unknown()
    raise semantics.SemanticError(f"{label}: z3 unknown ({reason}); query={query_hash}")


def check(node: dict, nodes: dict[str, dict], store) -> dict[str, Any]:
    cert, payload = node["certificate"], node["certificate"].get("payload", {})
    if cert.get("checker") != CHECKER or cert.get("evidence") != "CHECKED" or node["role"] == "compose":
        raise semantics.SemanticError("model-bound SMT needs the registered checker and a non-compose obligation")
    if not isinstance(payload, dict) or set(payload) - {"method", "invariants", "timeout_ms"}:
        raise semantics.SemanticError("model-bound SMT does not accept scripts, assumptions or supplied transitions")
    method = payload.get("method")
    if method not in {"combinational", "induction", "step"}:
        raise semantics.SemanticError("unsupported model-bound SMT proof method")
    limit = payload.get("timeout_ms", 5000)
    if type(limit) is not int or not 1 <= limit <= 60000:
        raise semantics.SemanticError("timeout_ms must be between 1 and 60000")
    guarantees = [g for g in node["provides"] if g["name"] == cert.get("goal")]
    if len(guarantees) != 1:
        raise semantics.SemanticError("ambiguous model-bound SMT guarantee")
    ctx = context(store, node["model"])
    predicate = binding_term(node, guarantees[0], store)
    if method != "step" and 1 in predicate.frames:
        raise semantics.SemanticError("a state lemma cannot refer to future values")
    if method == "step" and (1 not in predicate.frames or guarantees[0]["binding"]["kind"] == "btor-bad"):
        raise semantics.SemanticError("a step theorem must explicitly describe a transition, not certify a state property")
    strengthen = payload.get("invariants", [])
    if not isinstance(strengthen, list) or len(strengthen) > 128 or strengthen and method != "induction":
        raise semantics.SemanticError("strengthening invariants are supported only by induction")
    current_extra, next_extra = [], []
    for invariant in strengthen:
        now, nxt = ctx.lower(invariant), ctx.lower(invariant, 1)
        if now.sort != "Bool" or 1 in now.frames:
            raise semantics.SemanticError("strengthening must be a current-state Boolean formula")
        current_extra.append(now.value)
        next_extra.append(nxt.value)
    current_facts, next_facts, step_facts = [], [], []
    for ref in node.get("requires", []):
        if ref["node"] == node["id"] or ref["node"] not in nodes:
            raise semantics.SemanticError("missing or self-dependent semantic premise")
        dep = nodes[ref["node"]]
        if dep["model"] != node["model"]:
            raise semantics.SemanticError("a model-bound SMT premise must first transfer to the same model")
        matches = [g for g in dep["provides"] if g["name"] == ref["guarantee"]]
        if len(matches) != 1:
            raise semantics.SemanticError("ambiguous semantic premise")
        term = binding_term(dep, matches[0], store)
        dep_step = dep["certificate"].get("payload", {}).get("method") == "step"
        frame = ref.get("frame", "both")
        if frame not in {"current", "next", "both"}:
            raise semantics.SemanticError("premise frame must be current, next or both")
        if method == "combinational" and frame == "next":
            raise semantics.SemanticError("a state implication cannot use a next-only premise")
        if 1 in term.frames or dep_step:
            if method == "combinational":
                raise semantics.SemanticError("a state implication cannot assume a transition theorem")
            step_facts.append(term.value)
        else:
            # A proved state lemma is true at every reachable state.  Restricting
            # its use to one frame is a sound weakening; it is essential for
            # arithmetic invariants whose next-frame form re-introduces the
            # hardware quotient's bitwise OR.
            if frame in {"current", "both"}:
                current_facts.append(term.value)
            if frame in {"next", "both"}:
                next_facts.append(binding_term(dep, matches[0], store, 1).value)
    environment = ctx.constraints()
    initial = ctx.initial()
    # Catch an empty initial environment independently of the proposed lemma.
    feasibility = z3.Solver()
    feasibility.set(timeout=limit)
    feasibility.add(*(environment + initial))
    if feasibility.check() != z3.sat:
        raise semantics.SemanticError("model initialization/environment has no demonstrated satisfying state")
    checks = {}
    if method == "combinational":
        checks["implication"] = prove(environment + current_facts, predicate.value, "model implication", limit)
    elif method == "step":
        checks["step"] = prove(environment + ctx.constraints(1) + ctx.transition()
                               + current_facts + next_facts + step_facts,
                               predicate.value, "model step", limit)
    else:
        now = z3.And(predicate.value, *current_extra)
        nxt = z3.And(binding_term(node, guarantees[0], store, 1).value, *next_extra)
        checks["base"] = prove(environment + initial + current_facts, now, "model induction base", limit)
        checks["step"] = prove(environment + ctx.constraints(1) + ctx.transition()
                               + current_facts + next_facts + step_facts + [now],
                               nxt, "model induction step", limit)
    return {"accepted": True, "kind": FORMAT, "method": method,
            "model": node["model"], "checks": checks, "evidence": "CHECKED"}
