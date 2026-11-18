"""Offline LLM backend: the coding agent plays the role of the API-based LLM.

Two-pass usage, mirroring the real API backends' `run_api` contract:

  pass 1 (collect)
      NEUROABS_LLM_MODE=collect python3 -u src/main.py ...
    Every prompt is appended to $NEUROABS_LLM_PROMPTS and the identity
    abstraction (the original statement) is returned, so the gate trivially
    accepts and the run completes without any abstraction.

  pass 2 (replay)
      NEUROABS_LLM_MODE=replay  python3 -u src/main.py ...
    The hand-authored answers in $NEUROABS_LLM_ANSWERS are used where
    available; anything missing falls back to the identity abstraction.

Answers are keyed by the whitespace-normalised original statement, which is
stable across runs.
"""

import json
import os

from check import *

PROMPT_FILE = os.environ.get("NEUROABS_LLM_PROMPTS", "llm_prompts.jsonl")
ANSWER_FILE = os.environ.get("NEUROABS_LLM_ANSWERS", "llm_answers.json")
MODE = os.environ.get("NEUROABS_LLM_MODE", "replay")


def _norm(statement):
    return " ".join(statement.split())


def _load_answers():
    if not os.path.exists(ANSWER_FILE):
        return {}
    with open(ANSWER_FILE, "r") as handle:
        return json.load(handle)


def run_api(bot_name, message, original_statement, width_map, replacer, replace_input_map):
    answers = _load_answers()
    key = _norm(original_statement)

    with open(PROMPT_FILE, "a") as handle:
        handle.write(json.dumps({
            "statement": original_statement,
            "key": key,
            "answered": key in answers,
            "message": message,
        }) + "\n")

    content = answers.get(key, original_statement)
    try:
        result, replaced_response, replace_input, replace_input_map = check_implies(
            original_statement, content, width_map, replacer, replace_input_map)
    except Exception as error:
        # Mirror gpt_api.py: an unparsable or unsupported statement is skipped
        # rather than aborting the whole run.
        with open("authored_api_errors.txt", "a+") as handle:
            handle.write(original_statement + "\n")
            handle.write("gate failed: {0}\n\n".format(error))
        print("gate skipped statement: {0} ({1})".format(
            original_statement.strip()[:70], error))
        return None, None, None, replace_input_map
    return replaced_response, result, replace_input, replace_input_map