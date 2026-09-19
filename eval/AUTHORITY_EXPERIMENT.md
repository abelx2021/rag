# Authority experiment — isolated, main.py untouched

Corpus-authoring step: the C1 schema-organization relationship was authored into the
vault as scoped `authority` fields (2 pages, no generic fields). Then a mechanism ladder
was tested **outside** `main.py`, between the candidate set and the frozen reranker.

## Authored (vault change)

    wiki/data-model.md
      authority: [{topic: database-schema-organization, status: current,
                   supersedes: ianus-modular-analysis-and-implementation-plan}]

    wiki/ianus-modular-analysis-and-implementation-plan.md
      authority: [{topic: database-schema-organization, status: superseded,
                   superseded_by: data-model}]

Logged in `~/knowledge/ianus/log.md`. `index.md` unchanged (summaries unaffected).

Verification:
- parses with a real YAML parser; the map resolves in both directions; no dangling
  references; reciprocity holds (each side names the other)
- chunk text is **byte-identical** to the frozen benchmark (80/80 chunks), because
  frontmatter is stripped before chunking — so the frozen numbers stay comparable
- AB-Brain's watcher re-indexed the vault on its own; `abbrain validate` passes
  (80 vectors, corpus current)

## Mechanism rules tested

- topic-scoped: activates only when the candidate set holds BOTH a `current` and a
  `superseded` page for the same topic
- preference, not erasure: nothing is removed (verified — the superseded chunk stays a
  candidate in every variant)
- no-op by construction when no topic is in conflict

## Ladder (d04, 16 candidates)

    variant                       cand. order changed   delivered order
    V0 baseline (frozen)          no                    current #1, superseded #2
    V1 annotation only             no                    current #1, superseded #2
    V2 partition only              yes                   current #1, superseded #2
    V3 partition + annotation      yes                   current #1, superseded #3

## The result that matters: the failure no longer reproduces

The experiment was designed to fix a superseded-above-current ordering. At the frozen
configuration that ordering is already correct in all three frozen passes:
`data-model::Organization` (current) at #1, the older plan's proposal at #2, every pass.

The original observation was real but belongs to the **v1–v5 pipeline** — before sibling
expansion and the joint-sufficiency prompt changed the merge order. So today this failure
class has **zero reproducing benchmark failures**, and the promotion criterion is unmet:
there is nothing for the adjustment to fix.

## Regression over the 35 answerable questions (why not to promote even so)

    V1 annotation only      candidate order unchanged; answered 34/35; LOST: s03
                            (ANSWERABLE -> ABSTAIN); tokens 2,619/q (+1.9%)
    V2 partition only       order changed for 17/35; answered 35/35; lost: none;
                            state changes: none; tokens 2,570/q (+0.0%)
    V3 partition + annot.   order changed for 17/35; answered 35/35; lost: none;
                            state changes: none; tokens 2,619/q (+1.9%)

Two findings worth keeping:

1. **Authority text inside the prompt is a gate-destabilising lever.** V1 never changed
   candidate order and still lost `s03` — the same failure mode as the rejected v5
   named-artifact clause: adding semantic text to the candidates perturbs the
   sufficiency decision. Any future authority mechanism should not put authority prose
   in the prompt.
2. **The partition is behaviour-preserving on this benchmark.** V2 reorders candidates
   for 17 of 35 questions (the two conflicting pages co-occur widely) and changes no
   answer, no state and no contract outcome. That is useful safety evidence: if a
   conflict ever does reproduce, the reordering route is already measured as
   non-destructive, and it costs nothing (tokens identical to baseline).

## Decision

- **Keep the authored fields.** They are factual, scoped to one real conflict, and they
  document a relationship that previously lived only in prose. Nothing reads them yet,
  which is intended for a corpus-authoring step.
- **Do not promote an adjustment into the frozen pipeline.** With no reproducing failure,
  promotion would be architecture by anticipation. The frozen layer stays as it is.
- **If promotion is ever justified** (a superseded claim reaching #1 in a real run),
  the candidate mechanism is **V2 partition only** — topic-scoped, no prompt text, no
  token cost, already measured as non-destructive. V1/V3 are ruled out by the s03 loss.
- **C6 (source provenance per concept page) remains a recorded corpus limitation**,
  not something to manufacture from dates or link counts.

## Reproduce

    python3 eval/verify_authority_authoring.py    # YAML, map, chunk-identity (needs the API key env)
    python3 eval/authority_experiment.py          # ladder + regression (~90k tokens)
