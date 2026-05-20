![deep-sota hero](assets/hero.jpeg)

# /deep-sota, a Claude Code plugin

![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Status](https://img.shields.io/badge/status-beta-orange)
![License](https://img.shields.io/badge/license-Apache--2.0-green)
![Claude Code](https://img.shields.io/badge/Claude%20Code-Plugin-purple)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)

> **Blog post:**
> - [Lodestone: A SQLite-backed arXiv research paper retrieval system for Claude Code](https://medium.com/@pierce-lamb/lodestone-a-sqlite-backed-arxiv-research-paper-retrieval-system-for-claude-code-b77de201f0c8)

`/deep-sota` (*deep state of the art*) is the dedicated front-end for [`lodestone`](https://github.com/piercelamb/lodestone) — **and only for lodestone**. It is not a standalone plugin. It ships a single skill whose entire purpose is to drive lodestone's 21 MCP tools (coverage checks, top-down taxonomy walks, bottom-up BM25 searches, section reads, citation traversal, inline figures, and code-repo reads) to ground your task in your own research corpus instead of letting Claude hallucinate. **Without the `lodestone` Claude Code plugin installed and enabled, `/deep-sota` has nothing to drive and will not work.** Install `lodestone` first, every time.

Where [`/deep-plan`](https://github.com/piercelamb/deep-plan) is built for *planning* software and [`/deep-implement`](https://github.com/piercelamb/deep-implement) for *building* it, `/deep-sota` is built for *grounding* it: real citations, real figures, real training code, and an honest "lodestone doesn't have X" when it doesn't.

> **`lodestone` is a hard requirement, not a recommendation.** `/deep-sota` does not ship its own corpus, MCP server, or any of the tools it invokes — those all live in [`lodestone`](https://github.com/piercelamb/lodestone). Every install / TL;DR / quick-start block in this README installs `lodestone` first and `/deep-sota` second. If you only install `/deep-sota`, the skill loads but every tool call fails.

## TL;DR

Requires [`uv`](https://docs.astral.sh/uv/) on `PATH`.

Install `lodestone` *first*, then `/deep-sota`, then run `/lodestone:doctor` *before* you restart so the venv is populated by the time Claude Code launches the MCP server:
```
/plugin marketplace add piercelamb/lodestone
/plugin install lodestone
/plugin install deep-sota
/reload-plugins
/lodestone:doctor # picks LLM provider/model + downloads HF models (~400 MB) — give it a few minutes
/mcp -> find lodestone -> enable or reconnect
```
Then **fully quit and relaunch Claude Code** (not `/reload-plugins`) — once. Done.

**Optional — pre-seed the taxonomy** (domains and collections) before your first ingest. Either use [my taxonomy](./taxonomy.json) or write your own in the same shape, then point Claude at [`seed_taxonomy.py`](./_system/scripts/seed_taxonomy.py). Skip seeding entirely and the classify step grows the taxonomy from scratch as you ingest — both paths are fully supported. See [Seeding the Taxonomy](#seeding-the-taxonomy).

Now seed your corpus — `/deep-sota` accepts arXiv, code repo, and blog post URLs:

```
/deep-sota https://arxiv.org/abs/2305.10601                       # arXiv paper
/deep-sota https://github.com/owner/repo                          # code repo
/deep-sota https://lilianweng.github.io/posts/2023-06-23-agent/   # blog post
```

Once the corpus has a few papers, ask research questions:
```
/deep-sota "long-context retrieval"
/deep-sota "what's the SOTA on agentic web search?"
/deep-sota "what's the SOTA on RAG with KV-cache offloading?"
```

`/lodestone:doctor` is the **required** first-run setup: it runs the one-time `uv sync` (~30–90s) and pre-seeds the venv, walks you through the LLM provider + model picker (writing `~/.config/lodestone/config.toml`), and downloads the two CPU-only HuggingFace models (`bge-small-en-v1.5` embeddings + `gliner2-large-v1` entity extraction, ~400 MB total) in the background while you answer the picker prompts. On the next launch Claude Code finds the venv ready on its first MCP-server attempt, config in place, and models cached — `mcp__lodestone__*` tools register immediately and your first `/deep-sota` ingest can start straight away. If you skip doctor and try to ingest, `/deep-sota` reads `~/.config/lodestone/config.toml`, sees it's missing, and tells you to run `/lodestone:doctor` first — the skill does not do its own picker fallback.

> **Why doctor *before* restart?** Claude Code launches MCP servers in parallel with `SessionStart` prewarm hooks and won't retry one that fails mid-session. If you skip the doctor and just restart, the lodestone MCP server attempts to launch against an empty venv, exits 1, and stays unavailable until you restart *a second time*. Doctor-first preempts the race.

## Table of Contents

- [Overview](#overview)
- [The Plugin Family](#the-plugin-family)
- [Why deep-sota?](#why-deep-sota)
- [When to Use](#when-to-use)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [The Three Invocations](#the-three-invocations)
- [Tools It Reaches For](#tools-it-reaches-for)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [Requirements](#requirements)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)
- [Contributing](#contributing)

## Overview

**deep-sota** is a research orchestration skill. It treats lodestone as a queryable corpus and Claude as the agentic search loop, with prescribed patterns for the three things you actually want from a personal research index:

```
Coverage Check → Top-Down (taxonomy) ↘
                                      → Read Sections → Follow Citations → View Figures → Read Code
                Bottom-Up (BM25) ↗
```

The skill encodes:
- **When to walk the taxonomy** (top-down — you don't know the keywords yet, or you want a complete view of a domain)
- **When to BM25-search** (bottom-up — query patterns are obvious from context)
- **When to run `coverage`** (before claiming lodestone has nothing on X, so the gap is defensible instead of guessed)
- **How to ladder up the read tools** (`toc` → `read(section=...)` → `read` full body, each rung meaningfully more expensive than the last)
- **How to follow citations** (forward: "what does this lean on?", backward: "who cites this?")
- **How to validate against training code** (`repo_tree` → `read_code` from a paper's linked repo)
- **How to surface novelty** at the edges of your question, not just answer what you literally asked

It also handles ingestion: arXiv / GitHub / blog URL goes in, the full lodestone pipeline (fetch → convert → classify → index → resolve citations → fetch repo) runs out.

## The Plugin Family

`/deep-sota` and [`lodestone`](https://github.com/piercelamb/lodestone) ship from the same `piercelamb-plugins` marketplace as the [Deep Trilogy](https://github.com/piercelamb/deep-plan). The research half pairs as cleanly as the build half:

```
┌───────────────────────────────────────────────────────────────────┐
│                     THE PIERCELAMB PLUGINS                        │
├───────────────────────────────────────────────────────────────────┤
│                                                                   │
│   Research half:                  Build half:                     │
│                                                                   │
│   ┌──────────────┐                ┌──────────────┐                │
│   │  lodestone   │                │ /deep-project│                │
│   │  (corpus +   │                │  (decompose) │                │
│   │   MCP tools) │                └──────┬───────┘                │
│   └──────┬───────┘                       ▼                        │
│          │                        ┌──────────────┐                │
│          ▼                        │  /deep-plan  │                │
│   ┌──────────────┐                │    (plan)    │                │
│   │  /deep-sota  │ ◀── YOU ARE HERE └──────┬───────┘              │
│   │ (orchestrate │                       ▼                        │
│   │   research)  │                ┌──────────────┐                │
│   └──────────────┘                │/deep-implement│                │
│                                   │   (build)    │                │
│                                   └──────────────┘                │
│                                                                   │
│   "what's the SOTA on X?"         "build me a SaaS platform"      │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

| Plugin | Purpose | Pairs with |
|--------|---------|------------|
| [`lodestone`](https://github.com/piercelamb/lodestone) | Build & query a personal research corpus (arXiv, blogs, repos) | `/deep-sota`, any MCP client |
| [`/deep-sota`](https://github.com/piercelamb/deep-sota) | Orchestrate paper- and repo-grounded research over lodestone | `lodestone` |
| [`/deep-project`](https://github.com/piercelamb/deep-project) | Decompose vague requirements into focused spec files | `/deep-plan` |
| [`/deep-plan`](https://github.com/piercelamb/deep-plan) | AI-assisted deep planning with research, review, and TDD | `/deep-implement` |
| [`/deep-implement`](https://github.com/piercelamb/deep-implement) | Implement section files with TDD and integrated code review | — |

**Pairings that cross the half-line:**
- Use `/deep-sota` *inside* `/deep-plan` runs when a feature needs research grounding — feed lodestone-cited claims into the spec before the external LLM review step.
- Use `/deep-sota` *before* `/deep-project` decomposition when the project is in a domain you haven't surveyed yet, so the splits are informed by SOTA instead of vibes.

## Why deep-sota?

### Without deep-sota
```
You: "What's the state of the art on long-context retrieval?"
Claude: *web searches, hallucinates citations, can't see figures or code*
Result: Surface-level answers, broken arxiv links, confident wrong claims
```

### With deep-sota
```
You: /deep-sota https://arxiv.org/abs/2305.10601   # ingest first
You: /deep-sota "long-context retrieval"           # then research
deep-sota: coverage check → taxonomy / BM25 → read sections →
           follow citations → view figures → read training code
Result: Grounded answers with section-level citations, inline figures, real
        code excerpts — and an honest "lodestone doesn't have X" when it doesn't.
```

**One-time cost**: a few minutes per ingest (LaTeXML conversion, classification, embedding).
**Payoff**: every future query against those papers grounds in *your* corpus, no API calls.

`/deep-sota` will **not** silently fetch papers behind your back on a research question. Ingest is explicit — when the corpus lacks coverage, the skill surfaces the gap and (for arXiv-id citations) hands you exact `ingest_paper` calls to run.

## When to Use

**Use deep-sota when:**
- You want Claude to ground answers in specific papers, not generic web search
- You're starting a greenfield project in a domain with active research
- You want figure-level grounding (the assistant *sees* the architecture diagram, not just the caption)
- You want cross-paper citation following without third-party APIs
- You're about to run `/deep-plan` or `/deep-project` and the spec is research-heavy

**Skip deep-sota when:**
- The question is about the codebase you're sitting in (use Claude's normal file/grep tools)
- You're doing a bug fix or one-file change with no research dimension
- The corpus is empty or doesn't cover your domain — ingest first, then ask
- One-off factual questions that web search handles fine

## Quick Start

> **TL;DR**: Install `lodestone` *first*, then `/deep-sota`, restart, (optionally) seed the taxonomy, ingest at least one paper, then ask `/deep-sota` a research question. An empty corpus can't answer anything.

**1. Install both plugins — lodestone first, doctor before restart:**
```
/plugin marketplace add piercelamb/lodestone
/plugin install lodestone
/plugin install deep-sota
/reload-plugins
/lodestone:doctor
```

Then **fully quit and relaunch Claude Code** (not `/reload-plugins`).

> The marketplace add line uses `piercelamb/lodestone` — all five `piercelamb-plugins` (the Deep Trilogy, lodestone, and deep-sota) ship from the same marketplace listing, but pulling it via the lodestone repo makes the install order self-documenting: install the thing `/deep-sota` requires *before* `/deep-sota`.

What each step does:

| Step | Purpose |
|---|---|
| `/reload-plugins` | Makes the new slash commands (incl. `/lodestone:doctor`) available in the current session. |
| `/lodestone:doctor` | Runs the one-time `uv sync` (~30–90s) and pre-seeds the venv. Idempotent — doubles as a diagnostic. |
| Full quit + relaunch | Registers the lodestone MCP server against the now-populated venv. |

> **Why doctor *before* restart?** Claude Code launches MCP servers in parallel with `SessionStart` prewarm hooks and won't retry one that fails mid-session — so if you skip the doctor and just restart, lodestone's MCP server attempts to launch against an empty venv, exits 1, and stays unavailable until you restart *a second time*. Doctor-first preempts the race. (Optional: run `/plugins` after the restart if you need the UI to enable/disable individual plugins.)

The two CPU-only HuggingFace models (`bge-small-en-v1.5` embeddings + `gliner2-large-v1` entity extraction, ~400 MB total) are already cached because `/lodestone:doctor` downloaded them as part of the required first-run setup. If `mcp__lodestone__*` tools still don't appear after the restart, re-run **`/lodestone:doctor`** — it diagnoses `uv` presence, venv state, MCP registration, DB writability, HF model cache, and LLM provider config in one shot, and auto-remediates the venv / model / config gaps where it can.

**2. Make sure a classifier provider API key is exported:**

`/lodestone:doctor` reads `$ANTHROPIC_API_KEY` / `$OPENAI_API_KEY` / `$GEMINI_API_KEY` from your shell to know which providers it can offer in the picker. Set at least one before running doctor:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# and/or:
export OPENAI_API_KEY="sk-..."
# and/or:
export GEMINI_API_KEY="..."
```

With at least one key exported, run `/lodestone:doctor` (if you haven't already) — it writes your provider/model choice to `~/.config/lodestone/config.toml`. The skill reads that file directly on ingest; if it's missing, the skill stops and tells you to run `/lodestone:doctor`. The classifier is the only LLM call in the lodestone pipeline — input is capped (~8k of paper prose, ~10k chars of blog or README), so per-ingest token cost is small and predictable.

**3. Ingest something:**
```
/deep-sota https://arxiv.org/abs/2305.10601
```

**4. Ask a question:**
```
/deep-sota "long-context retrieval"
```

That's it. The skill picks the right tools, orders them sensibly, and tells you honestly when the corpus doesn't have something instead of papering over the gap.

> **Seed the taxonomy first (recommended).** Lodestone's classifier works fine against an empty taxonomy — it mints new domains and collections as it goes — but seeding from the shipped `taxonomy.json` gives the first dozen ingests a stable scaffold. See [Seeding the Taxonomy](https://github.com/piercelamb/lodestone#seeding-the-taxonomy) in the lodestone README.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                       deep-sota workflow                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   /deep-sota <url-or-question>                                  │
│          │                                                      │
│          ▼                                                      │
│   ┌──────────────┐                                              │
│   │   Classify   │  URL → ingest path                           │
│   │   Intent     │  Question → research path                    │
│   └──────┬───────┘                                              │
│          │                                                      │
│   ┌──────┴───────────────────────────────────────────────────┐  │
│   │                                                          │  │
│   ▼ INGEST                                  RESEARCH ▼       │  │
│   ┌──────────────┐                          ┌──────────────┐ │  │
│   │  Read TOML   │                          │  Coverage    │ │  │
│   │  config      │                          │  (negative-  │ │  │
│   │  (stop if    │                          │  evidence    │ │  │
│   │   missing)   │                          │  backstop)   │ │  │
│   └──────┬───────┘                          └──────┬───────┘ │  │
│          ▼                                         ▼         │  │
│   ┌──────────────┐                          ┌──────────────┐ │  │
│   │ ingest_paper │                          │  Top-down    │ │  │
│   │ ingest_post  │                          │  (overview / │ │  │
│   │ ingest_repo  │                          │  collection /│ │  │
│   └──────┬───────┘                          │  browse) +   │ │  │
│          ▼                                  │  Bottom-up   │ │  │
│   ┌──────────────┐                          │  (search /   │ │  │
│   │  Lodestone   │                          │  bm25 /      │ │  │
│   │  pipeline:   │                          │  lookup)     │ │  │
│   │  fetch →     │                          └──────┬───────┘ │  │
│   │  convert →   │                                 ▼         │  │
│   │  classify →  │                          ┌──────────────┐ │  │
│   │  index →     │                          │  toc →       │ │  │
│   │  cite-graph →│                          │  read(slice) │ │  │
│   │  fetch-repo  │                          │  → citations │ │  │
│   └──────────────┘                          │  → figures   │ │  │
│                                             │  → read_code │ │  │
│                                             └──────┬───────┘ │  │
│                                                    ▼         │  │
│                                             ┌──────────────┐ │  │
│                                             │  Answer +    │ │  │
│                                             │  novelty at  │ │  │
│                                             │  the edges   │ │  │
│                                             └──────────────┘ │  │
│                                                              │  │
│   └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## The Three Invocations

`/deep-sota` is invoked for exactly one of three reasons. The skill detects which from the argument shape and runs a different protocol for each.

### 1. Ingest — URL → corpus

Pass a URL and the skill routes to the right ingestion tool:

```
/deep-sota https://arxiv.org/abs/2305.10601               # arXiv paper
/deep-sota https://github.com/owner/repo                  # standalone repo
/deep-sota https://lilianweng.github.io/posts/...         # blog post
```

| Source | Tool | Notes |
|--------|------|-------|
| arXiv URL or bare ID | `ingest_paper` | If the paper ships a code repo, it's discovered (PapersWithCode → abstract scrape) and cloned automatically. |
| GitHub / GitLab / Bitbucket | `ingest_repo` | Standalone repos with no paper anchor. |
| Blog post URL | `ingest_post` | HTML → trafilatura → markdown. Same `collections` table as papers. |

All three are resumable and emit MCP progress notifications. Before kicking off any ingest, the skill reads `~/.config/lodestone/config.toml` and confirms `[llm].provider` and `[llm].model` are both set. If either is missing, the skill stops and tells the user to run `/lodestone:doctor` — it does not pick a provider or write config from inside the skill. Doctor is the single owner of that flow.

### 2. Research a question

Pass a natural-language query and the skill runs a coverage-first research loop over the existing corpus:

```
/deep-sota "long-context retrieval"
/deep-sota "what's the SOTA on agentic web search?"
/deep-sota "compare RAG architectures with KV-cache offloading"
```

The skill picks between top-down and bottom-up based on what it can infer:

- **Top-down** (`overview` → `collection` / `browse`) — when keywords aren't obvious, or when you want a complete view of a domain before drilling in. Walks the taxonomy of domains and collections.
- **Bottom-up** (`search` → `bm25` / `lookup`) — when query patterns are obvious from context. GitHub-style query syntax (AND/OR/NOT, `"phrase"`, `term*`, `paper:` / `domain:` / `collection:` / `surface:` qualifiers).
- **Coverage backstop** (`coverage`) — before asserting "lodestone has nothing on X." Combines FTS hits, exact taxonomy matches, and rapidfuzz nearest-neighbors with similarity scores. The structured signal makes the negative claim defensible instead of guessed.

Once exploration surfaces candidates, the read ladder:

1. **`toc` → `read(section=...)`** — pull the table of contents, then read only the relevant slice. The right move for nearly every "tell me what source X says about Y" follow-up.
2. **`toc_many`** — batched TOCs when triaging several candidates side by side.
3. **`read(slug=<slug>)`** without `section` — full body. Expensive; do this when a section slice genuinely won't suffice.

When relevant, the skill also pulls inline figures (`figure`), follows citations forward and backward (`citations`), and validates implementation claims against the paper's training code (`repo_tree` → `read_code`).

### 3. Ground an implementation plan

Same query shape as a research question, different intent. Use before `/deep-plan` for research-heavy specs, or before `/deep-project` when the project is in a domain you haven't surveyed yet:

```
/deep-sota "what's the SOTA on RAG with KV-cache offloading?"
/deep-sota "compare agentic web search architectures"
```

The skill grounds the planning conversation in real papers and real code, so the spec that `/deep-plan` receives already cites SOTA and avoids approaches the literature has moved past.

## Tools It Reaches For

All 21 lodestone MCP tools are available to `/deep-sota`. The skill knows when each fits — you don't need to memorize the surface area. For reference:

| Bucket | Tools | When |
|--------|-------|------|
| **Discovery** | `search`, `bm25`, `lookup`, `coverage`, `browse`, `overview`, `collection` | Locating papers, claiming coverage, walking the taxonomy |
| **Read** | `toc`, `toc_many`, `read`, `figure`, `citations` | Pulling section text, viewing architecture diagrams, following the cite graph |
| **Code** | `repo_tree`, `read_code`, `repo` | Validating paper claims against the linked training code |
| **Escape hatches** | `tables`, `schema`, `query` | Read-only SQL when the curated tools don't fit |
| **Ingest** | `ingest_paper`, `ingest_post`, `ingest_repo` | URL → corpus |

See [lodestone's MCP Tools section](https://github.com/piercelamb/lodestone#mcp-tools) for the full signatures.

## Installation

### Prerequisites

- [Claude Code](https://claude.ai/code) installed
- [`lodestone`](https://github.com/piercelamb/lodestone) — `/deep-sota` is the front-end, lodestone is the corpus + MCP server
- [uv](https://docs.astral.sh/uv/) on `PATH` (for lodestone)
- Python 3.11+
- An LLM API key for the lodestone classifier — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, or `GEMINI_API_KEY` (any one works)

### Install via Marketplace (Recommended)

> **Order matters.** `lodestone` carries the MCP server and tools `/deep-sota` invokes — install it *first*, then `/deep-sota`. The commands below already do this; don't reorder them.

**Canonical sequence — install, reload, doctor, then one restart:**
```
/plugin marketplace add piercelamb/lodestone
/plugin install lodestone
/plugin install deep-sota
/reload-plugins
/lodestone:doctor
```

Then **fully quit and relaunch Claude Code** (not `/reload-plugins`).

What each step does:

| Step | Purpose |
|---|---|
| `/plugin marketplace add piercelamb/lodestone` | Adds the `piercelamb-plugins` marketplace. Skip if you already have it from `/deep-project`, `/deep-plan`, or `/deep-implement`. |
| `/plugin install lodestone` + `/plugin install deep-sota` | Installs both. Lodestone first; `/deep-sota` depends on its MCP tools. |
| `/reload-plugins` | Makes the new slash commands available in the current session (without it, `/lodestone:doctor` won't resolve yet). |
| `/lodestone:doctor` | The required first-run setup: runs lodestone's `uv sync` (~30–90s) to seed the venv, walks you through the LLM provider + model picker (writes `~/.config/lodestone/config.toml`), and downloads the two HuggingFace models (~400 MB total) in the background while you answer the picker. Idempotent — also doubles as a diagnostic on later runs. |
| Full quit + relaunch | Registers `mcp__lodestone__*` against the now-populated venv. |

> **Why doctor *before* restart?** Claude Code launches MCP servers in parallel with `SessionStart` prewarm hooks and won't retry one that fails mid-session ([per its hook docs](https://code.claude.com/docs/en/hooks)). If you skip the doctor and just restart, the lodestone MCP server attempts to launch against an empty venv, exits 1, and stays unavailable until you restart *a second time*. Doctor-first preempts the race.

> **Already installed `/deep-project`, `/deep-plan`, or `/deep-implement`?** All five plugins share the `piercelamb-plugins` marketplace. Skip the `marketplace add` step — but still run the rest of the sequence in order.

> **Prefer the UI for enable/disable?** Run `/plugins` after the restart to scroll to "Installed" and manage each plugin individually.

The two HuggingFace models (`bge-small-en-v1.5` + `fastino/gliner2-large-v1`, ~400 MB total) are downloaded upfront by `/lodestone:doctor` as part of the required sequence above. If `mcp__lodestone__*` tools still don't appear after the restart, re-run **`/lodestone:doctor`** — it diagnoses `uv` presence, venv state, MCP registration, DB writability, HF model cache, and LLM provider config in one shot.

### Manual Installation

**Option A: Via settings.json**

Clone **lodestone first**, then `/deep-sota`, and list lodestone first in the plugin paths so it loads before `/deep-sota` looks for its tools:
```bash
git clone https://github.com/piercelamb/lodestone.git /path/to/lodestone
git clone https://github.com/piercelamb/deep-sota.git /path/to/deep-sota
```

```json
{
  "plugins": {
    "paths": ["/path/to/lodestone", "/path/to/deep-sota"]
  }
}
```

**Option B: Via --plugin-dir flag (development/testing)**

```bash
claude --plugin-dir /path/to/lodestone --plugin-dir /path/to/deep-sota
```

Same rule: pass `--plugin-dir` for `lodestone` before `deep-sota` so the MCP server registers first.

### Configure the classifier (required for ingest)

Set at least one LLM API key in your shell. `/lodestone:doctor` reads these to know which providers it can offer in the picker:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
# and/or:
export OPENAI_API_KEY="sk-..."
# and/or:
export GEMINI_API_KEY="..."
```

Then run `/lodestone:doctor` — it walks you through provider + model selection and writes `~/.config/lodestone/config.toml`. `/deep-sota` reads that file directly before each ingest; if it's missing, the skill stops and tells you to run `/lodestone:doctor`. The skill itself does **not** pick a provider, prompt for a model, or write config — that's all owned by doctor.

## Usage

### Basic Invocation

```
/deep-sota <url-or-question>
```

The skill classifies your argument as a URL (ingest path) or natural language (research path). Quoting natural-language questions is helpful but not required.

### Skipping deep-sota on codebase questions

If your question is about the codebase you're sitting in (its files, its bugs, its tests, its history), don't reach for `/deep-sota`. Lodestone is for arXiv research and ingested external repos, not for navigating the current working directory. Use Claude's normal file/grep tools instead.

### Driving lodestone tools directly (bypass)

You can also bypass `/deep-sota` and ask Claude to call lodestone tools individually:

- *"Ingest [arxiv URL]"* → `mcp__lodestone__ingest_paper`
- *"Search lodestone for X"* → `mcp__lodestone__search`
- *"Show me figure 3 of paper Y"* → `mcp__lodestone__figure`
- *"Read the methodology section of paper Y"* → `mcp__lodestone__toc` then `read`
- *"What papers cite Z?"* → `mcp__lodestone__citations`
- *"Do I have anything on long-context retrieval?"* → `mcp__lodestone__coverage`

`/deep-sota` is the intended front-end because it knows the right tool sequence, the right order, and when to stop. Reaching past it is a fallback for fine-grained control.

## Configuration

### Classifier provider + model

`/deep-sota` itself has no config file — it inherits lodestone's. Provider and model live in **`~/.config/lodestone/config.toml`** (XDG-compliant; `%APPDATA%\lodestone\config.toml` on Windows):

```toml
[llm]
provider = "anthropic"   # "anthropic" | "openai" | "gemini"
model = "claude-opus-4-7"
temperature = 0.2
```

Resolution order from `/deep-sota`'s perspective on every ingest call:

1. **Config file exists and has both `[llm].provider` and `[llm].model`?** Proceed with the ingest.
2. **Anything missing?** Stop and tell the user to run `/lodestone:doctor`.

`/lodestone:doctor` is the **sole** provider/model picker in the plugin path. It walks you through the choice and persists `~/.config/lodestone/config.toml`. The skill does not pick, prompt, or write config from inside `/deep-sota` — earlier versions of the skill shipped a fallback picker (`validate-env.sh` + `setup-lodestone.py`), but that flow is gone; doctor is the single owner.

## Requirements

- [`lodestone`](https://github.com/piercelamb/lodestone) (sibling plugin)
- Python ≥ 3.11
- `uv` package manager (for lodestone)
- An LLM API key for the classifier (Anthropic / OpenAI / Gemini — any one)

The `/deep-sota` plugin itself ships only a skill, a marketplace listing, and the two setup scripts. All heavy lifting lives in lodestone.

## Best Practices

1. **Ingest before asking.** An empty corpus can't answer research questions, and `/deep-sota` won't auto-fetch behind your back. Hand it a couple of relevant arXiv URLs in your area first, then start asking. The corpus grows naturally as `/deep-sota` surfaces gaps and hands you `ingest_paper` calls.

2. **Seed the taxonomy first.** Run lodestone's `seed_taxonomy` against the shipped `taxonomy.json` (or your own) before the first ingest so the classifier has a stable scaffold to slot into. The classifier will mint domains from scratch otherwise, but you'll spend the early corpus correcting near-duplicates.

3. **Let coverage decide negatives.** When you're about to claim "lodestone doesn't have X," let the skill run `coverage(topic=X)` first. It returns structured FTS hits, exact taxonomy matches, and rapidfuzz nearest-neighbors with similarity scores — a citation-grade negative is much more useful than a guessed one.

4. **Prefer top-down for unfamiliar territory.** When you're exploring a domain you don't know well, `overview` → `collection` (drilling into the most relevant collection) beats keyword-spamming `search`. The taxonomy is your map.

5. **Use figures.** Lodestone's `figure` tool returns real image bytes that reach the model. When a paper's claim is architectural ("we change the attention pattern to..."), pulling Figure 1 is often more informative than reading three sections of prose.

6. **Validate against training code.** Once paper research has produced an evidenced theory, check the linked repo. `repo_tree` shows the file layout; `read_code` slices specific files. Papers describe what was *intended* — code is what was *built*.

7. **Re-ingest with `force` only when you must.** It re-runs the whole pipeline including the LLM classify call — costs tokens and rewrites the citation graph. Worth it when a paper revision changes substance; not worth it for typos.

## Troubleshooting

### Skill says "Lodestone needs an LLM provider + model configured"

**Issue**: `/deep-sota <url>` stopped before invoking ingest because `~/.config/lodestone/config.toml` is missing or doesn't have both `[llm].provider` and `[llm].model` set.

**Solution**: Run `/lodestone:doctor`. It walks you through provider/model selection, writes the config, and downloads the HF models. Then re-run `/deep-sota <url>`.

### Ingest fails with an auth / API-key error

**Issue**: `~/.config/lodestone/config.toml` pins, say, `provider = "openai"`, but `OPENAI_API_KEY` isn't exported in the shell that launched Claude Code.

**Solution**:
- Export the matching API key and restart Claude Code, or
- Edit `~/.config/lodestone/config.toml` to point at a provider whose key *is* set, or
- Re-run `/lodestone:doctor` and pick a different provider

### "uv not installed"

**Issue**: The plugin entrypoint can't locate `uv`.

**Solution**: Install `uv` from [astral.sh/uv](https://astral.sh/uv) and ensure it's on `PATH`. The plugin won't fall back to system Python. `/lodestone:doctor` flags this too as part of its install-health check.

### `mcp__lodestone__*` tools missing

**Issue**: The skill registers but the `mcp__lodestone__*` tools never appear in the tool registry.

**Solution**: Run **`/lodestone:doctor`** from the lodestone plugin — it diagnoses `uv` presence, venv state, MCP server registration, DB writability, and HuggingFace model cache in one shot, prints a fix line per failure, and **automatically runs the prewarm hook when the venv is missing** (the common `/plugin install lodestone` + `/reload-plugins`-mid-session case). After the prewarm completes, run `/reload-plugins` to pick up the venv.

If `/lodestone:doctor` itself can't run, fall back to:
- Confirm lodestone is installed *and* enabled (`/plugin enable lodestone`)
- Restart Claude Code — MCP tool registration happens at startup

### Empty / nonsensical answers on research questions

**Issue**: The corpus is too sparse to answer.

**Solution**:
- Let the skill run `coverage(topic=...)` to confirm the gap
- Ingest the missing arXiv IDs it surfaces (or hand it new URLs)
- If the suggestion list is empty, lodestone genuinely has nothing nearby — try a different angle, or ingest a survey paper first to anchor a new corner of the taxonomy

### Ingest hangs after laptop sleep

**Issue**: A lodestone LLM-adapter or httpx call was wedged across the suspend.

**Solution**: Already fixed in lodestone — LLM adapter and httpx timeouts are capped server-side. If you see this on an older install, `/plugin update lodestone` and restart Claude Code.

## Project Structure

```
deep_sota/
├── .claude-plugin/
│   ├── plugin.json              # Plugin metadata
│   └── marketplace.json         # piercelamb-plugins marketplace listing
├── LICENSE                      # Apache-2.0
├── CHANGELOG.md
├── README.md                    # This file
└── skills/
    └── deep-sota/
        └── SKILL.md             # The skill definition — protocol lives here
```

The skill is the only load-bearing piece. `SKILL.md` encodes the three-invocation routing, the top-down / bottom-up research patterns, the coverage backstop, the read ladder, citation traversal, and the novelty heuristic. Provider/model configuration and all install validation lives in the lodestone plugin's `/lodestone:doctor` skill.

## Contributing

Contributions welcome! Please:

1. Clone the repository
2. Create a feature branch
3. Submit a pull request

For changes that span both plugins (skill protocol + lodestone behavior), open paired PRs and reference them across.

## License

[Apache-2.0](./LICENSE)

## Author

Pierce Lamb

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Version

0.1.0
