"""Stage 4: counterfactual for d14 — is the miss caused by the graph stage never
looking inside the seed document?

Variant A: today's candidate set (vector top-10 + graph neighbours of seed doc).
Variant B: same, plus every chunk of the seed document itself.
Both go through the identical rerank prompt, so only the candidate set changes.
"""

import contextlib
import io
import json
import re
from pathlib import Path

RAG_DIR = Path("/Users/ab/Desktop/rag")
src = (RAG_DIR / "main.py").read_text(encoding="utf-8")
head = src.partition("# ============================================================\n# TEST")[0]

ns = {}
try:
    exec(compile(head, "main.py", "exec"), ns)
except Exception as exc:
    print("EXEC FAILED:", type(exc).__name__, exc)
    raise SystemExit(1)

chunks = ns["chunks"]
q = "What are the nine IANUS modules?"
expect = "module-catalog::Modules"
key = lambda c: f"{c['document']}::{c['section']}"

q_emb = ns["embed_query"](q)
vec = ns["search"](q_emb, k=10)
seed = vec[0]["document"]
graph = ns["graph_search"](q_emb, seed, k=10)
merged = ns["merge_candidates"](vec, graph)

siblings = [c for c in chunks if c["document"] == seed]
seen = {key(c) for c in merged}
extra = [c for c in siblings if key(c) not in seen]
variant_b = merged + extra


def run(cands, label):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        final = ns["rerank"](q, cands, k=3)
    out = buf.getvalue()
    raw = (re.search(r"^DeepSeek:\s*(.*)$", out, re.M) or [None, ""])[1]
    print(f"\n{label}")
    print(f"  candidates: {len(cands)}  (keys: {[key(c) for c in cands]})")
    print(f"  rerank reply: {raw!r}")
    print(f"  delivered top-3: {[key(c) for c in final]}")
    print(f"  correct chunk delivered: {any(key(c) == expect for c in final)}")
    return any(key(c) == expect for c in final)


print(f"seed document: {seed}")
print(f"sibling chunks of the seed document not already in the candidate set: {[key(c) for c in extra]}")
run(merged, "VARIANT A — current architecture (vector + graph neighbours)")
run(variant_b, "VARIANT B — + the seed document's own remaining chunks")
