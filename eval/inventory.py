"""Stage 1 of the RAG evaluation: inventory the indexable units (no API calls).

Loads main.py with its module-level TEST block cut off, so importing it does NOT
run the demo query or cost a DeepSeek call. Writes eval/chunks.json and prints a
structural summary.
"""

import json
import sys
from pathlib import Path

RAG_DIR = Path("/Users/ab/Desktop/rag")
OUT = RAG_DIR / "eval" / "chunks.json"

MAIN = RAG_DIR / "main.py"
src = MAIN.read_text(encoding="utf-8")
marker = "# ============================================================\n# TEST"
head, sep, _tail = src.partition(marker)
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
embeddings = ns["embeddings"]
graph = ns["graph"]

import numpy as np

norms = np.linalg.norm(embeddings, axis=1)
lengths = np.array([len(c["text"]) for c in chunks])

print(f"chunks: {len(chunks)}   documents: {len({c['document'] for c in chunks})}")
print(f"embedding shape: {embeddings.shape}")
print("--- embedding norms (are they L2-normalised? dot product == cosine only if all ~1.0)")
print(f"  min {norms.min():.4f}  max {norms.max():.4f}  mean {norms.mean():.4f}  std {norms.std():.4f}")
print(f"  normalised chunks: {int((np.abs(norms - 1.0) < 1e-3).sum())}/{len(norms)}")
print("--- chunk text lengths (chars)")
print(f"  min {lengths.min()}  p50 {int(np.percentile(lengths, 50))}  p90 {int(np.percentile(lengths, 90))}  max {lengths.max()}  mean {int(lengths.mean())}")
print(f"  total chars: {int(lengths.sum()):,}")

per_doc = {}
for c in chunks:
    per_doc.setdefault(c["document"], []).append(c)

print("--- per document")
for doc in sorted(per_doc):
    cs = per_doc[doc]
    links = sorted({l for c in cs for l in c["links"]})
    print(f"  {doc:<48} {len(cs):>3} chunks  links→{len(links)}")

linked = sum(1 for c in chunks if c["links"])
print(f"--- graph: {len(graph)} source docs with outbound links; chunks carrying links: {linked}/{len(chunks)}")
print(f"  out-degree per doc: { {k: len(v) for k, v in sorted(graph.items())} }")

generic = [c for c in chunks if c["section"] == "Introduction"]
print(f"--- generic 'Introduction' chunks: {len(generic)} ({len(generic)/len(chunks):.0%} of corpus)")

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text(
    json.dumps(
        [
            {
                "i": i,
                "document": c["document"],
                "section": c["section"],
                "chars": len(c["text"]),
                "links": c["links"],
                "text": c["text"],
            }
            for i, c in enumerate(chunks)
        ],
        ensure_ascii=False,
        indent=1,
    ),
    encoding="utf-8",
)
print(f"wrote {OUT}")
