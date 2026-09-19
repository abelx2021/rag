"""Stage 2 (v3): structured reranker decision + strict validation.

Retrieval is frozen at SIBLING_K=3. The reranker now returns
{"answerable": bool, "indices": [...]} and the pipeline has three states:
ANSWERABLE / ABSTAIN / CONTRACT_FAILURE (a contract failure is never an
abstention). Metrics are reported per population:

  answerable   : merged recall, delivered top-3, false-abstention, contract-failure
  unanswerable : correct abstention, false-answer, contract-failure
  efficiency   : candidates/query, rerank input tokens/query
"""

import contextlib
import io
import json
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

chunks = ns["chunks"]
inventory = {KEY(c) for c in chunks}
questions = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]
for q in questions:
    for e in q["expect"]:
        if e not in inventory:
            print("GROUND TRUTH MISMATCH:", q["id"], e)
            sys.exit(3)

print(f"corpus {len(chunks)} chunks | SIBLING_K={ns['SIBLING_K']} VECTOR_K={ns['VECTOR_K']} "
      f"GRAPH_K={ns['GRAPH_K']} FINAL_K={ns['FINAL_K']}")

rows = []
tok_total = 0
for n, q in enumerate(questions, 1):
    expect = set(q["expect"])
    absent = q["type"] == "absent"

    q_emb = ns["embed_query"](q["q"])
    vec = ns["search"](q_emb, k=ns["VECTOR_K"])
    seed = vec[0]["document"]
    siblings, graph = ns["expanded_search"](q_emb, seed, sibling_k=ns["SIBLING_K"], graph_k=ns["GRAPH_K"])
    merged = ns["merge_candidates"](vec, siblings, graph)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        decision = ns["rerank"](q["q"], merged, k=ns["FINAL_K"])
    cap = buf.getvalue()
    import re
    m = re.search(r"^Tokens:\s*(\d+) input", cap, re.M)
    toks = int(m.group(1)) if m else 0
    tok_total += toks

    merged_keys = [KEY(c) for c in merged]
    delivered = [KEY(c) for c in decision["passages"]]

    row = {
        "id": q["id"], "type": q["type"], "absent": absent, "q": q["q"],
        "expect": sorted(expect),
        "state": decision["state"],
        "reason": decision["reason"],
        "raw": decision["raw"],
        "indices": decision["indices"],
        "n_candidates": decision["n_candidates"],
        "tokens": toks,
        "merged_hit": any(k in expect for k in merged_keys),
        "delivered": delivered,
        "delivered_expected": any(k in expect for k in delivered),
        "delivered_pos": next((i + 1 for i, k in enumerate(delivered) if k in expect), None),
        "seed": seed,
    }
    rows.append(row)

    flag = row["state"]
    if absent:
        flag += " (correct)" if row["state"] == ABSTAIN else " (FALSE ANSWER)" if row["state"] == OK else " (FAIL)"
    else:
        flag += " (correct)" if row["delivered_expected"] else " (NO ANSWER DELIVERED)"
    print(f"[{n:>2}/40] {row['id']:<4} {flag:<34} tok={toks:>5} cands={row['n_candidates']:>2} "
          f"raw={row['raw'][:60]}")

(EVAL / "results_v3.json").write_text(
    json.dumps({"rows": rows, "tokens": tok_total}, ensure_ascii=False, indent=1), encoding="utf-8")

real = [r for r in rows if not r["absent"]]
abst = [r for r in rows if r["absent"]]

print("\n" + "=" * 74)
print(f"ANSWERABLE QUESTIONS (n={len(real)})")
print(f"  merged recall            {sum(r['merged_hit'] for r in real)}/{len(real)}")
print(f"  delivered top-3          {sum(r['delivered_expected'] for r in real)}/{len(real)}")
fa = [r["id"] for r in real if r["merged_hit"] and r["state"] != OK]
print(f"  false-abstention         {len(fa)}/{len(real)}  {fa}")
cf = [r["id"] for r in real if r["state"] == FAIL]
print(f"  contract-failure         {len(cf)}/{len(real)}  {cf}")
miss = [r["id"] for r in real if r["state"] == OK and not r["delivered_expected"]]
print(f"  ANSWERABLE but wrong     {len(miss)}/{len(real)}  {miss}")
print(f"  state mix                {dict(Counter(r['state'] for r in real))}")

print(f"\nUNANSWERABLE QUESTIONS (n={len(abst)})")
ca = [r["id"] for r in abst if r["state"] == ABSTAIN]
fal = [r["id"] for r in abst if r["state"] == OK]
cf2 = [r["id"] for r in abst if r["state"] == FAIL]
print(f"  correct abstention       {len(ca)}/{len(abst)}  {ca}")
print(f"  false-answer             {len(fal)}/{len(abst)}  {fal}")
print(f"  contract-failure         {len(cf2)}/{len(abst)}  {cf2}")
for r in abst:
    print(f"    {r['id']} {r['state']:<17} raw={r['raw'][:64]}")
    if r["state"] == OK:
        print(f"        delivered: {r['delivered']}")

print("\nEFFICIENCY")
avg_c = sum(r["n_candidates"] for r in rows) / len(rows)
avg_t = tok_total / len(rows)
print(f"  candidates/query         {avg_c:.1f}")
print(f"  rerank input tok/query   {avg_t:,.0f}  (total {tok_total:,})")

v2 = json.loads((EVAL / "sweep_K3_p1.json").read_text(encoding="utf-8"))["summary"]
print("\nVS RETRIEVAL-ONLY BASELINE (sweep K=3, text-indices reranker)")
print(f"  merged recall   {v2['merged_recall']}/36 -> {sum(r['merged_hit'] for r in real)}/36")
print(f"  delivered top-3 {v2['final_top3']}/36 -> {sum(r['delivered_expected'] for r in real)}/36")
print(f"  tok/query       {v2['avg_tokens']:,.0f} -> {avg_t:,.0f}  ({(avg_t/v2['avg_tokens']-1):+.1%})")
print(f"  implicit empty results in old harness (x01/x02) were counted as hits; "
      f"the v3 states separate them")
