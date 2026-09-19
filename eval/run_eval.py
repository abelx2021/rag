"""Stage 2 of the RAG evaluation: run every question through the pipeline and
attribute each failure to the stage that caused it.

Stages tested, in order:
  1. embedding + vector search   (search, k=10)
  2. wikilink graph expansion    (graph_search, seeded from vector #1)
  3. merge/dedupe                (merge_candidates)
  4. DeepSeek rerank             (rerank, k=3)

main.py is loaded with its module-level TEST block cut off, so the demo query
never runs. Writes eval/results.json + eval/report.md.
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
except Exception as exc:  # keep the API key out of any traceback
    print("EXEC FAILED:", type(exc).__name__, exc)
    sys.exit(1)

chunks = ns["chunks"]
search = ns["search"]
graph_search = ns["graph_search"]
merge_candidates = ns["merge_candidates"]
rerank = ns["rerank"]
embed_query = ns["embed_query"]

KEY = lambda c: f"{c['document']}::{c['section']}"
inventory = {KEY(c) for c in chunks}

spec = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))
questions = spec["questions"]

bad = [(q["id"], e) for q in questions for e in q["expect"] if e not in inventory]
if bad:
    print("GROUND TRUTH MISMATCH (not a real chunk):")
    for qid, e in bad:
        print(f"  {qid}: {e}")
    sys.exit(3)

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
    graph = graph_search(q_emb, seed, k=ns["GRAPH_K"])
    merged = merge_candidates(vec, graph)

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
    graph_keys = [KEY(c) for c in graph]
    merged_keys = [KEY(c) for c in merged]
    final_keys = [KEY(c) for c in final]

    vec_ranks = [i + 1 for i, k in enumerate(vec_keys) if k in expect]
    rec = {
        "id": q["id"],
        "type": q["type"],
        "q": q["q"],
        "expect": sorted(expect),
        "seed": seed,
        "vector_top10": [{"key": k, "score": round(c["score"], 4)} for k, c in zip(vec_keys, vec)],
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
        "graph_hit": any(k in expect for k in graph_keys),
        "merged_hit": any(k in expect for k in merged_keys),
        "final_hit": any(k in expect for k in final_keys),
        "best_vector_score": round(max(c["score"] for c in vec), 4),
    }
    rec["vec_hit"] = rec["vec_best_rank"] is not None
    if absent or rec["final_hit"]:
        rec["fail_stage"] = None if not absent else "n/a"
    elif not rec["merged_hit"]:
        rec["fail_stage"] = "retrieval (embedding+graph)"
    else:
        rec["fail_stage"] = "rerank"

    graph_only = [k for k in graph_keys if k not in vec_keys]
    rec["graph_contributed_new"] = bool(graph_only)
    rec["final_from_graph_only"] = any(
        k in graph_only for k in final_keys
    )
    records.append(rec)

    flag = "OK " if (absent or rec["final_hit"]) else "MISS"
    print(
        f"[{n:>2}/{len(questions)}] {flag} {q['id']:<4} {q['type']:<9} "
        f"vec_rank={rec['vec_best_rank']} merged={rec['merged_hit']} final={rec['final_hit']} "
        f"rerank='{raw}' seed={seed[:28]}"
    )

(EVAL / "results.json").write_text(
    json.dumps({"records": records, "tokens": {"input": tok_in, "output": tok_out}},
               ensure_ascii=False, indent=1), encoding="utf-8")

# ---------------- summary ----------------
by_type = {}
for r in records:
    by_type.setdefault(r["type"], []).append(r)

lines = []
lines.append("# RAG evaluation — architecture failure map\n")
lines.append(f"Corpus: {len(chunks)} chunks / 12 documents (~35k chars). "
             f"Rerank tokens this run: {tok_in:,} in / {tok_out:,} out.\n")

lines.append("## Hit rate by question type (final top-3 after rerank)\n")
lines.append("| type | n | hit@3 | vec hit@10 | merged hit | rerank losses |")
lines.append("|---|---|---|---|---|---|")
for t, rs in by_type.items():
    if t == "absent":
        continue
    n = len(rs)
    h = sum(r["final_hit"] for r in rs)
    v = sum(r["vec_hit"] for r in rs)
    m = sum(r["merged_hit"] for r in rs)
    lost = sum(1 for r in rs if r["merged_hit"] and not r["final_hit"])
    lines.append(f"| {t} | {n} | {h}/{n} | {v}/{n} | {m}/{n} | {lost} |")

real = [r for r in records if r["type"] != "absent"]
lines.append(f"\nOverall (answerable questions): hit@3 = {sum(r['final_hit'] for r in real)}/{len(real)}")
lines.append(f"Vector hit@10 = {sum(r['vec_hit'] for r in real)}/{len(real)}; "
             f"merged recall = {sum(r['merged_hit'] for r in real)}/{len(real)}")
lines.append(f"Graph layer contributed a chunk the vector stage never surfaced in "
             f"{sum(r['graph_contributed_new'] for r in real)}/{len(real)} questions; "
             f"it reached the final answer in {sum(r['final_from_graph_only'] for r in real)}.")

lines.append("\n## Failure attribution\n")
stages = Counter(r["fail_stage"] for r in real if r["fail_stage"])
for t, rs in by_type.items():
    if t == "absent":
        continue
    lines.append(f"### {t}")
    for r in rs:
        mark = "hit" if r["final_hit"] else f"FAIL @ {r['fail_stage']}"
        lines.append(f"- {r['id']} {mark} — {r['q']}")
        lines.append(f"  - expected: {r['expect']}")
        lines.append(f"  - vec best rank {r['vec_best_rank']} (top score {r['best_vector_score']}), "
                     f"graph hit {r['graph_hit']}, merged {r['merged_hit']}, seed '{r['seed']}'")
        lines.append(f"  - rerank said '{r['rerank_raw']}' → final: "
                     f"{[f['key'] + ' (' + str(f['source']) + ')' for f in r['final3']]}")

lines.append("\n## Abstention test (answers NOT in the vault)\n")
lines.append("| id | question | best vector score | delivered anyway? |")
lines.append("|---|---|---|---|")
for r in by_type.get("absent", []):
    lines.append(f"| {r['id']} | {r['q']} | {r['best_vector_score']} | "
                 f"{len(r['final3'])} passages |")

parse_bad = [r["id"] for r in records if len(r["rerank_indices"]) != 3]
empty = [r["id"] for r in records if not r["final3"]]
lines.append("\n## Reranker contract\n")
lines.append(f"Replies that did not yield exactly 3 indices: {parse_bad or 'none'}")
lines.append(f"Questions that returned zero final passages: {empty or 'none'}")

(EVAL / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

print("\n" + "=" * 70)
print(f"answerable: {len(real)}  hit@3 {sum(r['final_hit'] for r in real)}  "
      f"vec@10 {sum(r['vec_hit'] for r in real)}  merged {sum(r['merged_hit'] for r in real)}")
print("fail stages:", dict(stages))
print(f"rerank tokens: {tok_in:,} in / {tok_out:,} out")
print("wrote eval/report.md and eval/results.json")
