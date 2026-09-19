"""Unit tests for validate_decision() - no API calls, pure contract logic."""

import sys
from pathlib import Path

MAIN = Path("/Users/ab/Desktop/rag/main.py")
src = MAIN.read_text(encoding="utf-8")
head = src.partition("# ============================================================\n# TEST")[0]

ns = {}
try:
    exec(compile(head, str(MAIN), "exec"), ns)
except Exception as exc:
    print("EXEC FAILED:", type(exc).__name__, exc)
    sys.exit(1)

validate = ns["validate_decision"]
OK = ns["STATE_ANSWERABLE"]
ABSTAIN = ns["STATE_ABSTAIN"]
FAIL = ns["STATE_CONTRACT_FAILURE"]

# (raw reply, n_candidates, expected state, expected reason prefix)
CASES = [
    ("", 20, FAIL, "empty_response"),
    ("   ", 20, FAIL, "empty_response"),
    ("I don't have enough information to answer this.", 20, FAIL, "invalid_json"),
    ("[1, 2]", 20, FAIL, "not_a_json_object"),
    ('{"indices": []}', 20, FAIL, "missing_field: answerable"),
    ('{"answerable": true}', 20, FAIL, "missing_field: indices"),
    ('{"answerable": "yes", "indices": []}', 20, FAIL, "answerable_not_boolean"),
    ('{"answerable": 1, "indices": []}', 20, FAIL, "answerable_not_boolean"),
    ('{"answerable": true, "indices": 3}', 20, FAIL, "indices_not_list"),
    ('{"answerable": true, "indices": {"0": 1}}', 20, FAIL, "indices_not_list"),
    ('{"answerable": false, "indices": [1]}', 20, FAIL, "abstain_with_nonempty_indices"),
    ('{"answerable": true, "indices": [0, 1]}', 20, FAIL, "wrong_index_count"),
    ('{"answerable": true, "indices": [0, 1, 2, 3]}', 20, FAIL, "wrong_index_count"),
    ('{"answerable": true, "indices": [0, 1, 1]}', 20, FAIL, "duplicate_indices"),
    ('{"answerable": true, "indices": [0, 1, 20]}', 20, FAIL, "index_out_of_range"),
    ('{"answerable": true, "indices": [-1, 0, 1]}', 20, FAIL, "index_out_of_range"),
    ('{"answerable": true, "indices": [0, 1, "2"]}', 20, FAIL, "index_not_integer"),
    ('{"answerable": true, "indices": [true, 1, 2]}', 20, FAIL, "index_not_integer"),
    ('{"answerable": true, "indices": [0, 1.5, 2]}', 20, FAIL, "index_not_integer"),
    ('{"answerable": true, "indices": [0, 1, 2]}', 2, FAIL, "index_out_of_range"),
    # --- valid decisions ---
    ('{"answerable": true, "indices": [10, 3, 9]}', 20, OK, None),
    ('{"answerable": true, "indices": [0, 1, 2]}', 3, OK, None),
    ('{"answerable": false, "indices": []}', 20, ABSTAIN, None),
    ('  {"answerable": true, "indices": [2, 5, 7]}  ', 20, OK, None),
    # extra keys are not part of the enumerated failure list: ignored, not fatal
    ('{"answerable": true, "indices": [0, 1, 2], "note": "x"}', 20, OK, None),
]

fails = 0
for raw, n, want_state, want_prefix in CASES:
    state, indices, reason = validate(raw, n, k=3)
    bad = state != want_state
    if want_prefix is not None:
        bad = bad or not str(reason or "").startswith(want_prefix)
    if state == OK:
        bad = bad or indices != [int(x) for x in raw.split("[")[1].split("]")[0].split(",") if x.strip().isdigit()]
    else:
        bad = bad or indices != []
    if bad:
        fails += 1
    label = "PASS" if not bad else "FAIL"
    print(f"{label}  n={n:<3} {raw[:58]:<58} -> {state}"
          + (f" [{reason}]" if reason else ""))

print(f"\n{len(CASES) - fails}/{len(CASES)} contract cases behave as specified")
sys.exit(1 if fails else 0)
