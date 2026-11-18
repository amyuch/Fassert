"""Author the LLM answers for riscv_formal_add by hand (agent plays the LLM).

Scenario: verify ADD. Under the ADD encoding {7'b0,5'bx,5'bx,3'b0,5'bx,7'b0110011}
every decode register except `instr_add` is provably 0, so the natural
abstraction is to let those become free (`'bx`), which the gate then has to
prove sound. `instr_add` and the register file are left alone because they
carry the property being checked.

Rules applied to each collected prompt:
  * keep the statement unchanged when it is not a simple one-line assignment of
    a decode register / dead read-data arm (part-select or concatenation LHS,
    `$signed`, memory writes, `if (...)`, labelled arms, PC/counter updates);
  * keep constant assignments (`<= 0;`, `<= 1;`) unchanged;
  * replace the remaining dead decode registers with `'bx`;
  * replace the `reg_out` arms that an ADD never selects with `'bx`.
"""

import json
import os
import re
import sys

CASE = sys.argv[1] if len(sys.argv) > 1 else "riscv_formal/riscv_formal_add"

# Arms of `reg_out <= ...` that an ADD instruction never selects.
DEAD_REG_OUT_ARMS = (
    "pcpi_int_rd", "irq_pending", "irq_mask", "timer", "STACKADDR",
    "count_cycle[31:0]", "count_cycle[63:32]",
    "count_instr[31:0]", "count_instr[63:32]", "cpuregs_rs1",
)

# Never abstract these: they carry the property or cannot be freed.
KEEP_SIGNALS = ("instr_add", "cpuregs", "mem_rdata", "reg_op1", "reg_op2")

SKIP_MARKERS = ("$signed", "$unsigned", "cpuregs[", "if (", "count_cycle",
                "count_instr", "decoded_imm_j", "reg_pc", "alu_out_q")


def norm(statement):
    return " ".join(statement.split())


def author(statement):
    text = norm(statement)
    if not text.endswith(";"):
        return None
    body = text[:-1]
    if "<=" not in body:
        return None
    lhs, rhs = body.split("<=", 1)
    lhs, rhs = lhs.strip(), rhs.strip()

    if any(marker in text for marker in SKIP_MARKERS):
        return None
    if any(signal in lhs for signal in KEEP_SIGNALS):
        return None
    # part-select / concatenation on the left, or a labelled case arm
    if "[" in lhs or "{" in lhs or "}" in lhs or ":" in lhs or "}" in text:
        return None
    if not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", lhs):
        return None
    # concrete assignments carry no abstraction opportunity
    if re.fullmatch(r"[0-9]+", rhs):
        return None

    dead_decode = lhs.startswith("instr_") or lhs.startswith("is_")
    dead_reg_out = lhs == "reg_out" and any(arm in rhs for arm in DEAD_REG_OUT_ARMS)
    if dead_decode or dead_reg_out:
        return "{0} <= 'bx;".format(lhs)
    return None


def main():
    prompts = os.path.join(CASE, "llm_prompts.jsonl")
    answers = {}
    with open(prompts) as handle:
        for line in handle:
            record = json.loads(line)
            proposed = author(record["statement"])
            if proposed is not None:
                answers[record["key"]] = proposed

    out = os.path.join(CASE, "llm_answers.json")
    with open(out, "w") as handle:
        json.dump(answers, handle, indent=1, sort_keys=True)
    print("authored {0} abstractions -> {1}".format(len(answers), out))
    for key in sorted(answers)[:12]:
        print("  {0}\n    -> {1}".format(key[:88], answers[key]))


if __name__ == "__main__":
    main()