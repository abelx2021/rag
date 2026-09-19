"""Authority experiment (ISOLATED - main.py untouched).

Applies the vault's authored `authority` fields as an adjustment between the
candidate set and the frozen reranker, and measures whether the current 10-schema
claim outranks the superseded 8-schema claim for d04 - without deleting anything.

Ladder (each level is a separate hypothesis):
  V0  baseline, frozen pipeline unchanged
  V1  annotation only   - authority status written into the candidate header
  V2  partition only    - conflicting superseded chunks moved after current ones
  V3  partition + annotation

Mechanism rules:
  - topic-scoped: an adjustment activates only when the candidate set contains
    BOTH a `current` and a `superseded` page for the same topic
  - preference, not erasure: nothing is removed from the candidate set
  - no-op by construction when no topic is in conflict

Usage: python3 eval/authority_experiment.py            # d04 ladder + regression for winners
"""

import contextlib
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

RAG = Path("/Users/ab/Desktop/rag")
WIKI = Path("/Users/ab/knowledge/ianus/wiki")
EVAL = RAG / "eval"

src = (RAG / "main.py").read_text(encoding="utf-8")
head = src.partition("# ============================================================\n# TEST")[0]
ns = {}
exec(compile(head, "main.py", "exec"), ns)

KEY = lambda c: f"{c['document']}::{c['section']}"
OK, ABSTAIN, FAIL = ns["STATE_ANSWERABLE"], ns["STATE_ABSTAIN"], ns["STATE_CONTRACT_FAILURE"]
RE_TOKENS = re.compile(r"^Tokens:\s*(\d+) input", re.M)

# ---------- authority map from the vault ----------
AUTH = {}
for p in sorted(WIKI.glob("*.md")):
    text = p.read_text(encoding="utf-8")
    if not text.startswith("---"):
        continue
    end = text.index("\n---", 3)
    fm = yaml.safe_load(text[3:end]) or {}
    for entry in fm.get("authority") or []:
        AUTH.setdefault(entry["topic"], []).append((p.stem, entry["status"]))

print("authority map from the vault:")
for topic, entries in AUTH.items():
    print(f"  {topic}: {entries}")


def active_topics(cands):
    """Topics where a current AND a superseded page are BOTH in the candidate set."""
    present = {c["document"] for c in cands}
    out = {}
    for topic, entries in AUTH.items():
        cur = {p for p, s in entries if s == "current" and p in present}
        sup = {p for p, s in entries if s == "superseded" and p in present}
        if cur and sup:
            out[topic] = (cur, sup)
    return out


def status_of(doc, active):
    for topic, (cur, sup) in active.items():
        if doc in sup:
            return "superseded", topic
        if doc in cur:
            return "current", topic
    return None, None


def partition(cands):
    """Move chunks from superseded pages after chunks from current pages."""
    active = active_topics(cands)
    if not active:
        return cands
    keep, demote = [], []
    for c in cands:
        st, _ = status_of(c["document"], active)
        (demote if st == "superseded" else keep).append(c)
    return keep + demote


def annotate(cands):
    """Write the authority status into the candidate header text."""
    active = active_topics(cands)
    if not active:
        return cands
    out = []
    for c in cands:
        st, topic = status_of(c["document"], active)
        c = c.copy()
        if st:
            c["text"] = f"[AUTHORITY: this page is {st.upper()} for topic '{topic}']\n\n" + c["text"]
        out.append(c)
    return out


def run(query, adjust):
    q_emb = ns["embed_query"](query)
    vec = ns["search"](q_emb, k=ns["VECTOR_K"])
    seed = vec[0]["document"]
    siblings, graph = ns["expanded_search"](q_emb, seed, sibling_k=ns["SIBLING_K"], graph_k=ns["GRAPH_K"])
    merged = ns["merge_candidates"](vec, siblings, graph)
    cands = adjust(merged)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        d = ns["rerank"](query, cands, k=ns["FINAL_K"])
    m = RE_TOKENS.search(buf.getvalue())
    return d, len(cands), int(m.group(1)) if m else 0, [KEY(c) for c in merged], [KEY(c) for c in cands]


# ---------- stage A: the d04 ladder ----------
Q = next(q for q in json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]
         if q["id"] == "d04")
EXPECT = set(Q["expect"])
OLD = "ianus-modular-analysis-and-implementation-plan::Architectural proposal > Proposed schema organisation"
CUR = "data-model::Organization"

VARIANTS = {
    "V0 baseline (no adjustment)": lambda c: c,
    "V1 annotation only": annotate,
    "V2 partition only": partition,
    "V3 partition + annotation": lambda c: annotate(partition(c)),
}

print(f"\n{'='*78}\nd04  '{Q['q']}'")
print(f"superseded claim : {OLD}")
print(f"current claim    : {CUR}   (expected: {sorted(EXPECT)})")

fixed = []
for name, adjust in VARIANTS.items():
    d, nc, toks, before_keys, after_keys = run(Q["q"], adjust)
    delivered = [KEY(c) for c in d["passages"]]
    cand_changed = before_keys != after_keys
    old_pos = delivered.index(OLD) + 1 if OLD in delivered else None
    cur_pos = delivered.index(CUR) + 1 if CUR in delivered else None
    ok = d["state"] == OK and cur_pos is not None and (old_pos is None or cur_pos < old_pos)
    if ok and name != "V0 baseline (no adjustment)":
        fixed.append(name)
    print(f"\n  {name}")
    print(f"    state={d['state']} candidates={nc} tokens={toks} candidate order changed={cand_changed}")
    print(f"    delivered: {delivered}")
    print(f"    current at #{cur_pos}, superseded at #{old_pos}  -> {'CURRENT AHEAD (desired)' if ok else 'not satisfied'}")

print(f"\nsuperseded chunk still present in the candidate set: "
      f"{OLD in run(Q['q'], partition)[4]}  (preference, not erasure)")

# ---------- stage B: regression across the answerable set ----------
questions = json.loads((EVAL / "questions.json").read_text(encoding="utf-8"))["questions"]
answerable = [q for q in questions if q.get("vault_can_answer", True) and q["type"] != "absent"]
baseline = {r["id"]: r for r in json.loads((EVAL / "results_v6_p1.json").read_text(encoding="utf-8"))["rows"]}

for name in fixed:
    adjust = VARIANTS[name]
    print(f"\n{'='*78}\nregression: {name} over {len(answerable)} answerable questions")
    rows = []
    triggered = []
    tok_total = 0
    for q in answerable:
        expect = set(q["expect"])
        d, nc, toks, before_keys, after_keys = run(q["q"], adjust)
        tok_total += toks
        if before_keys != after_keys:
            triggered.append(q["id"])
        delivered = [KEY(c) for c in d["passages"]]
        rows.append({
            "id": q["id"], "state": d["state"],
            "delivered_expected": bool(expect) and any(k in expect for k in delivered),
            "delivered": delivered,
            "was": baseline[q["id"]]["delivered_expected"],
            "was_state": baseline[q["id"]]["state"],
        })
    gained = [r["id"] for r in rows if r["delivered_expected"] and not r["was"]]
    lost = [r["id"] for r in rows if not r["delivered_expected"] and r["was"]]
    state_changed = [r["id"] for r in rows if r["state"] != r["was_state"]]
    print(f"  candidate order actually changed for: {triggered or 'none'}")
    print(f"  answered correctly: {sum(r['delivered_expected'] for r in rows)}/{len(rows)} "
          f"(frozen baseline {sum(r['was'] for r in rows)}/{len(rows)})")
    print(f"  gained: {gained or 'none'}")
    print(f"  LOST:   {lost or 'none'}")
    print(f"  state changed: {[(i, baseline[i]['state'], next(r['state'] for r in rows if r['id']==i)) for i in state_changed] or 'none'}")
    print(f"  contract failures: {[r['id'] for r in rows if r['state'] == FAIL] or 'none'}")
    print(f"  states: {dict(Counter(r['state'] for r in rows))}   tokens {tok_total:,} ({tok_total/len(rows):,.0f}/q)")
    (EVAL / f"authority_regression_{name.split()[0]}.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
