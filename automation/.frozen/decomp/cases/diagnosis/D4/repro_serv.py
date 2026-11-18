import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
import z3
from z3 import BitVec, BitVecVal, Solver, Not, ForAll, Implies, And
import s5_temporal as S5

XLEN=32; AW=XLEN+1
print(f"z3 {z3.get_version_string()}  (SERV bit-serial ADD)")
print("\n[bad: one-step/global result assertion at k=0]")
a,b = BitVec('a',XLEN), BitVec('b',XLEN)
# at k=0 partial=0, carry=0; asserting partial==a+b is false for some operands
s=Solver(); s.set(timeout=10000)
s.add(Not((BitVecVal(0,AW)) == (z3.ZeroExt(1,a)+z3.ZeroExt(1,b))))
t0=time.time(); r=s.check(); print(f"  one-step partial==a+b: {r} ({time.time()-t0:.2f}s)")

print("\n[good: macro-step invariant + completion]")
r1=S5.base_case(); print("  base:", r1)
r2,dt=S5.invariant_step(); print(f"  step: {r2} ({dt*1000:.2f} ms)")
r3,dt=S5._completion_check(); print(f"  exit: {r3} ({dt*1000:.2f} ms)")
