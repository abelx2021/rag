"""Stage 2 (v4): joint-sufficiency instruction, benchmark re-annotated.

Groups now follow the corrected definition (vault_can_answer), not just type:
  34 genuinely answerable  (36 minus i01 and o03, which the corpus cannot support)
   6 genuinely unanswerable (4 'absent' + the 2 reclassified)

Usage: python3 eval/run_eval_v4.py 1,2      (pass numbers)
"""

import contextlib
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

RAG_DIR = Path("/Users/ab/Desktop/rag")
EVAL = RAG_DIR / "eval"

src = (RAG_DIR / "main.py").read_text(encoding="utf-8")
head, sep, _ = src.partition("# ============================================================\n# TEST")
if not sep:
    print("WARNING: TEST marker not found")
    sys.exit(2)

ns = {}
try:
    exec(compile(head, "main.py", "exec"), ns)
except Exception as exc:
    print("EXEC FAILED:", type(exc).__name__, exc)
    sys.exit(1)

KEY = lambda c: f"{c['document']}::{c['section']}"
OK, ABSTAIN, FAIL = ns["STATE_ANSWERABLE"], ns["STATE_ABSTAIN"], ns["STATE_CONTRACT_FAILURE"]
RE_TOKENS = re.compile(r"^Tokens:\s*(\d+) input", re.M)

chunks = ns["chunks"]
inventory = {KEY(c) for c in chunks}
spec = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))
questions = spec["questions"]
for q in questions:
    for e in q["expect"]:
        if e not in inventory:
            print("GROUND TRUTH MISMATCH:", q["id"], e)
            sys.exit(3)

answerable_q = [q for q in questions if q.get("vault_can_answer", True) and q["type"] != "absent"]
unanswerable_q = [q for q in questions if not (q.get("vault_can_answer", True)) or q["type"] == "absent"]
print(f"corpus {len(chunks)} chunks | SIBLING_K={ns['SIBLING_K']} FINAL_K={ns['FINAL_K']}")
print(f"benchmark: {len(answerable_q)} answerable + {len(unanswerable_q)} unanswerable")


def score(rows):
    real = [r for r in rows if r["group"] == "answerable"]
    unas = [r for r in rows if r["group"] == "unanswerable"]
    return {
        "merged_recall": sum(r["merged_hit"] for r in real),
        "answered": sum(r["delivered_expected"] for r in real),
        "false_abstention": [r["id"] for r in real if r["merged_hit"] and r["state"] != OK],
        "abstain_all": [r["id"] for r in real if r["state"] == ABSTAIN],
        "cf_real": [r["id"] for r in real if r["state"] == FAIL],
        "correct_abstention": sum(1 for r in unas if r["state"] == ABSTAIN),
        "false_answer": [r["id"] for r in unas if r["state"] == OK],
        "cf_unas": [r["id"] for r in unas if r["state"] == FAIL],
        "n_real": len(real), "n_unas": len(unas),
        "avg_cands": sum(r["n_candidates"] for r in rows) / len(rows),
        "avg_tokens": sum(r["tokens"] for r in rows) / len(rows),
    }


def report(tag, s):
    print(f"\n--- {tag}")
    print(f"  ANSWERABLE (n={s['n_real']})")
    print(f"    merged recall      {s['merged_recall']}/{s['n_real']}")
    print(f"    answered correctly {s['answered']}/{s['n_real']}")
    print(f"    false-abstention   {len(s['false_abstention'])}/{s['n_real']}  {s['false_abstention']}")
    print(f"    contract-failure   {len(s['cf_real'])}/{s['n_real']}")
    print(f"  UNANSWERABLE (n={s['n_unas']})")
    print(f"    correct abstention {s['correct_abstention']}/{s['n_unas']}")
    print(f"    false-answer       {len(s['false_answer'])}/{s['n_unas']}  {s['false_answer']}")
    print(f"    contract-failure   {len(s['cf_unas'])}/{s['n_unas']}")
    print(f"  EFFICIENCY  cands {s['avg_cands']:.1f}/q   tokens {s['avg_tokens']:,.0f}/q")


for pas in [int(x) for x in sys.argv[1].split(",")]:
    rows = []
    for q in questions:
        expect = set(q["expect"])
        vault_ok = q.get("vault_can_answer", True)
        group = "answerable" if (vault_ok and q["type"] != "absent") else "unanswerable"

        q_emb = ns["embed_query"](q["q"])
        vec = ns["search"](q_emb, k=ns["VECTOR_K"])
        seed = vec[0]["document"]
        siblings, graph = ns["expanded_search"](q_emb, seed, sibling_k=ns["SIBLING_K"], graph_k=ns["GRAPH_K"])
        merged = ns["merge_candidates"](vec, siblings, graph)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            decision = ns["rerank"](q["q"], merged, k=ns["FINAL_K"])
        m = RE_TOKENS.search(buf.getvalue())
        merged_keys = [KEY(c) for c in merged]
        delivered = [KEY(c) for c in decision["passages"]]

        rows.append({
            "id": q["id"], "group": group, "q": q["q"], "expect": sorted(expect),
            "state": decision["state"], "reason": decision["reason"], "raw": decision["raw"],
            "indices": decision["indices"], "n_candidates": decision["n_candidates"],
            "tokens": int(m.group(1)) if m else 0,
            "merged_hit": any(k in expect for k in merged_keys),
            "delivered_expected": bool(expect) and any(k in expect for k in delivered),
            "delivered": delivered,
        })

    s = score(rows)
    (EVAL / f"results_v4_p{pas}.json").write_text(
        json.dumps({"summary": s, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    report(f"v4 pass {pas}", s)

    print("\n  ledger:")
    for r in rows:
        if r["group"] == "answerable":
            mark = "answered" if r["delivered_expected"] else f"{r['state']}"
        else:
            mark = "abstained(correct)" if r["state"] == ABSTAIN else f"{r['state']} <-- PROBLEM"
        print(f"    {r['id']:<4} {mark:<20} {r['q'][:52]}")

# --- re-score the v3 run under the corrected labels for a true before/after ---
v3 = json.loads((EVAL / "results_v3.json").read_text(encoding="utf-8"))["rows"]
lookup = {q["id"]: q for q in questions}
for r in v3:
    q = lookup[r["id"]]
    r["group"] = "answerable" if (q.get("vault_can_answer", True) and q["type"] != "absent") else "unanswerable"
report("v3 (pre-fix) re-scored under corrected labels", score(v3))
