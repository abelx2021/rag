"""Aggregate the sibling-K sweep into the requested table + stability checks."""

import json
import statistics
from pathlib import Path

EVAL = Path("/Users/ab/Desktop/rag/eval")
files = sorted(EVAL.glob("sweep_K*_p*.json"))
data = {}
for f in files:
    d = json.loads(f.read_text(encoding="utf-8"))
    s = d["summary"]
    data.setdefault(s["K"], {})[s["pass"]] = d

print("SIBLING-K SENSITIVITY  (36 answerable + 4 absent questions per run)\n")
hdr = f"{'K':>3} {'pass':>4} {'merged':>7} {'top3':>6} {'#1':>5} {'cands':>6} {'tok/q':>8} {'sib':>4} {'graph':>6}"
print(hdr)
print("-" * len(hdr))
for K in sorted(data):
    for p in sorted(data[K]):
        s = data[K][p]["summary"]
        print(f"{K:>3} {p:>4} {s['merged_recall']:>4}/36 {s['final_top3']:>3}/36 "
              f"{s['final_rank1']:>3}/36 {s['avg_candidates']:>6.1f} {s['avg_tokens']:>8,.0f} "
              f"{s['sibling_rescues']:>4} {s['graph_rescues']:>6}")

base = data[0][1]["summary"]
cur = data[10][1]["summary"]
k3 = data[3][1]["summary"]
print(f"\ncost vs control: K=0 {base['avg_tokens']:,.0f} tok/q  "
      f"K=3 {k3['avg_tokens']:,.0f} ({(k3['avg_tokens']/base['avg_tokens']-1):+.1%})  "
      f"K=10 {cur['avg_tokens']:,.0f} ({(cur['avg_tokens']/base['avg_tokens']-1):+.1%})")

print("\nfirst K that closes the recall hole:")
for K in sorted(data):
    s = data[K][min(data[K])]["summary"]
    if s["merged_recall"] == 36 and s["final_top3"] == 36:
        print(f"  K={K}  ({s['avg_tokens']:,.0f} tok/q, {(s['avg_tokens']/base['avg_tokens']-1):+.1%} vs control)")
        break

print("\nwhich question does the sibling stage rescue, per K:")
for K in sorted(data):
    r = data[K][min(data[K])]["rows"]
    sib = [x["id"] for x in r if x["found_by"] == "sibling"]
    gr = [x["id"] for x in r if x["found_by"] == "graph"]
    print(f"  K={K:<2} sibling-first: {sib or '-'}   graph-first: {gr or '-'}")

print("\nmerged recall is deterministic (no LLM in that stage)?")
for K in sorted(data):
    sets = [
        tuple(sorted(x["id"] for x in d["rows"] if x["merged_hit"] and not x["absent"]))
        for d in data[K].values()
    ]
    print(f"  K={K:<2} identical across passes: {len(set(sets)) == 1}")

print("\nreranker noise (same candidates, different order): final_pos per pass")
for K in sorted(data):
    if len(data[K]) < 2:
        continue
    a, b = (data[K][p] for p in sorted(data[K])[:2])
    fa = {x["id"]: x["final_pos"] for x in a["rows"] if not x["absent"]}
    fb = {x["id"]: x["final_pos"] for x in b["rows"] if not x["absent"]}
    diff = {i: (fa[i], fb[i]) for i in fa if fa[i] != fb[i]}
    lost = [i for i in fa if fa[i] and not fb[i]]
    print(f"  K={K}: positions changed for {len(diff)}/36 -> {diff or '{}'}")
    print(f"       wrong-answer cases: {'none' if not lost else lost}")

print("\nper-question behaviour at K=0 vs K=3 vs K=10 (final_pos)")
p0 = {x["id"]: x["final_pos"] for x in data[0][1]["rows"] if not x["absent"]}
p3 = {x["id"]: x["final_pos"] for x in data[3][1]["rows"] if not x["absent"]}
p10 = {x["id"]: x["final_pos"] for x in data[10][1]["rows"] if not x["absent"]}
for i in p0:
    if not (p0[i] == p3[i] == p10[i]):
        print(f"  {i}: K0={p0[i]}  K3={p3[i]}  K10={p10[i]}")

print("\nmalformed reranker replies per K (indices != 3)")
for K in sorted(data):
    bad = [x["id"] for x in data[K][min(data[K])]["rows"] if x["n_indices"] != 3]
    print(f"  K={K:<2} {bad or 'none'}")
