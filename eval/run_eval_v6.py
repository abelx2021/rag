"""Stage 2 (v6): stable joint-sufficiency prompt + deterministic identifier pre-gate.

Retrieval untouched (SIBLING_K=3). Runs N passes and checks the freeze target:

  retrieval    merged recall 35/35
  answerable   answered 35/35, false abstention 0/35
  unanswerable correct abstention 5/5, false answer 0/5
  interface    contract failures 0/40
  stability    identical STATES across all passes

State agreement and passage-order agreement are reported separately: ordering is
known to float, state must not.

Usage: python3 eval/run_eval_v6.py 1,2,3
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
questions = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]
for q in questions:
    for e in q["expect"]:
        if e not in inventory:
            print("GROUND TRUTH MISMATCH:", q["id"], e)
            sys.exit(3)

answerable_q = [q for q in questions if q.get("vault_can_answer", True) and q["type"] != "absent"]
unanswerable_q = [q for q in questions if not q.get("vault_can_answer", True) or q["type"] == "absent"]
passes = [int(x) for x in sys.argv[1].split(",")]
print(f"corpus {len(chunks)} chunks | SIBLING_K={ns['SIBLING_K']} FINAL_K={ns['FINAL_K']}")
print(f"benchmark: {len(answerable_q)} answerable + {len(unanswerable_q)} unanswerable "
      f"| passes: {passes}")

all_rows = {}
for pas in passes:
    rows = []
    tok_total = 0
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
        tok_total += int(m.group(1)) if m else 0

        merged_keys = [KEY(c) for c in merged]
        delivered = [KEY(c) for c in decision["passages"]]
        rows.append({
            "id": q["id"], "group": group, "q": q["q"], "expect": sorted(expect),
            "state": decision["state"], "gate": decision.get("gate"),
            "reason": decision["reason"], "raw": decision["raw"],
            "n_candidates": decision["n_candidates"],
            "tokens": int(m.group(1)) if m else 0,
            "merged_hit": any(k in expect for k in merged_keys),
            "delivered_expected": bool(expect) and any(k in expect for k in delivered),
            "delivered": delivered,
        })
    all_rows[pas] = rows
    (EVAL / f"results_v6_p{pas}.json").write_text(
        json.dumps({"rows": rows, "tokens": tok_total}, ensure_ascii=False, indent=1), encoding="utf-8")

    real = [r for r in rows if r["group"] == "answerable"]
    unas = [r for r in rows if r["group"] == "unanswerable"]
    print(f"\n--- pass {pas}")
    print(f"  merged recall      {sum(r['merged_hit'] for r in real)}/{len(real)}")
    print(f"  answered           {sum(r['delivered_expected'] for r in real)}/{len(real)}")
    print(f"  false-abstention   {[r['id'] for r in real if r['merged_hit'] and r['state'] != OK] or 0}/{len(real)}")
    print(f"  abstained (unans)  {sum(1 for r in unas if r['state'] == ABSTAIN)}/{len(unas)}")
    print(f"  false-answer       {[r['id'] for r in unas if r['state'] == OK] or 0}/{len(unas)}")
    print(f"  contract-failure   {sum(1 for r in rows if r['state'] == FAIL)}/40")
    print(f"  gates              {dict(Counter(r['gate'] for r in rows))}")
    print(f"  tokens             {tok_total:,} total, {tok_total/40:,.0f}/q")

# ---------------- stability ----------------
print("\n" + "=" * 74)
print("STABILITY")
state_sets = {q["id"]: {all_rows[p][i]["state"] for p in passes}
              for i, q in enumerate(questions) if False}
state_sets = {}
order_sets = {}
for i, q in enumerate(questions):
    state_sets[q["id"]] = [next(r for r in all_rows[p] if r["id"] == q["id"])["state"] for p in passes]
    order_sets[q["id"]] = [next(r for r in all_rows[p] if r["id"] == q["id"])["delivered"] for p in passes]

state_unstable = {i: s for i, s in state_sets.items() if len(set(s)) > 1}
state_stable_n = len(state_sets) - len(state_unstable)
print(f"  state agreement     {state_stable_n}/{len(state_sets)} questions identical across all {len(passes)} passes")
print(f"  state disagreements {state_unstable or 'none'}")

order_diff = {i: v for i, v in order_sets.items() if len({tuple(x) for x in v}) > 1}
set_only = {i: v for i, v in order_diff.items() if len({frozenset(x) for x in v}) == 1}
print(f"  passage order       {len(order_diff)} questions differ between passes "
      f"({len(set_only)} of them are the same SET in a different ORDER)")
for i, v in order_diff.items():
    print(f"    {i}: {' | '.join(str(x) for x in v)}")

# ---------------- acceptance ----------------
print("\n" + "=" * 74)
print("FREEZE TARGET")
real0 = [r for r in all_rows[passes[0]] if r["group"] == "answerable"]
unas0 = [r for r in all_rows[passes[0]] if r["group"] == "unanswerable"]
checks = [
    ("retrieval  merged recall 35/35", all(sum(r["merged_hit"] for r in [x for x in all_rows[p] if x["group"] == "answerable"]) == 35 for p in passes)),
    ("answerable answered 35/35", all(sum(r["delivered_expected"] for r in [x for x in all_rows[p] if x["group"] == "answerable"]) == 35 for p in passes)),
    ("answerable false abstention 0/35", all(not [r for r in all_rows[p] if r["group"] == "answerable" and r["merged_hit"] and r["state"] != OK] for p in passes)),
    ("unanswerable correct abstention 5/5", all(sum(1 for r in all_rows[p] if r["group"] == "unanswerable" and r["state"] == ABSTAIN) == 5 for p in passes)),
    ("unanswerable false answer 0/5", all(not [r for r in all_rows[p] if r["group"] == "unanswerable" and r["state"] == OK] for p in passes)),
    ("interface contract failures 0/40", all(not [r for r in all_rows[p] if r["state"] == FAIL] for p in passes)),
    (f"stability identical states {len(passes)}/{len(passes)} passes", not state_unstable),
]
for label, ok in checks:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")
print("\nVERDICT:", "FREEZE" if all(ok for _, ok in checks) else "DO NOT FREEZE")
