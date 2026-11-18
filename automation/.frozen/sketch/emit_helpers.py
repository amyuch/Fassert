#!/usr/bin/env python3
"""Emit helper assertions into a prepped fasten design.il from a sketch.

Design
------
The fasten runner's `prep.ys` produces a single flattened module (e.g.
`\\harness`) where every state element is an `$anyinit`/`$ff` cell with
explicit `\\D` and `\\Q` ports. Injecting a helper = appending a fresh
`$assert` cell whose `\\A` is a logic expression built from existing wires.
By the time `aig.ys` runs, each remaining `$assert` becomes a `bad` output,
so helper arms show up transparently as extra proof goals next to the real
property.

Arms
----
  --arm libre      counters from sketch recurrences: for each exact
                   increment counter, assert the design's own step relation
                       reset || D == Q + inc || D == Q
                   (Q and D are the register's current / next values).
  --arm control    syntactic non-helpers: same count of trivially true
                   asserts `D == D` over syntactically chosen registers.
  --arm both       both, labeled distinctly.

Name mapping
------------
Sketch register names are relative to module `testbench` (the case top).
The fasten rvfi harness instantiates testbench as `dut`, so the flattened
wire is `\\dut.<sketchname>`. `--prefix` supplies that (`dut` by default).

Usage
-----
  emit_helpers.py --il build/design.il --sketch sketch.json --arm libre \\
      --out build/design.helpers.il [--prefix dut] [--reset \\reset]
"""
from __future__ import annotations

import argparse
import re
import sys

CELL = "  attribute \\helper_arm \"{arm}\"\n{ind}cell {cell} \\{name}\n"
PORT = "{ind}  connect \\{port} {expr}\n"
PARAM = "{ind}    parameter \\{p} {v}\n"
END = "  end\n"


def parse_il(path):
    """Return (lines, {module_name: insert_line_idx}).

    Cells are inserted at `insert_line_idx` (before that line). The fasten
    prep flow's `write_rtlil` with this yosys closes the single module with a
    bare trailing `end` (no `endmodule`), so fall back to the last `end`."""
    with open(path) as f:
        lines = f.read().split('\n')
    mods = {}
    cur = None
    for i, ln in enumerate(lines):
        m = re.match(r'^module\s+(\S+)', ln)
        if m:
            cur = m.group(1)
            mods[cur] = None
            continue
        if ln.startswith('endmodule'):
            if cur is not None:
                mods[cur] = i
            cur = None
    if cur is not None and mods.get(cur) is None:
        # no endmodule: insert before the final bare `end`
        idx = None
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() == 'end':
                idx = i
                break
        mods[cur] = idx if idx is not None else len(lines)
    return lines, mods


def width_of(lines, name):
    """Width of a wire, given its bare (no leading backslash) RTLIL name."""
    pat = re.compile(r'^  wire(?: width (\d+))? \\' + re.escape(name) + r'(?:\s|$)')
    for ln in lines:
        m = pat.match(ln)
        if m:
            return int(m.group(1)) if m.group(1) else 1
    return 1


def const(width):
    return "{w}'0".format(w=width)


def new_sig(prefix):
    n = [0]
    wires = {}

    def sig(width=1):
        n[0] += 1
        name = '%s$h%d' % (prefix, n[0])
        wires[name] = max(int(width), 1)
        return name
    return sig, wires


def wire_decls(wires):
    out = []
    for name, w in wires.items():
        if w > 1:
            out.append('  wire width %d %s' % (w, name))
        else:
            out.append('  wire %s' % name)
    return out


def emit_step_helper(reg, q, d, w, inc, reset, arm, sig, asrt='$assert'):
    """Cells asserting reset || D == Q + inc || D == Q.

    q is a full RTLIL expression (leading backslash); d likewise; w the width.
    `asrt` selects the cell kind: `$assert` (extra bad) or `$assume`
    (constraint, for the assert-then-assume promotion)."""
    w = max(w, 1)
    one = '%d\'%d' % (w, abs(inc))
    sum_y = sig(w)
    sum_ = [
        CELL.format(arm=arm, ind='  ', cell='$add', name='helper.$add$' + reg) +
        PARAM.format(ind='  ', p='A_SIGNED', v=0) +
        PARAM.format(ind='  ', p='B_SIGNED', v=0) +
        PARAM.format(ind='  ', p='A_WIDTH', v=w) +
        PARAM.format(ind='  ', p='B_WIDTH', v=w) +
        PARAM.format(ind='  ', p='Y_WIDTH', v=w) +
        PORT.format(ind='  ', port='A', expr=q) +
        PORT.format(ind='  ', port='B', expr=one) +
        PORT.format(ind='  ', port='Y', expr=sum_y),
    ]
    eq_r = sig()
    eq_r_i = [
        CELL.format(arm=arm, ind='  ', cell='$eq', name='helper.$eqR$' + reg) +
        PARAM.format(ind='  ', p='A_SIGNED', v=0) +
        PARAM.format(ind='  ', p='B_SIGNED', v=0) +
        PARAM.format(ind='  ', p='A_WIDTH', v=w) +
        PARAM.format(ind='  ', p='B_WIDTH', v=w) +
        PARAM.format(ind='  ', p='Y_WIDTH', v=1) +
        PORT.format(ind='  ', port='A', expr=d) +
        PORT.format(ind='  ', port='B', expr=sum_y) +
        PORT.format(ind='  ', port='Y', expr=eq_r),
    ]
    eq_j = sig()
    eq_j_i = [
        CELL.format(arm=arm, ind='  ', cell='$eq', name='helper.$eqJ$' + reg) +
        PARAM.format(ind='  ', p='A_SIGNED', v=0) +
        PARAM.format(ind='  ', p='B_SIGNED', v=0) +
        PARAM.format(ind='  ', p='A_WIDTH', v=w) +
        PARAM.format(ind='  ', p='B_WIDTH', v=w) +
        PARAM.format(ind='  ', p='Y_WIDTH', v=1) +
        PORT.format(ind='  ', port='A', expr=d) +
        PORT.format(ind='  ', port='B', expr=q) +
        PORT.format(ind='  ', port='Y', expr=eq_j),
    ]
    or1 = sig()
    or1_i = [
        CELL.format(arm=arm, ind='  ', cell='$logic_or', name='helper.$or1$' + reg) +
        PARAM.format(ind='  ', p='A_SIGNED', v=0) +
        PARAM.format(ind='  ', p='B_SIGNED', v=0) +
        PARAM.format(ind='  ', p='A_WIDTH', v=1) +
        PARAM.format(ind='  ', p='B_WIDTH', v=1) +
        PARAM.format(ind='  ', p='Y_WIDTH', v=1) +
        PORT.format(ind='  ', port='A', expr=eq_r) +
        PORT.format(ind='  ', port='B', expr=eq_j) +
        PORT.format(ind='  ', port='Y', expr=or1),
    ]
    ok = sig()
    ok_i = [
        CELL.format(arm=arm, ind='  ', cell='$logic_or', name='helper.$or2$' + reg) +
        PARAM.format(ind='  ', p='A_SIGNED', v=0) +
        PARAM.format(ind='  ', p='B_SIGNED', v=0) +
        PARAM.format(ind='  ', p='A_WIDTH', v=1) +
        PARAM.format(ind='  ', p='B_WIDTH', v=1) +
        PARAM.format(ind='  ', p='Y_WIDTH', v=1) +
        PORT.format(ind='  ', port='A', expr=reset) +
        PORT.format(ind='  ', port='B', expr=or1) +
        PORT.format(ind='  ', port='Y', expr=ok),
    ]
    assert_cell = [
        CELL.format(arm=arm, ind='  ', cell=asrt, name='h_' + ('control#' if arm == 'control' else '') + 'libre_' + reg) +
        PORT.format(ind='  ', port='EN', expr="1'1") +
        PORT.format(ind='  ', port='A', expr=ok),
    ]
    cells = sum_ + eq_r_i + eq_j_i + or1_i + ok_i + assert_cell
    return [c + END for c in cells]


def eq_cells(arm, name, a_expr, b_expr, w, sig):
    y = sig()
    cell = [
        CELL.format(arm=arm, ind='  ', cell='$eq', name=name) +
        PARAM.format(ind='  ', p='A_SIGNED', v=0) +
        PARAM.format(ind='  ', p='B_SIGNED', v=0) +
        PARAM.format(ind='  ', p='A_WIDTH', v=w) +
        PARAM.format(ind='  ', p='B_WIDTH', v=w) +
        PARAM.format(ind='  ', p='Y_WIDTH', v=1) +
        PORT.format(ind='  ', port='A', expr=a_expr) +
        PORT.format(ind='  ', port='B', expr=b_expr) +
        PORT.format(ind='  ', port='Y', expr=y),
    ]
    return [c + END for c in cell], y


def or_cells(arm, name, a_expr, b_expr, sig):
    y = sig()
    cell = [
        CELL.format(arm=arm, ind='  ', cell='$logic_or', name=name) +
        PARAM.format(ind='  ', p='A_SIGNED', v=0) +
        PARAM.format(ind='  ', p='B_SIGNED', v=0) +
        PARAM.format(ind='  ', p='A_WIDTH', v=1) +
        PARAM.format(ind='  ', p='B_WIDTH', v=1) +
        PARAM.format(ind='  ', p='Y_WIDTH', v=1) +
        PORT.format(ind='  ', port='A', expr=a_expr) +
        PORT.format(ind='  ', port='B', expr=b_expr) +
        PORT.format(ind='  ', port='Y', expr=y),
    ]
    return [c + END for c in cell], y


def assert_cells(arm, name, a_expr, asrt='$assert'):
    cell = [
        CELL.format(arm=arm, ind='  ', cell=asrt, name=name) +
        PORT.format(ind='  ', port='EN', expr="1'1") +
        PORT.format(ind='  ', port='A', expr=a_expr),
    ]
    return [c + END for c in cell]


def lit(width, value):
    """RTLIL constant literal for `value` in `width` bits."""
    return "%d'%s" % (width, format(value & ((1 << width) - 1), '0%db' % width))


def emit_fsm_helper(reg, q, w, states, reset, arm, sig, asrt='$assert'):
    """Cells asserting reset || Q in {states} (a reachable-state bound).

    `states` are the distinct constants the register can be assigned, taken
    from its next-state cone; closure makes this a conjectured invariant that
    the driver's BMC gate must confirm."""
    w = max(w, 1)
    blocks = []
    acc = None
    for i, v in enumerate(states):
        cells, y = eq_cells(arm, 'helper.$fsm$%s$%d' % (reg, i),
                            q, lit(w, v), w, sig)
        blocks += cells
        if acc is None:
            acc = y
        else:
            cells, acc = or_cells(arm, 'helper.$fsmo$%s$%d' % (reg, i),
                                  acc, y, sig)
            blocks += cells
    cells, ok = or_cells(arm, 'helper.$fsmr$' + reg, reset, acc, sig)
    blocks += cells
    blocks += assert_cells(
        arm, 'h_' + ('control#' if arm == 'control' else '') + 'fsm_' + reg, ok,
        asrt)
    return blocks


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--il', required=True)
    ap.add_argument('--sketch')
    ap.add_argument('--arm', choices=['libre', 'control', 'both'], default='libre')
    ap.add_argument('--out', required=True)
    ap.add_argument('--prefix', default='dut')
    ap.add_argument('--reset', default='\\reset')
    ap.add_argument('--with-fsm', action='store_true',
                    help='also emit conjectured FSM state-set helpers '
                         '(unverified; needs a per-helper soundness gate)')
    ap.add_argument('--as-assume', action='store_true',
                    help='emit helpers as $assume (constraint) instead of '
                         '$assert (bad); use only for verified invariants')
    args = ap.parse_args()

    lines, mods = parse_il(args.il)
    if not mods:
        sys.exit('no modules found in %s' % args.il)
    # single-flattened-module assumption of the prep flow
    mod, mod_end = next(iter(mods.items()))
    sig, wires = new_sig(mod)

    def wire_for(name):
        full = (args.prefix + '.' + name) if args.prefix else name
        return '\\' + full

    if args.sketch:
        import json
        with open(args.sketch) as f:
            sketch = json.load(f)
        contracts = sketch.get('contracts', {})
        recur = contracts.get('recurrences', []) or []
        fsms = contracts.get('fsms', []) or []
    else:
        recur = []
        fsms = []

    blocks = []
    ASRT = '$assume' if args.as_assume else '$assert'
    if args.arm in ('libre', 'both'):
        injected = 0
        for r in recur:
            inc = r.get('increment')
            if inc not in (1, -1):
                continue
            reg = r['reg']
            q = wire_for(reg)
            d = find_d_wire(lines, q)
            if d is None:
                print('WARN: no D wire for %s (skipping)' % reg, file=sys.stderr)
                continue
            w = width_of(lines, (args.prefix + '.' + reg) if args.prefix else reg)
            cells = emit_step_helper(reg, q, d, w, inc,
                                     args.reset, 'libre', sig, ASRT)
            blocks.append('\n'.join(cells))
            injected += 1
        # FSM state-set invariants (sketch-only; not in the structural control).
        # OFF by default: the state set is derived from constants in the
        # next-state cone and is often incomplete, so these helpers can be
        # unsound until a per-helper gate is wired up.
        defs = build_defs(lines)
        nfsm = 0
        if args.with_fsm:
            for f in fsms:
                reg = f['reg']
                q = wire_for(reg)
                d = find_d_wire(lines, q)
                w = f.get('width') or width_of(
                    lines, (args.prefix + '.' + reg) if args.prefix else reg)
                if d is None:
                    print('WARN: no D wire for fsm %s (skipping)' % reg,
                          file=sys.stderr)
                    continue
                states = collect_cone_consts(defs, d, max(w, 1))
                if not states:
                    continue
                blocks.append('\n'.join(emit_fsm_helper(
                    reg, q, w, states, args.reset, 'libre', sig, ASRT)))
                nfsm += 1
        print('libre helpers injected: %d counters + %d fsms' % (injected, nfsm))

    if args.arm in ('control', 'both'):
        # Sketch-free control: a purely structural counter scan over the IL
        # (register's next-state function is `Q +- 1`), capped to the same
        # helper count as the libre arm. No sketch contracts are consulted.
        regs = collect_regs(lines)
        regs = {n: (q, d, width_of(lines, n)) for n, (q, d) in regs.items()}
        cand = detect_struct_counters(lines, regs)
        want = len(recur) if recur else len(cand)
        nctl = 0
        for name, inc in cand[:want]:
            q, d, w = regs[name]
            cells = emit_step_helper(name, q, d, w, inc,
                                     args.reset, 'control', sig, ASRT)
            blocks.append('\n'.join(cells))
            nctl += 1
        print('control helpers injected: %d (candidates=%d)' % (nctl, len(cand)))

    if not blocks:
        sys.exit('no helpers emitted; check sketch contracts / design wires')

    out = list(lines)
    body = wire_decls(wires) + [''] + blocks
    out.insert(mod_end, '\n'.join(body))
    with open(args.out, 'w') as f:
        f.write('\n'.join(out))
    print('wrote %s (module %s, +%d helper cells as %s)' % (
        args.out, mod,
        sum(b.count('$assert') + b.count('$assume') for b in blocks), ASRT))


def find_d_wire(lines, q_expr):
    """Inside an $anyinit/$ff cell whose \\Q connects to q_expr, return the \\D expr.

    q_expr is a backslash-prefixed RTLIL name. Cell type has no leading
    backslash; only user wire names do. Cell names like `$driver$...` also
    carry no backslash."""
    text = '\n'.join(lines)
    for cm in re.finditer(
            r'  cell \$anyinit (\S+)\n(.*?)\n  end', text, re.S):
        blk = cm.group(2)
        if re.search(r'connect \\Q ' + re.escape(q_expr) + r'\s*$', blk, re.M):
            m = re.search(r'connect \\D (\S+)\s*$', blk, re.M)
            return m.group(1) if m else None
    return None


def collect_regs(lines):
    """Map bare register name -> (q_expr, d_expr) for every $anyinit/$ff cell."""
    text = '\n'.join(lines)
    regs = {}
    for cm in re.finditer(
            r'  cell \$(?:anyinit|ff) (\S+)\n(.*?)\n  end', text, re.S):
        body = cm.group(2)
        qm = re.search(r'  connect \\Q (\S+)\s*$', body, re.M)
        if not qm:
            continue
        q = qm.group(1)
        dm = re.search(r'  connect \\D (\S+)\s*$', body, re.M)
        regs[q.lstrip('\\')] = (q, dm.group(1) if dm else None)
    return regs


def parse_const(tok):
    """Return the integer value of an RTLIL constant literal, else None.

    RTLIL literals look like `64'0000000000000001` or `1'1`; x/z bits are
    tolerated and treated as 0 so obvious constants still parse."""
    m = re.match(r"^(\d+)'([01xz]+)$", tok or '')
    if not m:
        return None
    try:
        return int(m.group(2).translate(str.maketrans('xz', '00')), 2)
    except ValueError:
        return None


def build_defs(lines):
    """Map each driven wire -> (cell type, {port: expr}) for all comb cells."""
    text = '\n'.join(lines)
    defs = {}
    for cm in re.finditer(r'  cell (\$\S+) (\S+)\n(.*?)\n  end', text, re.S):
        ctype, body = cm.group(1), cm.group(3)
        ports = dict(re.findall(r'connect \\(\w+) (\S+)', body))
        y = ports.get('Y')
        if y:
            defs[y] = (ctype, ports)
    return defs


def cone_increment(defs, d, q, depth=3):
    """Return +-inc if the D-cone of register q contains `q +- inc` with a
    constant inc, else None. Walks only through mux/add/sub/not cells so the
    search stays local to the register's next-state function."""
    if depth <= 0:
        return None
    e = defs.get(d)
    if not e:
        return None
    ctype, ports = e
    if ctype in ('$add', '$sub'):
        a, b = ports.get('A'), ports.get('B')
        ka, kb = parse_const(a), parse_const(b)
        if a == q and kb is not None:
            return kb if ctype == '$add' else -kb
        if b == q and ka is not None:
            return ka if ctype == '$add' else None
    for p in ('A', 'B'):
        expr = ports.get(p)
        if expr:
            r = cone_increment(defs, expr, q, depth - 1)
            if r is not None:
                return r
    return None


def detect_struct_counters(lines, regs):
    """Sketch-free: registers whose next-state function is `Q +- 1` or `Q`.

    regs maps a register's bare name -> (q_expr, d_expr, width). Returns a
    list of (name, inc) for candidates that structurally look like counters,
    independent of the sketch's semantic analysis. Candidates are conjectures:
    the driver gates them with a shallow BMC before trusting them."""
    defs = build_defs(lines)
    out = []
    for name, (q, d, _w) in regs.items():
        if not d:
            continue
        inc = cone_increment(defs, d, q, depth=8)
        if inc in (1, -1):
            out.append((name, inc))
    return out


def collect_cone_consts(defs, d, width, limit=64):
    """Distinct constants of `width` bits reachable in the D-cone of d.

    These are the values a register can be assigned, approximating its state
    set. Returns None if the set is too large to be a meaningful state bound."""
    out = set()

    def walk(expr, seen, depth):
        if depth <= 0 or expr in seen:
            return
        seen.add(expr)
        e = defs.get(expr)
        if not e:
            return
        _ctype, ports = e
        for p in ('A', 'B', 'S'):
            v = ports.get(p)
            if not v:
                continue
            m = re.match(r'^(\d+)\'([01xz]+)$', v)
            if m and int(m.group(1)) == width:
                out.add(int(m.group(2).translate(str.maketrans('xz', '00')), 2))
                if len(out) > limit:
                    return
            else:
                walk(v, seen, depth - 1)

    walk(d, set(), 8)
    return None if len(out) > limit else sorted(out)


if __name__ == '__main__':
    main()