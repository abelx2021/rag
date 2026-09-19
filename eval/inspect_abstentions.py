"""Inspect the three false-abstentions: does the expected chunk actually
contain enough to answer the specific question?"""

import json
from pathlib import Path

EVAL = Path("/Users/ab/Desktop/rag/eval")
chunks = json.loads((EVAL / "chunks.json").read_text(encoding="utf-8"))
v3 = {r["id"]: r for r in json.loads((EVAL / "results_v3.json").read_text(encoding="utf-8"))["rows"]}
bykey = {f"{c['document']}::{c['section']}": c for c in chunks}

for qid in ("s03", "i01", "o03"):
    r = v3[qid]
    print("=" * 78)
    print(f"{qid}  state={r['state']}  expect={r['expect']}")
    print(f"Q: {r['q']}")
    print(f"expected chunk present in candidate set: {r['merged_hit']} "
          f"(candidates={r['n_candidates']}, seed={r['seed']})")
    for e in r["expect"]:
        c = bykey.get(e)
        if not c:
            print(f"  [missing] {e}")
            continue
        print(f"\n--- {e}  ({c['chars']} chars)")
        print(c["text"])
