import sys, time, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
import z3
from z3 import BitVec, BitVecs, LShR, Solver, Not
from kernel import check_poly

print(f"z3 {z3.get_version_string()}")
print("\n[bad: raw BV one-step identity]")
for W in (8, 10, 12, 16):
    a, b = BitVecs('a b', W)
    s = Solver(); s.set(timeout=30000)
    s.add(Not((LShR(a,1)*(b<<1)) == a*b - (a & 1)*b))
    t0 = time.time(); r = s.check(); dt = time.time()-t0
    print(f"  W={W:2d}: {r}  ({dt:.2f}s)")

print("\n[good: purified ring identity at W=64 (kernel checker)]")
payload = {"W":64,
  "terms":[[1,["rs1","rs2"]],[-1,["x","s2"]],[-1,["bit","rs2"]]],
  "subst":{"rs1":[[2,["x"]],[1,["bit"]]],"s2":[[2,["rs2"]]]}}
t0=time.time(); ok=check_poly(payload); dt=time.time()-t0
print(f"  ring identity check: {'PASS' if ok else 'FAIL'} ({dt*1000:.3f}ms)")
