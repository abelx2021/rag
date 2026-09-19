"""Stage 2 (v2): same 40 questions, same ground truth, new pipeline.

v2 main.py adds sibling expansion: expanded_search() returns (siblings, graph) where
siblings = every chunk of the seed document. merge_candidates() now takes 3 groups.
This script records which stage found the correct chunk and diffs against the
v1 baseline in eval/results.json.
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

MAIN = RAG_DIR / "main.py"
src = MAIN.read_text(encoding="utf-8")
head, sep, _tail = src.partition("# ============================================================\n# TEST")
if not sep:
    print("WARNING: TEST marker not found; refusing to exec the whole file")
    sys.exit(2)

ns = {}
try:
    exec(compile(head, str(MAIN), "exec"), ns)
except Exception as exc:
    print("EXEC FAILED:", type(exc).__name__, exc)
    sys.exit(1)

chunks = ns["chunks"]
search = ns["search"]
expanded_search = ns["expanded_search"]
merge_candidates = ns["merge_candidates"]
rerank = ns["rerank"]
embed_query = ns["embed_query"]

KEY = lambda c: f"{c['document']}::{c['section']}"
inventory = {KEY(c) for c in chunks}

spec = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))
questions = spec["questions"]

bad = [(q["id"], e) for q in questions for e in q["expect"] if e not in inventory]
if bad:
    print("GROUND TRUTH MISMATCH (chunking changed?):")
    for qid, e in bad:
        print(f"  {qid}: {e}")
    sys.exit(3)

print(f"corpus unchanged: {len(chunks)} chunks")
records = []
tok_in = tok_out = 0
RE_DEEPSEEK = re.compile(r"^DeepSeek:\s*(.*)$", re.M)
RE_TOKENS = re.compile(r"^Tokens:\s*(\d+) input \+ (\d+) output", re.M)

for n, q in enumerate(questions, 1):
    expect = set(q["expect"])
    absent = q["type"] == "absent"

    q_emb = embed_query(q["q"])
    vec = search(q_emb, k=ns["VECTOR_K"])
    seed = vec[0]["document"]
    siblings, graph = expanded_search(
        q_emb, seed, sibling_k=ns["SIBLING_K"], graph_k=ns["GRAPH_K"]
    )
    merged = merge_candidates(vec, siblings, graph)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        final = rerank(q["q"], merged, k=ns["FINAL_K"])
    captured = buf.getvalue()
    m = RE_TOKENS.search(captured)
    if m:
        tok_in += int(m.group(1))
        tok_out += int(m.group(2))
    raw = (RE_DEEPSEEK.search(captured) or [None, ""])[1].strip()

    vec_keys = [KEY(c) for c in vec]
    sib_keys = [KEY(c) for c in siblings]
    graph_keys = [KEY(c) for c in graph]
    merged_keys = [KEY(c) for c in merged]
    final_keys = [KEY(c) for c in final]

    vec_ranks = [i + 1 for i, k in enumerate(vec_keys) if k in expect]
    sib_ranks = [i + 1 for i, k in enumerate(sib_keys) if k in expect]
    graph_ranks = [i + 1 for i, k in enumerate(graph_keys) if k in expect]

    # which stage surfaced the correct chunk first (in merge order)
    found_by = None
    for label, keys in (("vector", vec_keys), ("sibling", sib_keys), ("graph", graph_keys)):
        if any(k in expect for k in keys):
            found_by = label
            break

    rec = {
        "id": q["id"],
        "type": q["type"],
        "q": q["q"],
        "expect": sorted(expect),
        "seed": seed,
        "seed_is_expected_doc": any(e.split("::")[0] == seed for e in expect) if expect else None,
        "vector_top10": [{"key": k, "score": round(c["score"], 4)} for k, c in zip(vec_keys, vec)],
        "siblings": [{"key": k, "score": round(c["score"], 4)} for k, c in zip(sib_keys, siblings)],
        "graph_top10": [{"key": k, "score": round(c["score"], 4)} for k, c in zip(graph_keys, graph)],
        "merged_count": len(merged),
        "rerank_raw": raw,
        "rerank_indices": [int(i) for i in re.findall(r"\d+", raw)],
        "final3": [
            {
                "key": KEY(c),
                "source": c.get("source"),
                "score": round(c["score"], 4),
                "rerank_input_rank": c.get("rerank_input_rank"),
            }
            for c in final
        ],
        "vec_best_rank": min(vec_ranks) if vec_ranks else None,
        "sib_best_rank": min(sib_ranks) if sib_ranks else None,
        "graph_hit": bool(graph_ranks),
        "merged_hit": any(k in expect for k in merged_keys),
        "final_hit": any(k in expect for k in final_keys),
        "found_by": found_by,
        "best_vector_score": round(max(c["score"] for c in vec), 4),
        "tokens_in": int(m.group(1)) if m else 0,
    }
    rec["vec_hit"] = rec["vec_best_rank"] is not None
    records.append(rec)

    flag = "OK " if (absent or rec["final_hit"]) else "MISS"
    pos = [i + 1 for i, f in enumerate(rec["final3"]) if f["key"] in expect]
    print(
        f"[{n:>2}/{len(questions)}] {flag} {q['id']:<4} {q['type']:<9} "
        f"vec#{rec['vec_best_rank']}/sib#{rec['sib_best_rank']}/graph={rec['graph_hit']} "
        f"merged={rec['merged_count']:>2} final@{pos or '-'} by={rec['found_by']} "
        f"tok={rec['tokens_in']}"
    )

(EVAL / "results_v2.json").write_text(
    json.dumps({"records": records, "tokens": {"input": tok_in, "output": tok_out}},
               ensure_ascii=False, indent=1), encoding="utf-8")

# ---------------- before / after ----------------
v1 = {r["id"]: r for r in json.loads((EVAL / "results.json").read_text(encoding="utf-8"))["records"]}
v1tok = json.loads((EVAL / "results.json").read_text(encoding="utf-8"))["tokens"]["input"]
v2 = {r["id"]: r for r in records}

real = [r for r in records if r["type"] != "absent"]
real1 = [r for r in v1.values() if r["type"] != "absent"]
absent = [r for r in records if r["type"] == "absent"]

def agg(rs):
    return (
        sum(r["final_hit"] for r in rs),
        sum(r["vec_hit"] for r in rs),
        sum(r["merged_hit"] for r in rs),
    )

h1, v1h, m1 = agg(real1)
h2, v2h, m2 = agg(real)

print("\n" + "=" * 74)
print("BEFORE / AFTER (36 answerable questions)")
print(f"  final top-3 hit      v1 {h1}/36   ->  v2 {h2}/36")
print(f"  vector top-10 hit    v1 {v1h}/36   ->  v2 {v2h}/36")
print(f"  merged recall        v1 {m1}/36   ->  v2 {m2}/36")
print(f"  rerank input tokens  v1 {v1tok:,}  ->  v2 {tok_in:,}  "
      f"({v1tok/40:,.0f} -> {tok_in/40:,.0f} per question, "
      f"{(tok_in-v1tok)/v1tok:+.0%})")

print("\nper-question changes")
for qid in v1:
    a, b = v1[qid], v2[qid]
    if a["final_hit"] != b["final_hit"]:
        print(f"  {qid}: {'hit' if a['final_hit'] else 'MISS'} -> {'hit' if b['final_hit'] else 'MISS'}  '{b['q']}'")
        print(f"     v1 final: {[f['key'] for f in a['final3']]}")
        print(f"     v2 final: {[f['key'] for f in b['final3']]}")
    elif a["final_hit"] and b["final_hit"]:
        p1 = next(i for i, f in enumerate(a["final3"]) if f["key"] in a["expect"])
        p2 = next(i for i, f in enumerate(b["final3"]) if f["key"] in b["expect"])
        if p1 != p2:
            print(f"  {qid}: rank improved {'#'+str(p1+1)} -> {'#'+str(p2+1)}  ({b['q'][:44]})")

print("\nstage that surfaced the correct chunk (v2)")
print(f"  {dict(Counter(r['found_by'] for r in real))}")
print(f"  seed document was already the expected document: "
      f"{sum(1 for r in real if r['seed_is_expected_doc'])}/{len(real)}")
print(f"  correct chunk reachable ONLY via the new sibling stage: "
      f"{[r['id'] for r in real if r['found_by'] == 'sibling']}")
print(f"  still unreachable (not in merged): {[r['id'] for r in real if not r['merged_hit']]}")

print("\nabstention behaviour (answers not in the vault)")
for r in absent:
    print(f"  {r['id']} '{r['q']}' -> raw {r['rerank_raw']!r} / {len(r['final3'])} passages "
          f"{[f['key'] for f in r['final3']]}")

print("\nreranker contract (v2)")
print(f"  replies without exactly 3 indices: "
      f"{ {r['id']: r['rerank_raw'] for r in records if len(r['rerank_indices']) != 3} }")
print(f"  zero-passage outcomes: {[r['id'] for r in records if not r['final3']]}")
print(f"  candidate set size: median {sorted(r['merged_count'] for r in records)[len(records)//2]}"
      f"  max {max(r['merged_count'] for r in records)} (v1 median "
      f"{sorted(r['merged_count'] for r in v1.values())[len(v1)//2]}, max {max(r['merged_count'] for r in v1.values())})")
print(f"  final-3 slots by source (v2): {dict(Counter(f['source'] for r in records for f in r['final3']))}")
