# Gating + retrieval layer: FROZEN

Frozen after 3 identical passes on the 40-question benchmark. Any further change
to this layer must be justified by a new hypothesis, not by benchmark squeezing.

## Frozen configuration (main.py)

    VECTOR_K  = 10
    SIBLING_K = 3      # fitted to this benchmark, NOT a universal optimum
    GRAPH_K   = 10
    FINAL_K   = 3

**SIBLING_K=3 caveat.** The sweep showed K=1 and K=2 behave exactly like K=0
(35/36 candidate recall) and K=3 is the minimum that closes the hole, because
d14's correct chunk is the seed document's 3rd sibling. It is the cheapest value
that works here, with zero margin: re-chunking the corpus, or adding a question
whose correct sibling sits deeper, silently reverts to 35/36. K=4 adds headroom
at +4.6% tokens. Re-run `eval/sweep.py` before changing it.

Prompt: joint sufficiency (passages judged together, not one at a time), with
relatedness explicitly rejected as a substitute for sufficiency.

Deterministic identifier pre-gate: if the question names a traceable identifier
(`REQ-*`, `SEC-*`, `INT-*`, `NFR-*`, `DEC-*`, `RSK-*`, `EP-*`, `ADR-*`) that
occurs nowhere in the candidate evidence, the pipeline returns ABSTAIN without
calling the model. Ordinary named concepts are deliberately outside the grammar.

Reranker contract: `{"answerable": bool, "indices": [...]}` behind
`validate_decision()`. Three states only - ANSWERABLE / ABSTAIN /
CONTRACT_FAILURE - and a contract failure is never an empty result. Decisions
also carry `gate: identifier_pregate | reranker` so provenance stays visible
without adding a fourth state.

## Freeze target, as measured (3/3 passes)

    retrieval     merged recall              35/35     PASS
    answerable    answered                   35/35     PASS
    answerable    false abstention            0/35     PASS
    unanswerable  correct abstention          5/5      PASS
    interface     contract failures           0/40     PASS
    efficiency    2,499 rerank input tokens/q (retrieval-only baseline: 2,358, +6.0%)
    stability     states identical           40/40     PASS
                  identifiers gate fires      1 per pass (i01 only)

## Benchmark definition

35 answerable + 5 unanswerable. Ground truth has two layers in
`eval/questions.json`: `expect` = the original chunk-location labels, kept
unchanged for historical comparison; `vault_can_answer` = whether the indexed
corpus can actually support the answer. The reclassification history, including
the o03 revert and the i01 reason, is recorded in that file.

## Known properties and limits (do not mistake these for bugs)

1. **i01** (`INT-PUC-006`) abstains deterministically: the wiki's PUC key-rules
   chunk carries no requirement identifiers. Vault fix, not a retrieval fix -
   restoring the identifiers from the raw docx would make it answerable.
2. **o03** (digital file) is answerable from a one-line definition. Accepted:
   a brief answer can rest on a brief definition.
3. **Passage order floats; state does not.** Across the 3 passes, top-1 and
   top-2 passages were identical 40/40; the third slot differed on 3/40
   (d06, s01, i04). State agreement is the property that must hold; do not tune
   the gate on ranking order, and do not treat one run as a contract.
4. **Supersession is not handled.** d04 still ranks the superseded 8-schema
   list above the current 9-schema one. The corpus records supersession in
   prose and nothing in the pipeline reads it. This is the next workstream.
5. **raw/ is not indexed** (`WIKI` globs `wiki/**` only), so vault-gap
   questions have no answer path.

## Re-running

    cd ~/Desktop/rag
    python3 eval/test_validator.py        # 25/25 contract cases, no API
    python3 eval/test_identifier_gate.py  # 18/18 grammar + presence cases, no API
    python3 eval/run_eval_v6.py 1,2,3     # full benchmark, 3 passes

Historical runs: `results.json` (v1 chunk-location), `results_v2.json`,
`sweep_K*` (sibling sweep), `results_v3.json` (structured decision),
`results_v4_p*.json` (joint sufficiency), `results_v5_p*.json` (over-broad
named-artifact clause - rejected for instability), `results_v6_p*.json` (frozen).
