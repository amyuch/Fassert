#!/usr/bin/env python3
"""B0-B4 helper-ablation driver for the rvfi (AIG) family.

Operates on a fasten `suite_v0` build directory (which already contains the
prepped `design.il`, `aig.ys` and a baseline `design.aig`). For every arm it
prepares the design, re-synthesises the AIG, runs one engine under a fixed
budget, and records a per-arm result.json.

Arms
----
  b0   baseline: prepped design, no helpers.
  b1   full / vocabulary helpers from the sketch (emit_helpers --arm libre).
  b2   decomposition-only: reserved (cut-based) -- currently recorded as
       'skipped'.
  b3   full (decomposition + helpers): reserved -- 'skipped'.
  b4   control: same helper count, synthesised without the sketch
       (emit_helpers --arm control).

Usage
-----
  ablate.py --build /path/to/results/suite_v0/nerv_mcycle \\
            --sketch /tmp/.../nerv.sketch.json \\
            --arms b0,b1,b4 --engine abc_pdr --limit 300
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FASTEN_RUN = os.environ.get(
    'FASTEN_RUN', '/home/AM2/sec/cur_work/fasten/benchmarks/run')
sys.path.insert(0, FASTEN_RUN)

from runner import (ABC, engine_cmd, parse_engine_log, verdict_from,  # noqa: E402
                    parse_aig_header)
from emit_helpers import parse_il  # noqa: E402

ABC_SUMMARY = re.compile(
    r'All\s*=\s*(\d+)\.\s*Proved\s*=\s*(\d+)\.\s*Disproved\s*=\s*(\d+)\.'
    r'\s*Undecided\s*=\s*(\d+)\.\s*Time\s*=\s*([\d.]+)\s*sec')
# abc pdr prints progress as "<frame> : <counters...> <time> sec"; the
# runner's own frame regex lacks re.MULTILINE, so recover it here.
PDR_PROGRESS = re.compile(r'^\s*(\d+)\s*:.*?([\d.]+)\s*sec',
                          re.MULTILINE)


def parse_prove(engine, text):
    parsed = parse_engine_log(engine, text)
    if 'frames' not in parsed:
        frames = [int(m.group(1)) for m in PDR_PROGRESS.finditer(text)]
        if frames:
            parsed['frames'] = max(frames)
    return parsed


YOSYS = os.environ.get('YOSYS_BIN', 'yosys')
ABC_BIN = os.environ.get('ABC_BIN', 'yosys-abc')

# "Output 0 of miter "x" was asserted in frame 2."
BMC_ASSERT = re.compile(r'Output\s+(\d+)\s+of\s+.*?asserted\s+in\s+frame\s+(\d+)')
BMC_NONE = re.compile(r'No output asserted in (\d+) frames')


def bmc_gate(aig_path, depth, timeout=180):
    """Shallow BMC soundness gate: does any bad fire within `depth` frames?

    Helpers are injected as extra `bad` outputs after the real property, so a
    lone assertion here (when the baseline is quiet) means a helper is not an
    invariant of the design."""
    cmd = [ABC_BIN, '-c',
           'read_aiger %s; fold; strash; bmc3 -F %d' % (aig_path, depth)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {'depth': depth, 'result': 'timeout'}
    text = (r.stdout or '') + (r.stderr or '')
    m = BMC_ASSERT.search(text)
    if m:
        return {'depth': depth, 'result': 'asserted',
                'output': int(m.group(1)), 'frame': int(m.group(2))}
    if BMC_NONE.search(text):
        return {'depth': depth, 'result': 'clean'}
    return {'depth': depth, 'result': 'unknown'}


def aig_ys_template(build):
    with open(os.path.join(build, 'aig.ys')) as f:
        return f.read()


def make_aig(build, il_path, aig_path, yosys_bin=YOSYS, timeout=1800):
    """Run the case's aig.ys with the read/write paths redirected."""
    tmpl = aig_ys_template(build)
    tmpl = re.sub(r'^read_rtlil\s+\S+', 'read_rtlil ' + il_path, tmpl,
                  count=1, flags=re.MULTILINE)
    tmpl = re.sub(r'^write_aiger\s+[^\n]*\S+', '', tmpl, count=1,
                  flags=re.MULTILINE)
    tmpl = tmpl.rstrip() + '\nwrite_aiger -I -B -zinit %s\n' % aig_path
    ys = os.path.join(build, 'ablation_%s.ys' % os.path.basename(aig_path))
    with open(ys, 'w') as f:
        f.write(tmpl)
    log = os.path.join(build, 'ablation_%s.log' % os.path.basename(aig_path))
    r = subprocess.run([yosys_bin, '-q', '-s', ys], cwd=build, timeout=timeout,
                       stdout=open(log, 'w'), stderr=subprocess.STDOUT)
    if r.returncode != 0 or not os.path.exists(aig_path):
        return None, log
    return parse_aig_header(aig_path), log


def prove(build, aig_path, engine, limit):
    log = os.path.join(build, 'ablation_%s_%s.log' %
                       (os.path.basename(aig_path), engine))
    if engine.startswith('ric3'):
        sys.exit('ric3 needs a btor model; not wired into the ablation yet')
    cmd = engine_cmd(engine, aig_path)
    t0 = time.time()
    with open(log, 'w') as f:
        p = subprocess.Popen(cmd, cwd=build, stdout=f, stderr=subprocess.STDOUT)
        try:
            p.wait(timeout=limit)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()
            rc = 124
    wall = time.time() - t0
    text = open(log, errors='ignore').read()
    parsed = parse_prove(engine, text)
    return dict(verdict=verdict_from(parsed, rc), time_s=round(wall, 2),
                returncode=rc, limit_s=limit, **parsed), log


def run_arm(build, sketch, arm, engine, limit, prefix, gate_depth=0):
    res = {'arm': arm, 'engine': engine, 'limit_s': limit}
    il = os.path.join(build, 'design.il')
    if arm == 'b0':
        il_use = il
    elif arm in ('b1', 'b4'):
        helper_arm = 'libre' if arm == 'b1' else 'control'
        il_use = os.path.join(build, 'design.%s.il' % arm)
        cmd = [sys.executable, os.path.join(HERE, 'emit_helpers.py'),
               '--il', il, '--sketch', sketch or '', '--arm', helper_arm,
               '--out', il_use, '--prefix', prefix]
        subprocess.run(cmd, check=True)
    else:
        res['verdict'] = 'skipped'
        res['note'] = 'decomposition arms not implemented yet'
        return res

    aig = os.path.join(build, 'design.%s.aig' % arm)
    header, alog = make_aig(build, il_use, aig)
    if header is None:
        res['verdict'] = 'error'
        res['error'] = 'aig synthesis failed'
        res['aig_log'] = alog
        return res
    res['aig'] = header
    if gate_depth:
        res['gate'] = bmc_gate(aig, gate_depth)
    p, plog = prove(build, aig, engine, limit)
    res.update(p)
    res['engine_log'] = plog
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--build', required=True)
    ap.add_argument('--sketch')
    ap.add_argument('--arms', default='b0,b1,b4')
    ap.add_argument('--engine', default='abc_pdr')
    ap.add_argument('--limit', type=int, default=300)
    ap.add_argument('--prefix', default='dut')
    ap.add_argument('--gate', type=int, default=0,
                    help='shallow BMC depth for the helper soundness gate '
                         '(0 = disabled)')
    args = ap.parse_args()

    arms = [a.strip() for a in args.arms.split(',') if a.strip()]
    out = []
    for arm in arms:
        print('=== arm %s (%s, %ss) ===' % (arm, args.engine, args.limit))
        r = run_arm(args.build, args.sketch, arm, args.engine, args.limit,
                    args.prefix, gate_depth=args.gate)
        a = r.get('aig') or {}
        g = r.get('gate') or {}
        print('    verdict=%s time=%ss frames=%s bads=%s ands=%s gate=%s' % (
            r.get('verdict'), r.get('time_s'), r.get('frames'),
            a.get('bads'), a.get('ands'), g.get('result')))
        out.append(r)

    # Interpret the gate: if the baseline is quiet but a helper arm fires, the
    # extra assertion is not a design invariant and the arm is unsound.
    base = next((x.get('gate') for x in out if x['arm'] == 'b0'), None)
    if base:
        for r in out:
            g = r.get('gate')
            if not g or r['arm'] == 'b0':
                continue
            g['baseline'] = base.get('result')
            g['sound'] = not (base.get('result') == 'clean'
                              and g.get('result') == 'asserted')

    path = os.path.join(args.build, 'ablation.json')
    with open(path, 'w') as f:
        json.dump(out, f, indent=2)
    print('wrote', path)


if __name__ == '__main__':
    main()