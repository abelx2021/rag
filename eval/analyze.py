"""Stage 3: turn eval/results.json into the numbers that attribute failures."""

import json
import statistics
from pathlib import Path

EVAL = Path("/Users/ab/Desktop/rag/eval")
data = json.loads((EVAL / "results.json").read_text(encoding="utf-8"))
recs = data["records"]
real = [r for r in recs if r["type"] != "absent"]
absent = [r for r in recs if r["type"] == "absent"]

print(f"corpus questions: {len(recs)} ({len(real)} answerable, {len(absent)} absent)")
print(f"rerank tokens: {data['tokens']['input']:,} in / {data['tokens']['output']:,} out "
      f"= {data['tokens']['input']/len(recs):,.0f} input tokens per question\n")

print("=== 1. where the correct chunk came from")
have = [r for r in real if r["final_hit"]]
print(f"  delivered in top-3: {len(have)}/{len(real)}")
print(f"  of those, expected chunk was in vector top-10: {sum(r['vec_hit'] for r in have)}")
print(f"  of those, expected chunk was ONLY reachable via graph (vec miss, merged hit): "
      f"{[r['id'] for r in have if not r['vec_hit'] and r['merged_hit']]}")
print(f"  expected chunk missing from merged entirely: "
      f"{[r['id'] for r in real if not r['merged_hit']]}")

print("\n=== 2. rank of the correct chunk in the vector stage")
ranks = [r["vec_best_rank"] for r in real if r["vec_best_rank"]]
print(f"  rank 1: {sum(1 for x in ranks if x == 1)}/{len(real)}   "
      f"<=3: {sum(1 for x in ranks if x <= 3)}   <=10: {sum(1 for x in ranks if x <= 10)}")
print(f"  distribution: {sorted(ranks)}")
print(f"  median rank of the correct chunk: {statistics.median(ranks)}")

print("\n=== 3. reranker behaviour")
first = [r for r in have if r["final3"] and r["expect"]]
print(f"  correct chunk delivered at #1: {sum(1 for r in have if r['final3'][0]['key'] in r['expect'])}/{len(real)}")
viol = {r["id"]: r["rerank_raw"] for r in recs if len(r["rerank_indices"]) != 3}
print(f"  replies that did not contain exactly 3 indices: {viol}")
bad_idx = {
    r["id"]: r["rerank_indices"]
    for r in recs
    if any(i >= r["merged_count"] for i in r["rerank_indices"])
}
print(f"  out-of-range indices: {bad_idx or 'none'}")
print(f"  zero-passage outcomes: {[r['id'] for r in recs if not r['final3']]}")

graph_slots = graph_bad = 0
for r in recs:
    for f in r["final3"]:
        if f["source"] == "graph":
            graph_slots += 1
            if f["key"] not in r["expect"]:
                graph_bad += 1
print(f"  final-3 slots filled by graph-sourced passages: {graph_slots}/{len(recs)*3} "
      f"({graph_slots/(len(recs)*3):.0%}); of those, off-target: {graph_bad}")

print("\n=== 4. can a score threshold separate answerable from absent?")
hit_scores = []
for r in real:
    sc = [v["score"] for v in r["vector_top10"] if v["key"] in r["expect"]]
    if sc:
        hit_scores.append(max(sc))
absent_scores = [r["best_vector_score"] for r in absent]
print(f"  lowest score of a CORRECT chunk (answerable): {min(hit_scores):.4f}")
print(f"  highest best-score on an ABSENT question:     {max(absent_scores):.4f}  {absent_scores}")
print(f"  overlap -> a single similarity threshold cannot separate them: "
      f"{max(absent_scores) > min(hit_scores)}")

print("\n=== 5. false positives on absent questions")
for r in absent:
    print(f"  {r['id']} '{r['q']}'")
    print(f"     model said: {r['rerank_raw']!r}")
    print(f"     delivered: {[f['key'] for f in r['final3']]}")

print("\n=== 6. why d14 failed ('What are the nine IANUS modules?')")
d14 = next(r for r in recs if r["id"] == "d14")
print(f"  seed document (vector #1): {d14['seed']}")
print("  vector top-10:")
for v in d14["vector_top10"]:
    print(f"    {v['score']:.4f}  {v['key']}")
print("  expected chunk: module-catalog::Modules is in the vector list above? "
      f"{any(v['key'] == 'module-catalog::Modules' for v in d14['vector_top10'])}")
print("  graph stage searched documents:",
      sorted({v["key"].split("::")[0] for v in d14["graph_top10"]}))
print("  does the graph stage ever look inside the seed document itself? "
      f"{any(v['key'].startswith('module-catalog::') for v in d14['graph_top10'])}")

print("\n=== 7. stale-vs-current risk (delivered #1 key vs expected)")
for r in have:
    if r["final3"] and r["final3"][0]["key"] not in r["expect"]:
        print(f"  {r['id']}: #1 delivered = {r['final3'][0]['key']}  |  expected = {r['expect']}")
