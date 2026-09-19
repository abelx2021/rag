"""Authority-signal inventory over the ianus wiki. READ-ONLY.

Answers: what does the vault actually expose for deciding "current vs
superseded"? No model, no network, no writes to the vault.

Sections:
  1. frontmatter fields per document (and schema deviations)
  2. explicit supersession / update language, with sentences
  3. version and date tokens
  4. reference graph (outbound + inbound), orphans, hubs
  5. schema enumerations per document
  6. numeric claims per document, and cross-document divergence on the same claim
"""

import re
from collections import Counter, defaultdict
from pathlib import Path

WIKI = Path("/Users/ab/knowledge/ianus/wiki")
pages = sorted(WIKI.glob("*.md"))

FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
LINK = re.compile(r"\[\[([^\]|#]+)")
SUPERSESSION = [
    "earlier", "previously", "supersed", "no longer", "replaced", "former",
    "the later", "was added", "were added", "consolidated", "renamed",
    "builds on", "obsolete", "reflects the later", "now", "was treated",
    "is treated as authoritative", "proposed only", "moved", "promoted",
]
VERSIONISH = re.compile(r"\b(?:PUC|SNM|Protocol|Vademecum|Controls|RGS|ADR)\s*[- ]?\s*(\d+(?:\.\d+)*)\b")
SEMVER = re.compile(r"\bv(\d+\.\d+(?:\.\d+)?)\b")
SCHEMAS = {"core", "iam", "procedures", "projects", "finance", "documents",
           "controls", "integrations", "reporting", "audit"}
CLAIMS = re.compile(
    r"\b(\d{1,4})\s+(information structures|validation codes|TC sheets|phases|modules|schemas|"
    r"open\s+Sprint\s+0\s+decisions|risks|epics|chunks|documents|collections|structures)\b",
    re.IGNORECASE)

docs = {}
for p in pages:
    text = p.read_text(encoding="utf-8")
    m = FM.match(text)
    fm_raw = m.group(1) if m else ""
    body = text[m.end():] if m else text
    fields = {}
    for line in fm_raw.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    docs[p.stem] = {"text": text, "body": body, "fields": fields}

print("=" * 78)
print("1. FRONTMATTER")
allkeys = Counter()
for name, d in docs.items():
    keys = list(d["fields"])
    allkeys.update(keys)
    extra = [k for k in keys if k not in ("tags", "created")]
    print(f"  {name:<48} {d['fields']}")
    if extra:
        print(f"      !! non-schema fields: {extra}")
print(f"\n  fields used across the vault: {dict(allkeys)}")
print("  schema allows only 'tags' and 'created'")

print("\n" + "=" * 78)
print("2. SUPERSESSION / UPDATE LANGUAGE (sentences containing a trigger)")
for name, d in docs.items():
    hits = []
    for sent in re.split(r"(?<=[.;])\s+|\n", d["body"]):
        s = sent.strip()
        if not s or len(s) < 12:
            continue
        low = s.lower()
        trig = [t for t in SUPERSESSION if t in low]
        if trig:
            hits.append((trig, s))
    if hits:
        print(f"\n  --- {name}  ({len(hits)} sentences)")
        for trig, s in hits:
            print(f"      [{','.join(trig)}] {s[:190]}")

print("\n" + "=" * 78)
print("3. VERSION AND DATE TOKENS")
for name, d in docs.items():
    v = VERSIONISH.findall(d["text"])
    s = SEMVER.findall(d["text"])
    dates = sorted(set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", d["text"])))
    months = sorted(set(re.findall(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b", d["text"])))
    yrs = sorted(set(re.findall(r"\b20\d{2}\b", d["text"])))
    print(f"  {name:<48}")
    print(f"      named versions: {v or '-'}   v-semver: {s or '-'}")
    print(f"      iso dates: {dates or '-'}   month-year: {months or '-'}   years: {yrs or '-'}")

print("\n" + "=" * 78)
print("4. REFERENCE GRAPH")
out = {n: sorted({l.strip() for l in LINK.findall(d["text"])}) for n, d in docs.items()}
inn = defaultdict(set)
for src, targets in out.items():
    for t in targets:
        inn[t].add(src)
for name in sorted(docs):
    print(f"  {name:<48} out={len(out[name]):>2} in={len(inn[name]):>2}")
print("\n  orphans (no inbound links):", [n for n in sorted(docs) if not inn[n]] or "none")
print("  hubs (most inbound):", sorted(((len(v), k) for k, v in inn.items()), reverse=True)[:4])

print("\n" + "=" * 78)
print("5. SCHEMA ENUMERATIONS")
for name, d in docs.items():
    back = [s for s in re.findall(r"`([a-z][a-z\-]*)`", d["text"]) if s in SCHEMAS]
    prose = [s for s in re.findall(r"\b([a-z][a-z\-]{2,})\b", d["text"]) if s in SCHEMAS]
    bset, pset = sorted(set(back)), sorted(set(prose))
    if bset or len(pset) >= 4:
        print(f"  {name:<48}")
        print(f"      backticked: {bset}  (n={len(bset)})")
        print(f"      plain text mentions: {pset}  (n={len(pset)})")

print("\n" + "=" * 78)
print("6. NUMERIC CLAIMS (cross-document)")
claims = defaultdict(list)
for name, d in docs.items():
    for num, what in CLAIMS.findall(d["body"]):
        claims[what.lower().strip()].append((name, num))
for what, hits in sorted(claims.items()):
    vals = {n for _, n in hits}
    flag = "  <-- DIVERGENT" if len(vals) > 1 else ""
    print(f"\n  claim '{what}': values={sorted(vals)}{flag}")
    for name, num in hits:
        if len(hits) <= 12:
            print(f"      {num:>5}  {name}")

print("\n" + "=" * 78)
print("7. EXPLICIT AUTHORITY FIELDS (supersedes / superseded_by / version / status / source)")
for name, d in docs.items():
    found = {k: v for k, v in d["fields"].items()
             if k in ("supersedes", "superseded_by", "version", "status", "source", "updated", "date")}
    if found:
        print(f"  {name}: {found}")
print("  (none printed above = no document declares its own version, status, source or supersession)")
