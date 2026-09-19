"""Stage 2 (v5): named-artifact clause added; labels finalised at 35/5.

Writes results_v5_p{N}.json and re-scores the v4 run (pre-clause) under the same
labels so the before/after is apples-to-apples.

Usage: python3 eval/run_eval_v5.py 1,2
"""

import contextlib
import io
import json
import re
import sys
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
questions = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]
for q in questions:
    for e in q["expect"]:
        if e not in inventory:
            print("GROUND TRUTH MISMATCH:", q["id"], e)
            sys.exit(3)

answerable_q = [q for q in questions if q.get("vault_can_answer", True) and q["type"] != "absent"]
unanswerable_q = [q for q in questions if not q.get("vault_can_answer", True) or q["type"] == "absent"]
print(f"corpus {len(chunks)} chunks | SIBLING_K={ns['SIBLING_K']} VECTOR_K={ns['VECTOR_K']} "
      f"GRAPH_K={ns['GRAPH_K']} FINAL_K={ns['FINAL_K']}")
print(f"benchmark: {len(answerable_q)} answerable + {len(unanswerable_q)} unanswerable")
print(f"  answerable ids: {[q['id'] for q in answerable_q]}")
print(f"  unanswerable ids: {[q['id'] for q in unanswerable_q]}")

# questions that name an identifier/artefact: the clause's blast radius
CONTROLS = {"i01": "must ABSTAIN (INT-PUC-006 absent from corpus)",
            "i02": "must ANSWERABLE (SEC-IAM-005 literal in corpus)",
            "i03": "must ANSWERABLE (RSK-04 literal in corpus)",
            "i05": "must ANSWERABLE (DEC-CNF-01 literal in corpus)"}


def score(rows):
    real = [r for r in rows if r["group"] == "answerable"]
    unas = [r for r in rows if r["group"] == "unanswerable"]
    return {
        "merged_recall": sum(r["merged_hit"] for r in real),
        "answered": sum(r["delivered_expected"] for r in real),
        "ans_but_wrong": [r["id"] for r in real if r["state"] == OK and not r["delivered_expected"]],
        "false_abstention": [r["id"] for r in real if r["merged_hit"] and r["state"] != OK],
        "cf_real": [r["id"] for r in real if r["state"] == FAIL],
        "correct_abstention": sum(1 for r in unas if r["state"] == ABSTAIN),
        "false_answer": [r["id"] for r in unas if r["state"] == OK],
        "cf_unas": [r["id"] for r in unas if r["state"] == FAIL],
        "n_real": len(real), "n_unas": len(unas),
        "avg_cands": sum(r["n_candidates"] for r in rows) / len(rows),
        "avg_tokens": sum(r["tokens"] for r in rows) / len(rows),
    }


def report(tag, s, rows=None):
    print(f"\n--- {tag}")
    print(f"  ANSWERABLE (n={s['n_real']})")
    print(f"    merged recall      {s['merged_recall']}/{s['n_real']}")
    print(f"    answered correctly {s['answered']}/{s['n_real']}")
    print(f"    answered-but-wrong {len(s['ans_but_wrong'])}/{s['n_real']}  {s['ans_but_wrong']}")
    print(f"    false-abstention   {len(s['false_abstention'])}/{s['n_real']}  {s['false_abstention']}")
    print(f"    contract-failure   {len(s['cf_real'])}/{s['n_real']}")
    print(f"  UNANSWERABLE (n={s['n_unas']})")
    print(f"    correct abstention {s['correct_abstention']}/{s['n_unas']}")
    print(f"    false-answer       {len(s['false_answer'])}/{s['n_unas']}  {s['false_answer']}")
    print(f"    contract-failure   {len(s['cf_unas'])}/{s['n_unas']}")
    print(f"  EFFICIENCY  cands {s['avg_cands']:.1f}/q   tokens {s['avg_tokens']:,.0f}/q")
    if rows:
        print("  named-artifact controls:")
        for cid, want in CONTROLS.items():
            r = next((x for x in rows if x["id"] == cid), None)
            if r:
                print(f"    {cid}: {r['state']:<12} ({want})")


for pas in [int(x) for x in sys.argv[1].split(",")]:
    rows = []
    for q in questions:
        expect = set(q["expect"])
        group = "answerable" if (q.get("vault_can_answer", True) and q["type"] != "absent") else "unanswerable"

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
    (EVAL / f"results_v5_p{pas}.json").write_text(
        json.dumps({"summary": s, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    report(f"v5 pass {pas} (named-artifact clause)", s, rows)
    print("\n  ledger:")
    for r in rows:
        if r["group"] == "answerable":
            mark = "answered" if r["delivered_expected"] else f"{r['state']} <-- CHECK"
        else:
            mark = "abstained" if r["state"] == ABSTAIN else f"{r['state']} <-- FALSE ANSWER"
        print(f"    {r['id']:<4} {mark:<24} {r['q'][:50]}")

# --- pre-clause baseline (v4) under the final labels ---
v4 = json.loads((EVAL / "results_v4_p1.json").read_text(encoding="utf-8"))["rows"]
lookup = {q["id"]: q for q in questions}
for r in v4:
    q = lookup[r["id"]]
    r["group"] = "answerable" if (q.get("vault_can_answer", True) and q["type"] != "absent") else "unanswerable"
report("v4 pass 1 (pre-clause) re-scored under final labels", score(v4), v4)
