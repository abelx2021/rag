"""Sibling-K sensitivity sweep.

Usage: python3 eval/sweep.py 0:1,1:1,2:1,3:1     (specs are K:pass)

For each spec it runs all 40 questions with sibling_k=K passed explicitly into
expanded_search (so a single process can sweep several K values), and writes
eval/sweep_K{K}_p{pass}.json. Only the seven metrics asked for are tracked:

  merged recall /36, final top-3 /36, final #1 /36, avg candidates,
  avg rerank input tokens, sibling rescues, graph rescues.

rescued = this stage was the first to surface the correct chunk AND that chunk
reached the final answer.
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
chunks = ns["chunks"]
inventory = {KEY(c) for c in chunks}
questions = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]

for q in questions:
    for e in q["expect"]:
        if e not in inventory:
            print("GROUND TRUTH MISMATCH:", q["id"], e)
            sys.exit(3)

RE_DEEPSEEK = re.compile(r"^DeepSeek:\s*(.*)$", re.M)
RE_TOKENS = re.compile(r"^Tokens:\s*(\d+) input \+ (\d+) output", re.M)

specs = []
for part in sys.argv[1].split(","):
    k, _, p = part.partition(":")
    specs.append((int(k), int(p or 1)))

for K, PASSNO in specs:
    rows = []
    tok_total = 0
    for q in questions:
        expect = set(q["expect"])
        absent = q["type"] == "absent"

        q_emb = ns["embed_query"](q["q"])
        vec = ns["search"](q_emb, k=ns["VECTOR_K"])
        seed = vec[0]["document"]
        siblings, graph = ns["expanded_search"](
            q_emb, seed, sibling_k=K, graph_k=ns["GRAPH_K"]
        )
        merged = ns["merge_candidates"](vec, siblings, graph)

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            final = ns["rerank"](q["q"], merged, k=ns["FINAL_K"])
        cap = buf.getvalue()
        m = RE_TOKENS.search(cap)
        tok = int(m.group(1)) if m else 0
        tok_total += tok
        raw = (RE_DEEPSEEK.search(cap) or [None, ""])[1].strip()

        vec_keys, sib_keys, graph_keys = (KEY(c) for c in vec), (KEY(c) for c in siblings), (KEY(c) for c in graph)
        merged_keys = [KEY(c) for c in merged]
        final_keys = [KEY(c) for c in final]

        found_by = next(
            (lbl for lbl, keys in (("vector", vec_keys), ("sibling", sib_keys), ("graph", graph_keys))
             if any(k in expect for k in keys)),
            None,
        )
        final_hit = any(k in expect for k in final_keys)
        pos = next((i + 1 for i, k in enumerate(final_keys) if k in expect), None)
        rows.append({
            "id": q["id"], "type": q["type"], "absent": absent,
            "merged_hit": any(k in expect for k in merged_keys),
            "final_hit": final_hit, "final_pos": pos, "found_by": found_by,
            "merged_count": len(merged), "tokens": tok, "rerank_raw": raw,
            "n_indices": len(re.findall(r"\d+", raw)), "final3": final_keys,
        })

    real = [r for r in rows if not r["absent"]]
    summary = {
        "K": K, "pass": PASSNO,
        "merged_recall": sum(r["merged_hit"] for r in real),
        "final_top3": sum(r["final_hit"] for r in real),
        "final_rank1": sum(1 for r in real if r["final_pos"] == 1),
        "avg_candidates": sum(r["merged_count"] for r in rows) / len(rows),
        "avg_tokens": tok_total / len(rows),
        "tokens_total": tok_total,
        "sibling_rescues": sum(1 for r in real if r["found_by"] == "sibling" and r["final_hit"]),
        "graph_rescues": sum(1 for r in real if r["found_by"] == "graph" and r["final_hit"]),
        "sibling_first_hit": sum(1 for r in real if r["found_by"] == "sibling"),
        "graph_first_hit": sum(1 for r in real if r["found_by"] == "graph"),
    }
    (EVAL / f"sweep_K{K}_p{PASSNO}.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(
        f"K={K:<2} p{PASSNO}  merged {summary['merged_recall']}/36  "
        f"top3 {summary['final_top3']}/36  #1 {summary['final_rank1']}/36  "
        f"cands {summary['avg_candidates']:.1f}  tok {summary['avg_tokens']:,.0f}  "
        f"sib {summary['sibling_rescues']}  graph {summary['graph_rescues']}"
    )
    sys.stdout.flush()
