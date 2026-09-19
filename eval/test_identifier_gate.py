"""Unit tests for the deterministic identifier pre-gate - no API calls.

Two properties matter and both are objective:
  1. the grammar fires on identifiers and does NOT fire on ordinary concepts
  2. identifier presence in the corpus is a fact, not a model opinion
"""

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

extract = ns["extract_identifiers"]
chunks = ns["chunks"]
corpus = "\n".join(c["text"] for c in chunks).upper()

EXTRACTION = [
    ("What does INT-PUC-006 require?", ["INT-PUC-006"]),
    ("What is SEC-IAM-005?", ["SEC-IAM-005"]),
    ("What is risk RSK-04 and how is it mitigated?", ["RSK-04"]),
    ("What is DEC-CNF-01?", ["DEC-CNF-01"]),
    ("What is the architectural decision ADR-001?", ["ADR-001"]),
    ("Which Sprint 0 decisions must be closed before committing release dates?", []),
    ("How many epics does the initial backlog contain?", []),
    # ordinary named concepts must NOT be identifiers
    ("What is the digital file (fascicolo di progetto) in IANUS?", []),
    ("What arguments ruled out a microservices architecture?", []),
    ("What are the statuses a project can have in IANUS?", []),
    ("Which schemas make up the IANUS database?", []),
    # dedup + order preservation
    ("compare DEC-CNF-01 with INT-PUC-006 and again DEC-CNF-01", ["DEC-CNF-01", "INT-PUC-006"]),
]

PRESENCE = [
    ("INT-PUC-006", False),   # i01: must abstain - the corpus never carries it
    ("SEC-IAM-005", True),    # i02: control, must stay answerable
    ("RSK-04", True),         # i03: control
    ("DEC-CNF-01", True),     # i05: control
    ("ADR-001", True),        # d16: control
    ("REQ-CORE-003", False),  # raw-only identifier, absent from the wiki
]

fails = 0
print("grammar: extraction")
for text, want in EXTRACTION:
    got = extract(text)
    ok = got == want
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {text[:56]:<56} -> {got}")

print("\npresence in the indexed corpus (a fact, not a judgement)")
for ident, want in PRESENCE:
    present = ident in corpus
    ok = present == want
    fails += 0 if ok else 1
    print(f"  {'PASS' if ok else 'FAIL'}  {ident:<14} present={present:<5} expected={want}")

print(f"\n{len(EXTRACTION) + len(PRESENCE) - fails}/{len(EXTRACTION) + len(PRESENCE)} identifier-gate cases behave as specified")
sys.exit(1 if fails else 0)
