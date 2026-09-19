"""Verify the authority authoring: YAML validity, resolvable authority map, and
that chunk text is byte-identical to the frozen benchmark's inventory."""

import json
import sys
from collections import defaultdict
from pathlib import Path

WIKI = Path("/Users/ab/knowledge/ianus/wiki")
RAG = Path("/Users/ab/Desktop/rag")

try:
    import yaml
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False


def frontmatter(text):
    if not text.startswith("---"):
        return {}, text
    end = text.index("\n---", 3)
    return text[3:end], text[end + 4:]


print(f"real YAML parser available: {HAVE_YAML}")

authority = defaultdict(list)
problems = []
for p in sorted(WIKI.glob("*.md")):
    raw, body = frontmatter(p.read_text(encoding="utf-8"))
    if HAVE_YAML:
        try:
            fm = yaml.safe_load(raw) or {}
        except Exception as exc:
            problems.append(f"{p.stem}: YAML ERROR {exc}")
            continue
    else:
        fm = {}
    entries = fm.get("authority") or []
    if not isinstance(entries, list):
        problems.append(f"{p.stem}: authority is not a list")
        continue
    for e in entries:
        if not isinstance(e, dict) or "topic" not in e or "status" not in e:
            problems.append(f"{p.stem}: malformed authority entry {e!r}")
            continue
        authority[e["topic"]].append((p.stem, e["status"], e.get("supersedes"), e.get("superseded_by")))

print("\nparsed authority map:")
for topic, entries in authority.items():
    print(f"  topic: {topic}")
    for page, status, sup, supby in entries:
        print(f"    page={page:<48} status={status:<11} supersedes={sup or '-':<48} superseded_by={supby or '-'}")

# resolvability: named pages must exist
stems = {p.stem for p in WIKI.glob("*.md")}
for topic, entries in authority.items():
    for page, status, sup, supby in entries:
        for ref in (sup, supby):
            if ref and ref not in stems:
                problems.append(f"{page}: authority references unknown page '{ref}'")

# reciprocity: superseded page's superseded_by must point back
for topic, entries in authority.items():
    cur = [e for e in entries if e[1] == "current"]
    old = [e for e in entries if e[1] == "superseded"]
    for page, _, sup, _ in cur:
        for opage, _, _, supby in old:
            if sup != opage:
                problems.append(f"{topic}: {page} supersedes {sup} but the superseded entry is {opage}")
            if supby != page:
                problems.append(f"{topic}: {opage} superseded_by {supby} but the current entry is {page}")

print("\nconsistency problems:", problems or "none")

# chunk text unchanged? frontmatter is stripped before chunking, so it must be.
sys.path.insert(0, str(RAG))
src = (RAG / "main.py").read_text(encoding="utf-8")
head = src.partition("# ============================================================\n# TEST")[0]
ns = {}
exec(compile(head, "main.py", "exec"), ns)
live = [(c["document"], c["section"], c["text"]) for c in ns["chunks"]]
frozen = [(c["document"], c["section"], c["text"])
          for c in json.loads((RAG / "eval" / "chunks.json").read_text(encoding="utf-8"))]

print(f"\nchunks live={len(live)} frozen={len(frozen)}")
print("chunk inventory identical to the frozen benchmark:", live == frozen)
if live != frozen:
    for a, b in zip(live, frozen):
        if a != b:
            print("  first difference:", a[:2], "vs", b[:2])
            break
