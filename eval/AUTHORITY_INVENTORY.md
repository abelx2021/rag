# Authority-signal inventory — ianus wiki

Read-only survey of the 12 wiki documents. Question: what does the corpus actually
expose for deciding "current vs superseded"? Produced by `eval/authority_inventory.py`
(no model, no network, no writes to the vault). **No code, retrieval, ranking or
metadata was changed.**

## 1. Frontmatter: structured authority does not exist

Every one of the 12 pages carries exactly two fields:

    tags     12/12
    created  12/12   (11 pages 2026-09-15, module-creation-checklist 2026-09-16)

Absent everywhere: `version`, `status`, `source`, `source_version`, `supersedes`,
`superseded_by`, `updated`, `date`. No page declares what it was compiled from, which
source version it reflects, whether it is current, or what it replaces.

Tags observed: `[entity]` 1, `[source]` 2, `[concept]` 8, `[synthesis]` 1.

**Verdict for architecture A (structured authority already exists): no.**

## 2. Supersession language: exists in prose, in 5 of 12 documents

| document | what it says | direction |
|---|---|---|
| `data-model` | "The earlier [[ianus-modular-analysis-and-implementation-plan]] proposed only 8 — `core`, `procedures`, `projects`, `documents`, `controls`, `integrations`, `audit`, `reporting`; `iam` and `finance` were added in the [[ianus-technical-operational-project-document]]." | names what is older AND what superseded it |
| `ianus-modular-analysis-and-implementation-plan` | "The earlier, analysis-oriented companion to the [[ianus-technical-operational-project-document]] (v1.3), which it feeds as an input attachment." + "Note the later [[data-model]] adds `iam` and `finance` schemas on top of these." | self-declares as earlier; forward pointer to the newer page |
| `module-catalog` | "The earlier [[ianus-modular-analysis-and-implementation-plan]] listed the modules slightly differently: it kept **Public section of beneficiaries** and **Reporting & BI** as two separate optional modules […] This consolidated table, with **Audit & Operations** promoted to a mandatory module and Reporting/Public merged, reflects the later [[ianus-technical-operational-project-document]]." | names the older page, the exact differences, and which one to believe |
| `modular-monolith-architecture` | "the subsequent modular analysis proposed a modular monolith, and that is treated as authoritative." | explicit precedence decision between two sources |
| `ianus-technical-operational-project-document` | "[[ianus-modular-analysis-and-implementation-plan]] — the modular analysis and implementation plan this document builds on." | declares its own input, not a supersession |

Pattern worth noting: the relationship is recorded **from both ends** — the newer page
carries the correction note ("the earlier X proposed only 8"), and the older page
carries a forward note ("the later data-model adds…"). Both are natural language.

**Verdict for architecture B (authority exists only in prose): yes, partially.** It
covers the main lineage chain; it is absent everywhere else.

## 3. Dates: frontmatter `created` is useless as an authority signal

All 12 pages were created on 2026-09-15 or -09-16, i.e. in one or two sittings. The
dates that carry meaning are inside the prose:

    ianus-technical-operational-project-document v1.3   2026-09-07   (the source doc date)
    ISTAT/PUC context tables                            April 2025   (external snapshot)
    PUC 4.0 / SNM Application Protocol 1.2 / Vademecum 1.0 / Controls 1.0  (external source versions)
    .NET 10 LTS support end                             2028-11-14   (a future date in prose)

Measured consequence: the newest page by `created` is `module-creation-checklist`
(2026-09-16), a derived synthesis page, while `ianus-technical-operational-project-document`
(2026-09-15) is the authority for scope, modules and delivery. **A "newer `created`
date wins" rule would actively pick the wrong page.** This is the concrete evidence
for not building a chronology rule.

## 4. Reference graph: a weak load-bearing proxy, not an authority signal

    data-model                                      in=11   out=6
    ianus-technical-operational-project-document    in=11   out=9
    ianus-platform                                  in= 9   out=8
    modular-monolith-architecture                   in= 8   out=5
    ianus-modular-analysis-and-implementation-plan  in= 6   out=7
    module-catalog                                  in= 6   out=6
    identity-and-access-management                  in= 6   out=4
    instance-isolation                              in= 5   out=6
    document-pipeline                               in= 4   out=4
    audit-trail                                     in= 3   out=6
    puc-rgs-regis-snm-connector                     in= 2   out=4
    module-creation-checklist                       in= 0   out=6   (orphan)

Inbound count tracks how load-bearing a page is, but it does **not** distinguish current
from superseded: `ianus-modular-analysis-and-implementation-plan` has 6 inbound links,
including one from the very document that supersedes it, while carrying a superseded
schema list. Using centrality as authority would preserve exactly the error we are
trying to fix.

## 5. The schema conflict: it is 8 vs 10, not 8 vs 9

Correcting the shorthand used earlier (mine included): **9 is the module count, 10 is
the current schema count.**

    data-model (backticked enumeration, n=10)
      core, iam, procedures, projects, finance, documents, controls, integrations, reporting, audit

    ianus-technical-operational-project-document (backticked, n=8)
      "9 modules across core, procedures, projects, documents, controls, integrations, reporting, audit"
      -> 9 modules mapped to 8 schema names; no iam, no finance, although this document
         is the one credited elsewhere with adding them

    ianus-modular-analysis-and-implementation-plan (backticked, n=10)
      core, iam, procedures, projects, finance, documents, controls, integrations, reporting, audit
      -> but iam/finance appear here only because the page was PATCHED with a forward note
         ("Note the later [[data-model]] adds `iam` and `finance` schemas on top of these"),
         not because the original analysis listed them

Measured consequence: a naive extractor sees the same 10-name set on both `data-model`
and the older plan page, and 8 names on the tech-op page. Counting names per page
cannot tell you which page is current — the older page now contains the newer names.

Other numeric claims show no divergence: "9 modules" is consistent across the four pages
that state it; 54 information structures, 55 validation codes, 72 TC sheets appear only
on the PUC page; 12 Sprint 0 decisions and 12 risks only on the tech-op page.

## Conflict register (resolvability by text, not by metadata)

| # | conflict | resolvable from the text? | how |
|---|---|---|---|
| C1 | Schema set: 8 names (tech-op page) vs 10 names (data-model) | Partially | `data-model` states the lineage explicitly ("the earlier plan proposed only 8 … iam and finance were added"). The tech-op page's own 8-name list is not marked as abbreviated, so nothing in it says its list is incomplete |
| C2 | Module list: plan's version (Public section + Reporting & BI separate, audit cross-functional) vs consolidated (Audit & Operations mandatory, Reporting/Public merged) | Yes | `module-catalog` names the older page, both differences, and the superseding document |
| C3 | Which source governs the architecture: the demo (microservices) or the modular analysis (modular monolith) | Yes | `modular-monolith-architecture` states the analysis "is treated as authoritative" |
| C4 | Document lineage / which is the input | Yes | both pages state it (plan "feeds as an input attachment"; tech-op "builds on") |
| C5 | Currency by date | No — and misleading | all pages same-day; newest page is the derived synthesis |
| C6 | Which source version a concept page reflects | No | source versions appear only on the two source pages and the PUC page; concept pages carry none |

## Which architecture we actually have

    A. structured authority exists        -> NO. Only tags + created, on all 12 pages.
    B. authority exists only in prose     -> YES, partially. 5 of 12 pages, covering the
                                             lineage chain and 3 of the 6 conflicts.
    C. authority is missing               -> YES, for the parts that matter most:
                                             per-claim source version (C6) and any
                                             machine-readable "authoritative for what?"
                                             statement. The schema conflict (C1) is exactly
                                             the case where prose covers the direction but
                                             the losing page remains self-inconsistent.

Both B and C are true, at different scopes. Nothing in the corpus is machine-readable,
and the two signals that are cheaply available — `created` and inbound link count — are
demonstrably wrong or uninformative for this purpose.

## Measured impact so far

**Corrected after the authority experiment (see `AUTHORITY_EXPERIMENT.md`): the d04
failure does NOT reproduce at the frozen v6 configuration.** The observation that the
superseded 8-name list outranks the current 10-name list was measured on the v1–v5
pipeline. At the frozen configuration all three passes deliver
`data-model::Organization` (current) at #1 and the older proposal at #2:

    v6 pass 1/2/3   #1 data-model::Organization (current)
                    #2 ianus-modular-analysis…::Proposed schema organisation (superseded)
                    #3 data-model::Table catalog

So at present the class has **zero reproducing benchmark failures**. The C1 relationship
is real and was worth authoring, but there is no current evidence justifying a ranking
adjustment in the pipeline.

## Open questions for the design decision (no implementation yet)

1. Is the fix corpus-authoring (add authority fields to the 2–3 pages that need them, and
   mark the tech-op page's schema list as abbreviated) or pipeline-side (parse the prose
   relations into a typed authority signal)?
2. If fields are added, which ones? The vault schema says frontmatter must carry *at
   minimum* `tags` and `created`, so additional fields are permitted but become a new
   convention every page must respect.
3. Scope of an authority signal: page-level ("this page supersedes that one") or
   claim-level ("this page is authoritative for schemas")? C1 and C6 suggest claim-level
   scope, which is a heavier commitment.
4. Whether to act at all before a second real conflict appears in the benchmark.
