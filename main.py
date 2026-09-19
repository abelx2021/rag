import os
import re
import json
import hashlib
import pickle
import numpy as np
import ollama

from pathlib import Path
from collections import defaultdict
from openai import OpenAI


# ============================================================
# CONFIG
# ============================================================

WIKI = Path("/Users/ab/knowledge/ianus/wiki")

EMBEDDING_MODEL = "embeddinggemma"
DEEPSEEK_MODEL = "deepseek-chat"

VECTOR_K = 10
# Minimum sibling expansion that closes the candidate-recall hole on the
# 40-question benchmark (sweep: K=1 and K=2 behave exactly like K=0; K=3 is
# required because d14's correct chunk is the seed document's 3rd sibling).
# This value is FITTED TO THAT BENCHMARK, not a universal optimum - K=4 is the
# conservative alternative. Do not raise it without re-running eval/sweep.py.
SIBLING_K = 3
GRAPH_K = 10
FINAL_K = 3


# ============================================================
# CACHE
# ============================================================

INDEX_DIR = Path(".index")
INDEX_DIR.mkdir(exist_ok=True)

CHUNKS_CACHE = INDEX_DIR / "chunks.pkl"
EMB_CACHE = INDEX_DIR / "embeddings.npy"
HASH_CACHE = INDEX_DIR / "hashes.pkl"


# ============================================================
# REGEX
# ============================================================

RE_FRONTMATTER = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n?",
    re.DOTALL,
)

RE_HTML_COMMENT = re.compile(
    r"<!--.*?-->",
    re.DOTALL,
)

RE_WIKI_LINK = re.compile(
    r"\[\[([^\]|#]+)"
    r"(?:#[^\]|]+)?"
    r"(?:\|[^\]]+)?\]\]"
)

RE_HEADING = re.compile(
    r"^(#{1,6})\s+(.+?)\s*$"
)


# ============================================================
# DEEPSEEK
# ============================================================

if "DEEPSEEK_API_KEY" not in os.environ:
    raise RuntimeError(
        "DEEPSEEK_API_KEY is not set."
    )

deepseek = OpenAI(
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url="https://api.deepseek.com",
)



# ============================================================
# FRONTMATTER
# ============================================================

def parse_frontmatter(text):
    m = RE_FRONTMATTER.match(text)

    if not m:
        return text, {}

    metadata = {}

    for line in m.group(1).splitlines():
        if ":" not in line:
            continue

        key, value = (
            p.strip()
            for p in line.split(":", 1)
        )

        if (
            value.startswith("[")
            and value.endswith("]")
        ):
            value = [
                v.strip()
                for v in value[1:-1].split(",")
                if v.strip()
            ]

        metadata[key] = value

    return text[m.end():], metadata


# ============================================================
# CLEAN TEXT
# ============================================================

def remove_html_comments(text):
    return RE_HTML_COMMENT.sub("", text)


# ============================================================
# OBSIDIAN LINKS
# ============================================================

def extract_wiki_links(text):
    seen = []

    for match in RE_WIKI_LINK.findall(text):
        link = match.strip()

        if link and link not in seen:
            seen.append(link)

    return seen


# ============================================================
# CHUNK MARKDOWN
# ============================================================

def chunk_markdown(path):
    text = path.read_text(
        encoding="utf-8",
        errors="ignore",
    )

    text, metadata = parse_frontmatter(text)
    text = remove_html_comments(text)

    chunks = []
    heading_stack = []

    section = "Introduction"
    lines = []

    def save():
        body = "\n".join(lines).strip()

        if not body:
            return

        chunks.append({
            "document": path.stem,
            "section": section,
            "path": str(path),
            "text": body,
            "metadata": metadata.copy(),
            "links": extract_wiki_links(body),
        })

    for line in text.splitlines():
        heading = RE_HEADING.match(line)

        if not heading:
            lines.append(line)
            continue

        save()
        lines = []

        level = len(heading.group(1))
        title = heading.group(2).strip()

        if level == 1:
            heading_stack = []
            section = "Introduction"
            continue

        heading_stack = (
            heading_stack[:level - 2]
            + [title]
        )

        section = " > ".join(
            heading_stack
        )

    save()

    return chunks


# ============================================================
# FILE HASH
# ============================================================

def file_hash(path):
    return hashlib.md5(
        path.read_bytes()
    ).hexdigest()


# ============================================================
# LOAD WIKI
# ============================================================

def load_wiki():
    files = sorted(
        WIKI.rglob("*.md")
    )

    current_hashes = {
        str(f): file_hash(f)
        for f in files
    }

    cache_exists = (
        CHUNKS_CACHE.exists()
        and HASH_CACHE.exists()
        and EMB_CACHE.exists()
    )

    if cache_exists:
        old_hashes = pickle.loads(
            HASH_CACHE.read_bytes()
        )

        if old_hashes == current_hashes:
            chunks = pickle.loads(
                CHUNKS_CACHE.read_bytes()
            )

            embeddings = np.load(
                EMB_CACHE
            )

            print(
                f"Loaded {len(chunks)} chunks "
                "from cache (wiki unchanged)"
            )

            return (
                chunks,
                embeddings,
                current_hashes,
            )

    print(
        f"Found {len(files)} Markdown files "
        "— rebuilding index"
    )

    chunks = [
        chunk
        for f in files
        for chunk in chunk_markdown(f)
    ]

    print(
        f"Loaded {len(chunks)} chunks"
    )

    return chunks, None, current_hashes


# ============================================================
# EMBEDDING TEXT
# ============================================================

def text_for_embedding(c):
    return (
        f"title: {c['document']}\n"
        f"text: {c['section']}\n\n"
        f"{c['text']}"
    ).strip()


def query_for_embedding(query):
    return (
        "task: search result\n"
        f"query: {query}"
    )


# ============================================================
# LOAD + EMBED WIKI
# ============================================================

chunks, embeddings, current_hashes = (
    load_wiki()
)

if embeddings is None:
    texts = [
        text_for_embedding(c)
        for c in chunks
    ]

    print(
        f"Embedding {len(texts)} chunks..."
    )

    response = ollama.embed(
        model=EMBEDDING_MODEL,
        input=texts,
    )

    embeddings = np.array(
        response["embeddings"],
        dtype=np.float32,
    )

    print(
        "Embedding matrix:",
        embeddings.shape,
    )

    CHUNKS_CACHE.write_bytes(
        pickle.dumps(chunks)
    )

    HASH_CACHE.write_bytes(
        pickle.dumps(current_hashes)
    )

    np.save(
        EMB_CACHE,
        embeddings,
    )

else:
    print(
        "Embedding matrix:",
        embeddings.shape,
    )


# ============================================================
# DOCUMENT GRAPH
# ============================================================

graph = defaultdict(set)

for c in chunks:
    source = c["document"]

    for target in c["links"]:
        graph[source].add(target)


def get_neighbors(document):
    return sorted(
        graph.get(document, set())
    )


# ============================================================
# QUERY EMBEDDING
# ============================================================

def embed_query(query):
    response = ollama.embed(
        model=EMBEDDING_MODEL,
        input=query_for_embedding(query),
    )

    return np.array(
        response["embeddings"][0],
        dtype=np.float32,
    )


# ============================================================
# VECTOR SEARCH
# ============================================================

def search(
    q_emb,
    k=VECTOR_K,
):
    scores = embeddings @ q_emb

    k = min(
        k,
        len(scores),
    )

    top = np.argpartition(
        scores,
        -k,
    )[-k:]

    best = top[
        np.argsort(scores[top])[::-1]
    ]

    results = []

    for rank, i in enumerate(best, 1):
        result = chunks[i].copy()

        result["score"] = float(
            scores[i]
        )

        result["source"] = "vector"
        result["vector_rank"] = rank

        results.append(result)

    return results


# ============================================================
# SIBLING + GRAPH EXPANSION
# ============================================================

def expanded_search(
    q_emb,
    document,
    sibling_k=SIBLING_K,
    graph_k=GRAPH_K,
):
    neighbors = set(
        get_neighbors(document)
    )

    scores = embeddings @ q_emb

    siblings = []
    graph_results = []

    for i, c in enumerate(chunks):
        score = float(
            scores[i]
        )

        # Same document as the vector seed
        if c["document"] == document:
            result = c.copy()

            result["score"] = score
            result["source"] = "sibling"
            result["vector_rank"] = None

            siblings.append(result)

        # Explicitly linked document
        elif c["document"] in neighbors:
            result = c.copy()

            result["score"] = score
            result["source"] = "graph"
            result["vector_rank"] = None

            graph_results.append(result)

    siblings.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    graph_results.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    return (
        siblings[:sibling_k],
        graph_results[:graph_k],
    )


# ============================================================
# MERGE CANDIDATES
# ============================================================

def merge_candidates(
    vector_results,
    siblings,
    graph_results,
):
    merged = []
    seen = set()

    groups = (
        vector_results,
        siblings,
        graph_results,
    )

    for group in groups:
        for c in group:
            key = (
                c["document"],
                c["section"],
            )

            if key in seen:
                continue

            merged.append(
                c.copy()
            )

            seen.add(key)

    return merged


# ============================================================
# IDENTIFIER PRE-GATE - DETERMINISTIC
# ============================================================

# Traceable identifiers that occur verbatim in the corpus. Kept as one grammar
# so this check stays mechanical: an identifier either occurs in the evidence
# or it does not, and no model is asked to guess.
#
# Ordinary named concepts are deliberately NOT in this grammar. "digital file"
# and "microservices architecture" are sufficiency judgements, not identity
# checks - putting them here would make the gate lexical matching.
RE_IDENTIFIER = re.compile(
    r"\b(?:"
    r"REQ-[A-Z]+-\d+|"
    r"SEC-[A-Z]+-\d+|"
    r"INT-[A-Z]+-\d+|"
    r"NFR-[A-Z]+-\d+|"
    r"DEC-[A-Z]+-\d+|"
    r"DEC-\d+|"
    r"RSK-\d+|"
    r"EP-\d+|"
    r"ADR-\d+"
    r")\b",
    re.IGNORECASE,
)


def extract_identifiers(text):
    """Identifiers named in text, upper-cased, order preserved, deduplicated."""

    seen = []

    for match in RE_IDENTIFIER.findall(
        text or ""
    ):
        identifier = match.upper()

        if identifier not in seen:
            seen.append(identifier)

    return seen


def missing_identifiers(question, candidates):
    """Identifiers named in the question that do not occur in the evidence."""

    wanted = extract_identifiers(question)

    if not wanted:
        return []

    evidence = "\n".join(
        c["text"]
        for c in candidates
    ).upper()

    return [
        identifier
        for identifier in wanted
        if identifier not in evidence
    ]


# ============================================================
# DEEPSEEK RERANKER - STRUCTURED DECISION
# ============================================================

# Three downstream states. CONTRACT_FAILURE is deliberately NOT an empty
# result: an unparseable or invalid reranker reply is an engineering failure
# and must stay visible instead of being laundered into "no answer found".
STATE_ANSWERABLE = "ANSWERABLE"
STATE_ABSTAIN = "ABSTAIN"
STATE_CONTRACT_FAILURE = "CONTRACT_FAILURE"


def validate_decision(
    raw,
    n_candidates,
    k=FINAL_K,
):
    """Strictly validate the reranker's structured decision.

    Returns (state, indices, reason). Any violation of the contract returns
    STATE_CONTRACT_FAILURE with a machine-readable reason and empty indices;
    callers must branch on state, never on "indices is empty".
    """

    if raw is None or not raw.strip():
        return (
            STATE_CONTRACT_FAILURE,
            [],
            "empty_response",
        )

    try:
        payload = json.loads(
            raw.strip()
        )

    except ValueError as exc:
        return (
            STATE_CONTRACT_FAILURE,
            [],
            f"invalid_json: {exc}",
        )

    if not isinstance(
        payload,
        dict,
    ):
        return (
            STATE_CONTRACT_FAILURE,
            [],
            "not_a_json_object",
        )

    for field in (
        "answerable",
        "indices",
    ):
        if field not in payload:
            return (
                STATE_CONTRACT_FAILURE,
                [],
                f"missing_field: {field}",
            )

    answerable = payload["answerable"]
    indices = payload["indices"]

    # bool is a subclass of int: check it explicitly.
    if not isinstance(
        answerable,
        bool,
    ):
        return (
            STATE_CONTRACT_FAILURE,
            [],
            f"answerable_not_boolean: {type(answerable).__name__}",
        )

    if not isinstance(
        indices,
        list,
    ):
        return (
            STATE_CONTRACT_FAILURE,
            [],
            f"indices_not_list: {type(indices).__name__}",
        )

    if not answerable:
        if indices:
            return (
                STATE_CONTRACT_FAILURE,
                [],
                "abstain_with_nonempty_indices",
            )

        return (
            STATE_ABSTAIN,
            [],
            None,
        )

    for i in indices:
        if isinstance(
            i,
            bool,
        ) or not isinstance(
            i,
            int,
        ):
            return (
                STATE_CONTRACT_FAILURE,
                [],
                f"index_not_integer: {i!r}",
            )

        if not 0 <= i < n_candidates:
            return (
                STATE_CONTRACT_FAILURE,
                [],
                f"index_out_of_range: {i} (n_candidates={n_candidates})",
            )

    if len(indices) != k:
        return (
            STATE_CONTRACT_FAILURE,
            [],
            f"wrong_index_count: {len(indices)} != {k}",
        )

    if len(set(indices)) != len(indices):
        return (
            STATE_CONTRACT_FAILURE,
            [],
            f"duplicate_indices: {indices}",
        )

    return (
        STATE_ANSWERABLE,
        list(indices),
        None,
    )


def rerank(
    query,
    candidates,
    k=FINAL_K,
):
    # Deterministic identity check first: if the question names a traceable
    # identifier that appears nowhere in the evidence, no passage can establish
    # the mapping and the model is never consulted. This keeps "does the
    # evidence contain the thing being asked about" out of the LLM's job.
    absent = missing_identifiers(
        query,
        candidates,
    )

    if absent:
        print(
            f"IDENTIFIER PRE-GATE: {', '.join(absent)} named in the "
            f"question and absent from all {len(candidates)} candidates "
            f"- ABSTAIN without consulting the model"
        )

        return {
            "state": STATE_ABSTAIN,
            "answerable": False,
            "indices": [],
            "reason": (
                "identifier_absent_from_evidence: "
                + ", ".join(absent)
            ),
            "raw": None,
            "gate": "identifier_pregate",
            "n_candidates": len(candidates),
            "usage": None,
            "passages": [],
        }

    passages = "\n\n---\n\n".join(
        (
            f"CANDIDATE {i}\n\n"
            f"Document: {c['document']}\n"
            f"Section: {c['section']}\n\n"
            f"{c['text']}"
        )
        for i, c in enumerate(candidates)
    )

    prompt = f"""
You are a precision reranker for a RAG system.

QUESTION:
{query}

Decide TWO things, in this order.

STEP 1 - SUFFICIENCY.
Determine whether the candidate passages,
considered together, contain enough
information to answer the question.

Do not require one single passage to hold
the complete answer: several passages may
jointly support it. Combine them before
deciding.

ANSWERABLE means the answer can be derived
from the supplied passages without
introducing facts that are not in them.

ABSTAIN means information required to
answer the question is missing, even after
considering all the passages together.

Relatedness alone is not sufficient. A
passage that merely covers the same subject,
names the topic, or discusses a neighbouring
concept does not make the passages
sufficient.

STEP 2 - RANKING (only if the passages are
sufficient).
Choose the {k} passages that most directly
explain the answer, most useful first.
Prefer concrete procedures, mechanisms,
steps, protocols, rules, data flows or
facts over general introductions.

Do not answer the question. Do not explain.

Respond with a single JSON object and
nothing else.

If the passages are sufficient:

{{"answerable": true, "indices": [10, 3, 9]}}

If they are not sufficient:

{{"answerable": false, "indices": []}}

"indices" must contain exactly {k} distinct
candidate numbers when "answerable" is true,
and must be empty when it is false.

CANDIDATES:

{passages}
""".strip()

    response = (
        deepseek.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            temperature=0,
            max_tokens=120,
            response_format={
                "type": "json_object",
            },
        )
    )

    raw = (
        response.choices[0].message.content
        or ""
    )

    print(
        "DeepSeek:",
        raw.strip(),
    )

    usage = None

    if response.usage:
        u = response.usage

        usage = {
            "input": u.prompt_tokens,
            "output": u.completion_tokens,
            "total": u.total_tokens,
        }

        print(
            f"Tokens: "
            f"{u.prompt_tokens} input + "
            f"{u.completion_tokens} output = "
            f"{u.total_tokens}"
        )

    state, indices, reason = validate_decision(
        raw,
        len(candidates),
        k=k,
    )

    passages = []

    for i in indices:
        result = candidates[i].copy()

        result["rerank_input_rank"] = (
            i + 1
        )

        passages.append(result)

    if state == STATE_CONTRACT_FAILURE:
        print(
            f"RERANKER CONTRACT FAILURE ({reason}) - "
            f"this is NOT an abstention"
        )

    elif state == STATE_ABSTAIN:
        print(
            "RERANKER ABSTAINED: no candidate contains "
            "sufficient information to answer"
        )

    return {
        "state": state,
        "answerable": state == STATE_ANSWERABLE,
        "indices": indices,
        "reason": reason,
        "raw": raw.strip(),
        "gate": "reranker",
        "n_candidates": len(candidates),
        "usage": usage,
        "passages": passages,
    }


# ============================================================
# RETRIEVE
# ============================================================

def retrieve(
    query,
    vector_k=VECTOR_K,
    sibling_k=SIBLING_K,
    graph_k=GRAPH_K,
    final_k=FINAL_K,
):
    # --------------------------------------------------------
    # EMBED QUESTION ONCE
    # --------------------------------------------------------

    q_emb = embed_query(
        query
    )

    # --------------------------------------------------------
    # VECTOR SEARCH
    # --------------------------------------------------------

    vector_results = search(
        q_emb,
        k=vector_k,
    )

    print("\nVECTOR RESULTS")
    print("-" * 70)

    for rank, c in enumerate(
        vector_results,
        1,
    ):
        print(
            f"{rank:2}. "
            f"{c['score']:.3f} | "
            f"{c['document']} → "
            f"{c['section']}"
        )

    if not vector_results:
        return []

    # --------------------------------------------------------
    # SEED DOCUMENT
    # --------------------------------------------------------

    seed_document = (
        vector_results[0]["document"]
    )

    print(
        f"\nEXPANSION SEED: "
        f"{seed_document}"
    )

    # --------------------------------------------------------
    # SIBLING + GRAPH SEARCH
    # --------------------------------------------------------

    siblings, graph_results = (
        expanded_search(
            q_emb,
            seed_document,
            sibling_k=sibling_k,
            graph_k=graph_k,
        )
    )

    # --------------------------------------------------------
    # PRINT SIBLINGS
    # --------------------------------------------------------

    print("\nSIBLING RESULTS")
    print("-" * 70)

    for rank, c in enumerate(
        siblings,
        1,
    ):
        print(
            f"{rank:2}. "
            f"{c['score']:.3f} | "
            f"{c['document']} → "
            f"{c['section']}"
        )

    # --------------------------------------------------------
    # PRINT GRAPH RESULTS
    # --------------------------------------------------------

    print("\nGRAPH RESULTS")
    print("-" * 70)

    for rank, c in enumerate(
        graph_results,
        1,
    ):
        print(
            f"{rank:2}. "
            f"{c['score']:.3f} | "
            f"{c['document']} → "
            f"{c['section']}"
        )

    # --------------------------------------------------------
    # MERGE + DEDUPLICATE
    # --------------------------------------------------------

    merged = merge_candidates(
        vector_results,
        siblings,
        graph_results,
    )

    print(
        f"\nMERGED: "
        f"{len(merged)} candidates"
    )

    # --------------------------------------------------------
    # RERANK
    # --------------------------------------------------------

    print("\nRERANKING...")

    return rerank(
        query,
        merged,
        k=final_k,
    )


# ============================================================
# PRINT FINAL RESULTS
# ============================================================

def print_results(decision):
    state = decision["state"]

    print("\nFINAL RESULT")
    print("=" * 70)

    print(
        f"State: {state} | "
        f"candidates: {decision['n_candidates']}"
    )

    if state == STATE_ABSTAIN:
        if decision.get("gate") == "identifier_pregate":
            print(
                "\nABSTAIN - deterministic identifier "
                "pre-gate: the question names an "
                "identifier that occurs nowhere in the "
                "evidence, so no mapping can be "
                "established."
            )

            print(
                f"Reason: "
                f"{decision['reason']}"
            )

            return

        print(
            "\nABSTAIN - the reranker decided that no "
            "candidate passage contains sufficient "
            "information to answer."
        )

        print(
            f"Reranker reply: "
            f"{decision['raw']}"
        )

        return

    if state == STATE_CONTRACT_FAILURE:
        print(
            "\nCONTRACT FAILURE - the reranker reply did "
            "not satisfy the decision contract."
        )

        print(
            f"Reason: "
            f"{decision['reason']}"
        )

        print(
            f"Reranker reply: "
            f"{decision['raw']}"
        )

        print(
            "\nThis is an engineering failure, NOT an "
            "abstention: no passage is returned because "
            "none could be trusted."
        )

        return

    print(
        f"Indices: "
        f"{decision['indices']}"
    )

    for rank, r in enumerate(
        decision["passages"],
        1,
    ):
        print(
            f"\n{rank}. "
            f"{r['document']} → "
            f"{r['section']}"
        )

        source = r.get(
            "source",
            "vector",
        )

        vector_rank = r.get(
            "vector_rank"
        )

        if source == "vector":
            origin = (
                f"vector #{vector_rank}"
            )

        elif source == "sibling":
            origin = "sibling"

        elif source == "graph":
            origin = "graph"

        else:
            origin = source

        print(
            f"Found by: {origin} | "
            f"score: {r['score']:.3f}"
        )

        print(
            f"Rerank input: "
            f"#{r['rerank_input_rank']}"
        )

        print()
        print(
            r["text"]
        )


# ============================================================
# TEST
# ============================================================

query = (
    "How does IANUS send monitoring "
    "data to RGS?"
)

results = retrieve(
    query,
    vector_k=10,
    sibling_k=10,
    graph_k=10,
    final_k=3,
)

print_results(
    results
)