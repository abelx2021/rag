# LLM Wiki — System Schema

A personal, multi-domain knowledge system. Each **domain** is its own Obsidian vault under
`~/knowledge/<vault-name>/`. Claude writes and maintains the wikis; the user curates
sources, directs the analysis, and asks the questions.

The wiki is a **persistent, compounding artifact** — knowledge is compiled once and kept
current, never re-derived from scratch per query.

## Directory layout

```
~/knowledge/
├── CLAUDE.md            ← this file: the shared schema for every vault
├── _template/           ← vault scaffold, copied by /new-domain
└── <vault-name>/        ← one Obsidian vault per domain
    ├── CLAUDE.md        ← per-vault conventions (subject, emphasis, naming)
    ├── raw/             ← immutable source documents (read, never edit)
    ├── wiki/            ← LLM-generated pages (Claude owns this entirely)
    ├── index.md         ← content catalog: one line per page
    └── log.md           ← append-only timeline of ingests / queries / lints
```

## Three layers

1. **raw/** — curated, immutable sources (articles, papers, notes, data). Source of truth.
2. **wiki/** — structured, interlinked markdown Claude creates and maintains: entity pages,
   concept pages, summaries, comparisons, synthesis. Cross-referenced with `[[wikilinks]]`.
3. **Schema** — this file plus each vault's CLAUDE.md. Encodes conventions and workflows.

## Retrieval (AB-Brain)

Retrieval is `abbrain`: a FAISS index plus a knowledge graph over the compiled markdown, built
locally (`embeddinggemma:latest` via Ollama on 127.0.0.1:11434 — nothing is uploaded). Every vault
listed in `~/.config/abbrain/config.toml` is indexed under its own name (`ianus`, `Teams`) with its
own index, graph, state database and job queue.

```bash
abbrain retrieve "<question>"                      # every vault, labelled; progressive L1→L6
abbrain retrieve "<question>" --vault-name Teams   # one vault only
abbrain retrieve "<question>" --json               # {vault: {trace, context, citations}}
abbrain status                                     # per-vault index / graph / job state
abbrain index update                               # re-embed changed pages (idempotent)
abbrain graph query "<question>"                   # traverse the knowledge graph
abbrain graph god-nodes                            # the most connected pages
abbrain validate                                   # derived layers against the vault
```

What a query is allowed to assemble — this is what decides the token bill:

```bash
abbrain retrieve "<question>" --evidence summaries   # catalogue + one-paragraph summaries only
abbrain retrieve "<question>" --evidence chunks      # + top indexed passages (the default)
abbrain retrieve "<question>" --evidence auto        # escalate to whole sections only if needed
abbrain retrieve "<question>" --full                 # always whole sections (most tokens)
abbrain retrieve "<question>" -k 4 --item-chars 600  # fewer pieces, shorter pieces
```

Use `summaries` for "what is X / who owns Y" (tens of tokens, no embeddings), `chunks` for detail
(small passages, semantic match), and only reach for `--full` when the surrounding prose matters —
that is the mode that hands over whole documents. Measured on this vault: `summaries` ≈ 90 tokens,
`chunks` ≈ 800, `--full` ≈ 1,800 for the same question.

The indexed corpus is `wiki/**/*.md` plus `raw/**/*.md`, so saved chat transcripts are searchable
by meaning too. A vault can override those globs in its `[[vault]]` table. `index.md`, `log.md` and
`.obsidian/` are excluded by design. AB-Brain never writes to a vault.

**Never answer from the assembled context alone.** After retrieving, READ the top matching files in
full, then synthesize an answer with citations as `[[wikilinks]]` to the pages.

## Operations

### Ingest (add a source)
1. Confirm the source is in the vault's `raw/` (copy it in if it's elsewhere).
2. Read the source fully.
3. Discuss key takeaways with the user — what to emphasize, what's new vs. existing.
4. Write a summary page in `wiki/`.
5. Update `index.md` (add the entry; adjust summaries if needed).
6. Update any existing entity/concept pages the source touches — add facts, note
   contradictions, flag where new data supersedes old claims.
7. Append to `log.md`: `## [YYYY-MM-DD] ingest | <Source Title>`.
8. Re-index so the new page is searchable: `abbrain index update --vault-name <vault>` (idempotent — only changed pages are re-embedded; the AB-Brain watcher would also pick the change up within seconds on its own).

A single source may touch 10–15 pages. Prefer one source at a time; stay involved.

### Query (answer a question)
1. `abbrain retrieve "<question>" --vault-name <vault>` (see Retrieval).
2. Read the top matching pages fully (and their linked pages where relevant).
3. Synthesize the answer with citations.
4. If the answer is worth keeping (a comparison, an analysis, a new connection),
   file it back as a new `wiki/` page, update `index.md`, and log it as `query`.

### Lint (health check)
Look for:
- contradictions between pages
- stale claims superseded by newer sources
- orphan pages with no inbound `[[links]]`
- important concepts mentioned but lacking their own page
- missing cross-references
- data gaps that could be filled with a web search

Report findings + proposed fixes. Apply only what the user confirms.

## Page conventions

- Start every page with a one-sentence summary (the "what is this" line).
- Use `[[wikilinks]]` for internal links; prefer them over URLs.
- Cite sources by linking the raw file or naming the source.
- Frontmatter on every page — at minimum `tags` and `created`:

  ```yaml
  ---
  tags: [concept]        # concept | entity | source | summary | comparison | synthesis
  created: 2026-09-15
  ---
  ```

- Filenames: kebab-case, e.g. `retrieval-vs-generation.md`.

## index.md and log.md

- **index.md** — catalog of every page: `- [[page-name]] — one-line summary`, grouped by
  category. Read it first to route queries. Update on every ingest.
- **log.md** — append-only. Every entry starts `## [YYYY-MM-DD] <type> | <Title>`,
  where `<type>` ∈ `ingest | query | lint`. Parseable:
  `grep "^## \[" log.md | tail -5`.

## Adding a domain

`/new-domain <name>` copies `_template/` into `~/knowledge/<name>/`, registers it with
the local embedding model, and builds vectors. The user then opens the folder as a vault in Obsidian
(Open folder as vault → select `~/knowledge/<name>`).
