---
name: deep-sota
description: "Research the user's arXiv/repo knowledge base using a MCP retrieval tool called lodestone to answer questions with paper-grounded and repo-grounded citations. Use when the user is requesting research or building something new or greenfield. Use when you're considering calling lodestone MCP tools. Will ground the users request in research and also enable finding novelty."
argument-hint: <research question>
allowed-tools: mcp__lodestone__search mcp__lodestone__bm25 mcp__lodestone__lookup mcp__lodestone__browse mcp__lodestone__overview mcp__lodestone__collection mcp__lodestone__coverage mcp__lodestone__toc mcp__lodestone__toc_many mcp__lodestone__read mcp__lodestone__figure mcp__lodestone__repo_tree mcp__lodestone__read_code mcp__lodestone__repo mcp__lodestone__citations mcp__lodestone__tables mcp__lodestone__schema mcp__lodestone__query mcp__lodestone__ingest_paper mcp__lodestone__ingest_repo mcp__lodestone__ingest_post Read Grep Glob
---

# /deep-sota — paper & repo research over the lodestone knowledge base

Lodestone is an arXiv paper/repo research retrieval tool served entirely from a SQLLite database. /deep-sota is the skill that contains the knowledge for how to use it. /deep-sota was invoked for one of three reasons:

1. Ingest a new paper / repo / blog post into lodestone
2. Fulfill a user task that should be informed by research
3. You're planning an implementation and should ground the plan in research

> **If `mcp__lodestone__*` tools aren't available in this session**, lodestone isn't loaded. Stop immediately and tell the user to run `/lodestone:doctor` — `/deep-sota` is non-functional without those tools. Don't attempt to substitute web search, training-data recall, or hand-rolled SQLite queries; the whole point of `/deep-sota` is paper-grounded answers from the user's local corpus.

**When not to use lodestone:** if the user's question is about the codebase you're sitting in (its files, its bugs, its tests, its history), don't reach for lodestone. Lodestone is for arXiv research and ingested external repos, not for navigating the current working directory.

## Ingestion

The user passed an arXiv link, github link, or blog post URL that they want ingested into lodestone. Ignore everything beyond the Ingestion section and ingest the link.

### Confirm classify-stage config (ingestion-only)

Ingestion is the only path that touches an LLM (one structured "classify" call per source). Skip this subsection entirely when /deep-sota was invoked for research or plan-grounding.

`Read(~/.config/lodestone/config.toml)` and confirm both:
- An `[llm]` section exists
- Both `provider` and `model` are set to non-empty strings under it

If the file is missing, the `[llm]` section is absent, or either value is empty / unset, **stop and tell the user**:

> Lodestone needs an LLM provider + model configured before it can ingest. Run `/lodestone:doctor` — it walks you through provider/model selection and writes `~/.config/lodestone/config.toml`. Then re-run this command.

Do not attempt to pick a provider or write the config yourself; doctor owns that flow. Do not invoke any ingest tool until config is in place.

If both values are present, proceed to **Run the ingest** below — trust the config. If the configured provider's API key isn't set in the environment, the ingest tool's classify stage will surface a clear error; no need to pre-check env vars here.

### Run the ingest

- **arXiv or ACL Anthology URL / bare ID** → `mcp__lodestone__ingest_paper(url=<arxiv_or_acl>)`. Accepts arxiv (`2512.03413`, `https://arxiv.org/abs/...`) **and** ACL Anthology (`2021.acl-long.285`, `P19-1001`, `https://aclanthology.org/<id>/`, or the `.pdf` / `.xml` / `.bib` asset URL). ACL papers ingest from MODS metadata + PDF body (no HTML/LaTeX fulltext exists), so no PwC repo discovery; otherwise same shape as arxiv. If the paper ships a code repo URL (arxiv path only), the linked repo is registered and cloned as a follow-up — do not call `ingest_repo` separately for it. Pass `force=true` to wipe and re-ingest. Optional `domain="..."` (display name or slug — e.g. `domain="Conversation Understanding"`) pins the classifier to that domain.
- Standalone github/gitlab/bitbucket URL (no associated paper) → `mcp__lodestone__ingest_repo(url=<repo_url>)`. Optional `force`, `domain`.
- Blog post URL (e.g. `https://lilianweng.github.io/posts/...`) → `mcp__lodestone__ingest_post(url=<post_url>)`. Runs fetch → trafilatura HTML→markdown → classify → extract → index. Optional `force`, `domain`.

All three tools are resumable and emit MCP progress notifications between stages.

**Set expectations *before* kicking off the ingest call.** In the same turn that issues the tool call, prefix it with a short message to the user along the lines of:

> Ingest is running. This typically takes **5–10 minutes** on a typical machine — the bulk is **GLiNER2 entity extraction** over each section on CPU (this scales with the number of sections — a 60-section paper can be a few minutes alone), plus **entity/topic embedding and 5-tier resolution** against the existing taxonomy. The classify-stage LLM call is the only network roundtrip and is usually the smallest contributor. Progress notifications stream between stages.

Phrase it in your own voice, but include the key facts: 5–10 min typical, GLiNER2 + entity/topic embedding + resolution are the dominant costs, progress streams between stages.

Then call the ingest tool and **wait for it to return**. A 5–10 minute tool call is expected and normal — do not interpret the duration as a hang, do not claim a client-side timeout, and do not retry mid-flight. The MCP client keeps the call alive via the streamed progress notifications; the result envelope arrives when ingestion is done. Proceed once it returns.

## Fulfill a task or ground a plan

The user needs a task fulfilled that would benefit from research or a plan would benefit from research. There are two ways to kick off research on lodestone, top-down and bottom-up:

### Top-down Research

If you aren't sure what keywords to pass, or want a more complete perspective of the entire knowledge base, Lodestone maintains a taxonomy of domains and collections that sort papers/repos/posts into different categories. To research from a "top-down" perspective, start by returning this taxonomy to get a feel for what areas you can drill deeper into.

- `mcp__lodestone__overview()` — full nested domains → collections tree. Each domain and each collection carries per-kind counts: `paper_count`, `post_count`, `repo_count`. Pass `domain=<slug>` to restrict to one domain.

From here, you can use selected domains or collections to narrow your results, for e.g. you might:

#### Return abstracts from a given collection
  - `mcp__lodestone__collection(collection=<name>)` — drills into one or more collections and returns three parallel arrays per entry: `papers[]` (with `abstract` + `topics` + `has_repo` / `repo_slug` stamps), `posts[]` (slim shape: title, slug, author, site_name, date, section_count, abstract, topics), and `repos[]` (**standalone repos only** — paper-linked repos surface inside their owning paper via `has_repo`). Each entry also carries `paper_count` / `post_count` / `repo_count` totals (the `repo_count` total *does* include paper-linked repos, even though they don't appear in `repos[]`) plus matching `_truncated` flags. Pass an array of up to 16 names to bundle. `domain` disambiguates collections that exist under multiple domains. `include_abstracts=false` / `include_topics=false` slim the response — and when calling with >1 collection, `include_abstracts` defaults to `false` automatically (response carries `auto_trimmed: true`); pass `include_abstracts=true` to override. `limit` caps papers/posts/repos per collection independently (default 20, max 100).

#### Return topics in a given collection
  - `mcp__lodestone__browse(which='topics', collection=<name>, domain=<slug>?)` — aggregated topic rollup scoped to one collection. Topics for papers, posts, and standalone+paper-linked repos all join through the polymorphic `collections(target_kind, target_id, domain, collection, is_primary)` junction (so secondary memberships count for every kind). Each row carries `count`, `paper_count`, `post_count`, and `repo_count`. Pass `domain` to disambiguate collection names that exist under multiple domains.
  - For per-source topic arrays instead of a deduplicated rollup, use `mcp__lodestone__collection(collection=<name>, include_topics=true, include_abstracts=false)` — topics ride along on each paper/post/repo entry.
  
#### Issue github-query-flavored keyword searches over paper/post chunks or repo READMEs filtered to a domain
  - `mcp__lodestone__bm25(query=<q>, scope="sections"|"readmes"|"both", domain=<slug>, collection=<name>?, limit=15, offset=0, recency_boost=0.2, since=<YYYY|YYYY-MM-DD>?)`. The `sections` surface is polymorphic — paper sections and post sections share one FTS5 table, keyed by a globally-unique slug; the `readmes` surface covers every ingested repo (paper-linked and standalone). Query syntax: bare-token AND, `"phrase"`, uppercase `OR`/`NOT`, parens, `term*` prefix, `paper:NAME`, `domain:NAME`, `collection:NAME`, `surface:sections|readmes|both`. **AND→OR fallback:** if the query is bare tokens (no explicit `AND`/`OR`/`NOT`) and the AND-joined form returns zero rows, `bm25` retries as OR and tags the response with `fallback: "OR"`. User-typed operators are respected as-is. **Temporal knobs:** `recency_boost` (0.0–1.0, default 0.2) applies a soft multiplicative tilt toward recent papers; `since` is a hard floor on `papers.date`. Both are no-ops on README hits (repos have no publication date). Returns hits grouped by source slug with topics, entity preview, figure counts; `(figure:N)` refs inside snippets are auto-attached as inline images.

As lodestone fills with more and more data, top-down is the preferred method of exploration. 

### Coverage / negative-evidence queries

When you need to claim "lodestone has (no / weak / strong) coverage of X" use `mcp__lodestone__coverage(topic=<str>, domain=<slug>?)`. One call returns: `papers_matched` + top 5 (FTS over sections), `repos_matched` + top 5 (FTS over READMEs), `collections_exact` (case-insensitive equality), and `collections_nearest` / `entities_nearest` / `topics_nearest` / `aliases_nearest` (rapidfuzz ≥70, bucketed by `term_type`). No heuristic `"high|medium|low"` label — the structured counts + similarity scores are the citation-grade signal. Run this as the backstop before asserting a gap.

### Bottom-up Research

If the query patterns are obvious from context, Lodestone offers github-query-flavored, keyword-based, exploratory search. This "bottom-up" approach gives you a feel for how your keywords land across the whole database.

- **Default first move:** `mcp__lodestone__search(query=<q_or_array>, domain=<slug>?, limit=5, union=false, recency_boost=0.2, since=<YYYY|YYYY-MM-DD>?)` — returns three buckets in one call: taxonomy (canonical entity/topic/collection hits, each tagged with `kind`), sections (BM25 over a polymorphic FTS5 table holding paper section text *and* blog-post section text — both surface together, keyed by a globally-unique slug), readmes (BM25 over READMEs for every ingested repo, paper-linked and standalone alike — paper-linked rows additionally carry `paper_name` so you can pivot back to the prose). No images — kept cheap for orientation. Inherits the same AND→OR fallback and `recency_boost`/`since` knobs as `bm25` (no-op on README/taxonomy buckets).
- Multi-query fan-out: pass `query=["chain of thought", "tree of thoughts", "self-consistency"]` (up to 8 strings); each is parsed and executed independently. Default returns per-query H2 sections; pass `union=true` to RRF-merge into one ranked list where each hit carries `matched_queries: [i, j, ...]` (use when you want "any doc matching any of these N concepts"). `limit` is shared across the fan-out — keep it small.
- Same syntax as `bm25` plus: `surface:sections|readmes|taxonomy` (omit for all three), `kind:entity|topic|collection` (narrow taxonomy bucket).
- **Note:** `search` accepts `limit` but **not** `offset`. For deep paging into one bucket, switch to `bm25` (sections/readmes) or `lookup` (taxonomy).

Fallbacks once `search` has oriented you:

- `mcp__lodestone__bm25(query=<q>, scope="sections"|"readmes"|"both", ...)` — when you need `offset` to page deeper into one surface. Same query syntax as `search`.
- `mcp__lodestone__lookup(term=<q>, kind="entity"|"topic"|"collection", domain=<slug>?, limit=50, offset=0)` — taxonomy-only resolution of a known surface form. Returns canonical metadata, aliases, and the papers that mention it. FTS5-only, no semantic fallback — use `search` for a wider sweep.

### After exploratory queries

Once exploration has surfaced candidate papers or posts, work down this ladder — each rung is meaningfully more expensive than the one above it. The `slug` argument on `toc`, `toc_many`, and `read` is polymorphic — papers and posts share one slug namespace, so any of these tools resolve a paper or post slug transparently.

1. **Default: `toc` → `read(section=...)`.** Pull the table of contents first, then read only the relevant slice. This is the right move for nearly every "tell me what source X says about Y" follow-up.
2. **Comparing across sources: `toc_many`.** Use when you're triaging several candidates (papers and/or posts) and need to see their structures side by side before picking a slice.
3. **Reading a paper: `read(slug=<slug>)` with no `section`.** Reads the full markdown body and can be expensive — do this when a section slice genuinely won't suffice (e.g. you've already identified the source as load-bearing and need the whole thing).

The tools:

- `mcp__lodestone__toc(slug=<slug>)` — level-1..3 ATX header tree for one source (paper or post). Response carries `slug` and `toc[]`.
- `mcp__lodestone__toc_many(slugs=[<slug1>, <slug2>, ...])` — same shape, batched, mix of paper and post slugs allowed. Slugs that don't resolve are reported in `missing` instead of raising — a typo in one doesn't abandon the rest. Response carries `slugs`, `results[]` (each with `slug` + `toc[]`), `missing[]`.
- `mcp__lodestone__read(slug=<slug>, section="<title>")` — `section` is a hierarchical `Parent > Child` breadcrumb (e.g. `"Method"`, `"Method > Setup"`, `"Experiments > Setup"`). Suffix-match, case-insensitive, on the title path. Any `(figure:N)` refs in the slice are auto-attached as inline images.
- `mcp__lodestone__read(slug=<slug>)` — omit `section` to get the full markdown body. Expensive — prefer a section slice when possible.

### Citations

**Citation graph.** Reach the graph via `mcp__lodestone__citations(slug=<slug>, direction=<outbound|inbound>)` — it bakes the polymorphism (papers + posts) and the resolved/missing/unresolvable split in for you. Drop to `query` only when you need a traversal the tool doesn't expose. Useful calls:
- **Outbound — "what does paper / post X lean on?"** `mcp__lodestone__citations(slug=<slug>)` (direction defaults to `outbound`). Returns three buckets: `resolved`, cited sources already in Lodestone, `missing`, cited arxiv ids we don't have, each with an `ingest_hint` carrying the exact `ingest_paper` call, and `unresolvable` (no arxiv id at all). Capped at 500 rows with `truncated=true` if exceeded.
- **Inbound — "who cites paper X?"** `mcp__lodestone__citations(slug=<paper_slug>, direction="inbound")` unions papers and posts that cite the target, ordered by date DESC. Paper-only.

### Code repos

Most of the time, code repos are expected to validate what you learn during paper research. Once you've built up evidenced theories from paper research, its generally a good idea to validate their implementation in associated code repos.

However, lodestone can ingest code repos on their own (no paper) so code repos should also be thought of as a research dimension independent of papers/posts.

Navigating code repos has basically two paths:

#### Diving deeper on a known code repo:

If you already know what code repo you want to look at, you can return the entire path/filename tree for a given repo then pick which files you want to read in:

- `mcp__lodestone__repo(repo=<repo_slug>)` — one-shot metadata + topics + linked paper (if any). Cheap "tell me about this repo" step.
- `mcp__lodestone__repo_tree(paper_name=<name>)` **or** `mcp__lodestone__repo_tree(repo=<repo_slug>)` — every code-file path. Identify by exactly one of the two. Soft statuses for missing data: `no_repo`, `failed_repo`.
- `mcp__lodestone__read_code(path=<file_path>, paper_name=<name>?, repo=<repo_slug>?, lines="A-B"?)` — read one file, optionally sliced by inclusive 1-based line range (e.g. `lines="100-200"`). Identify the repo by exactly one of `paper_name` or `repo`.

#### Exploring ingested code repos

If you are exploring code repos, the only place to explore is issuing github-query-flavored FTS searches over repo README's (this is the only FTS dimension for repos).

- `mcp__lodestone__bm25(query=<q>, scope="readmes", domain=<slug>?, limit=15, offset=0)` — README-only BM25. Same query syntax as the sections variant.
- Or `mcp__lodestone__search(query=<q>)` and read the `readmes` bucket of the response (alongside `taxonomy` and `sections`).

## Controlling results

You are a mechanism for agentic search over the lodestone database. Every token you spend costs money, so you want to use the top-down/bottom-up approaches provided to narrow to the right places to read in slices of papers or full papers. Queries can be passed limit and offset parameters to reduce result size and page through results

- `bm25` and `lookup` both accept `limit` (default 15 / 50 respectively) and `offset` (default 0). The response carries `total_hits` and `has_more`; raise `offset` by `limit` to walk forward. For `bm25` `scope=both`, each surface paginates independently with the same offset/limit and `total_hits` sums across surfaces.
- `search` accepts `limit` (default 5, max 20) but **not** `offset` — for deep paging, drop down to `bm25` / `lookup`.
- `collection` accepts `limit` (default 20, max 100) — papers per collection.
- `query` (SQL) is hard-capped at 1000 rows per call; paginate inside your SQL with `LIMIT N OFFSET M` plus a stable `ORDER BY`.

## None of the above fits my need

In the event none of the above fits your need you can:
- Return all lodestone tables: `mcp__lodestone__tables(include_internal=false)` — lists every user table / view / virtual table; FTS5/vec0 shadow tables are filtered out unless `include_internal=true`.
- Return the schema for a given table or multiple tables: `mcp__lodestone__schema(tables=<name_or_array>)` — CREATE DDL + columns + indexes. Names that don't resolve land in `missing`.
- Execute read-only queries directly on the DB: `mcp__lodestone__query(sql=<single_select>)`. Engine-enforced read-only (mode=ro URI); DML/DDL returns `read_only_violation`. Exactly one statement per call. 1000-row hard cap (`truncated=true` on overflow). 5s wall-clock timeout. BLOB columns are summarized as `{_blob: true, size_bytes: N}` — fetch real binary content via `figure` or `read_code`.

If lodestone doesn't have it, say so — don't paper over the gap with training-data recall. Note that lodestone doesn't have it and return anything nearby the request if you have it. Before asserting a gap, run `coverage(topic=…)` so the negative claim is defensible.

## Novelty
If the /deep-sota skill has been invoked then almost certainly the user desires their task to be grounded in their lodestone database of research papers and code repos. However, use of Lodestone should include looking for novelty at the edges of the users request. Seek to include novelty you find in your responses. By novelty, we mean ideas that are related to what you're researching that the user likely doesnt know about or doesn't remember.


