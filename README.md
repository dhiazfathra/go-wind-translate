# go-wind-translate

Tooling and plans for translating Chinese comments, docs, and non-i18n strings across the eleven `go-wind*` repositories to English — without burning LLM tokens on the bulk of the work.

## Why this exists

`go-admin-translate` is a prior attempt at the same task, driven by whole-file LLM translation. It left **75,224 CJK characters** untranslated — roughly 90% of its source repo's Chinese — and translated generated files that revert on the next `make gen`. Whole-file agentic translation does not converge at this scale.

The approach here converges because it deduplicates first:

| Measure | Value |
|---|---|
| CJK chars across 11 repos | 1,373,775 |
| …in generated files (regenerate instead) | 329,635 |
| …in runtime i18n resources (leave Chinese) | excluded |
| **Real translatable corpus** | **969,853 chars / 5,171 files** |
| CJK-bearing lines | 174,310 |
| Unique after normalization | 61,059 (2.85×) |

Deduplicated payload lands around 450k characters — inside DeepL Free's 500k/month tier. Translation cost: $0.

See [ADR-0001](docs/decisions/0001-deduplicated-segment-cache-over-per-file-llm-translation.md) for the full argument and the evidence from the prior attempt.

## Status

**Tooling built (Tasks 1-11 of the [implementation plan](docs/superpowers/plans/2026-08-14-go-wind-zh-en-translation.md)), 100/100 tests passing.** The `gwt` CLI below runs end to end against a stub engine; a live pilot run against `go-wind-bootstrap` (Task 12) needs a `DEEPL_API_KEY`. Fan-out to the other ten repos (Task 13) and the optional LLM quality pass (Task 14) follow after the pilot.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
export DEEPL_API_KEY='<your-key>:fx'      # free tier, no card required
python3 -m pytest                          # must be green before touching any repo
gwt run go-wind-bootstrap --engine deepl   # pilot repo
```

Target repos are expected as siblings of this one, under `~/Documents/GitHub/dhiazfathra/`.

## Commands (planned CLI surface)

| Command | Description |
|---|---|
| `gwt extract <repo>` | Parse the repo, write `work/<repo>/occurrences.jsonl`, report occurrence and unique-segment counts |
| `gwt translate <repo> --engine deepl` | Translate segments not already in the cache; chains dictionary → engine |
| `gwt splice <repo>` | Write cached translations back into the repo by byte span |
| `gwt docs <repo> [--dry-run]` | Restructure READMEs and `docs/` to English-default, insert language switchers |
| `gwt verify <repo> [--skip-build] [--baseline <path>]` | Residual CJK, broken doc links, identifier drift, build. `--baseline` takes a prior `gwt verify` JSON result and only reports findings that are new relative to it |
| `gwt run <repo> --engine deepl` | The whole pipeline: extract → docs → translate → splice → `make gen` → verify |

## Architecture

```
extract   tree-sitter parse; spans narrow to the Chinese run only,
          so adjacent identifiers are never part of a segment
dedup     NFC + whitespace-collapse + SHA-1; 174,310 occurrences → ~61,000 segments
docs      README.md moves to README.zh-CN.md via git mv (preserved, untouched
          from here on); a working copy is recreated at README.md so the
          steps below can still translate it. Runs BEFORE translate/splice,
          since the has_cjk() check that triggers the archival move needs to
          see the still-Chinese content, not an already-translated README.
translate chained engines, first hit wins: dictionary → DeepL → Argos
cache     cache/segments.jsonl, committed and permanent
splice    byte-span writeback, deepest offset first; skips a span whose
          current bytes no longer hash-match the occurrence it was recorded
          for (stale occurrences.jsonl), rather than risk corrupting it
regen     each repo's own `make gen` propagates translated proto / ent schema
verify    residual CJK, link integrity, identifier drift, build; optionally
          diffed against a baseline to ignore pre-existing defects
```

The cache is committed, not gitignored — it *is* the artifact. Re-running after an upstream merge only pays for genuinely new segments, which is the property the prior attempt lacked.

Design rationale lives in [`docs/decisions/`](docs/decisions/README.md):

| # | Decision |
|---|---|
| [0001](docs/decisions/0001-deduplicated-segment-cache-over-per-file-llm-translation.md) | Deduplicate segments and cache them, rather than translating files with an LLM |
| [0002](docs/decisions/0002-translate-sources-regenerate-derived-artifacts.md) | Translate generator inputs, regenerate their outputs |
| [0003](docs/decisions/0003-deepl-free-with-chained-engine-fallback.md) | DeepL Free as the primary engine, behind a chained fallback |
| [0004](docs/decisions/0004-english-default-doc-layout.md) | English-default docs with Chinese preserved as a selectable variant |
| [0005](docs/decisions/0005-ast-extraction-with-cjk-span-narrowing.md) | Extract with an AST, narrow spans to the Chinese run, mask what remains |

## Docs

- [Execution options](docs/superpowers/specs/2026-08-14-go-wind-translation-options.md) — spec; five approaches costed against the measured corpus, three of which involve no LLM inference
- [Implementation plan](docs/superpowers/plans/2026-08-14-go-wind-zh-en-translation.md) — 14 task-by-task steps with tests
- [Decision records](docs/decisions/README.md) — why the approach looks like this

## Scope rules

**Never translated:** `locales/`, `messages/`, `langs/`, `i18n/`, `*.arb`, `[locale]/`, `*zh-CN*`, `README*.ja*` — these are deliberately Chinese runtime resources.

**Never translated, regenerated instead:** `gen/`, `generated/`, `ent/` (except `ent/schema/`, which is hand-written), `*.pb.go`, `*.pb.ts`, `migrate/schema.go`. The proto and ent schema sources are translated, then each repo's `make gen` propagates. See [ADR-0002](docs/decisions/0002-translate-sources-regenerate-derived-artifacts.md).

**Never altered:** any ASCII token that is camelCase, PascalCase, snake_case, dotted, a call site, a URL, or a printf verb. See [ADR-0005](docs/decisions/0005-ast-extraction-with-cjk-span-narrowing.md).

## Doc layout

```
README.md          English (default)
README.zh-CN.md    original Chinese, moved via git mv so history follows
README.ja-JP.md    Japanese where present
docs/*.md          English default
docs/zh-CN/*.md    original Chinese
```

Every variant carries a switcher line: `[English](./README.md) · [简体中文](./README.zh-CN.md)`.

## Target repos

`go-wind`, `go-wind-admin`, `go-wind-admin-template`, `go-wind-bi`, `go-wind-bootstrap`, `go-wind-cms`, `go-wind-ledger`, `go-wind-plugins`, `go-wind-shop`, `go-wind-toolkit`, `go-wind-uba`

One branch per repo (`chore/i18n-en-default`), one PR per repo.
