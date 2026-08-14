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

## Pipeline

```
extract (tree-sitter, CJK-run spans only)
  → dedup by content hash
  → translate unseen segments (dictionary → DeepL → Argos)
  → permanent cache/segments.jsonl
  → splice back by byte span
  → docs restructure (English default, Chinese as variant)
  → make gen
  → verify (residual CJK, links, identifier drift, build)
```

The cache is committed and permanent. Re-running after an upstream merge only pays for genuinely new segments — the property the prior attempt lacked.

## Docs

- [Execution options](docs/superpowers/specs/2026-08-14-go-wind-translation-options.md) — five approaches costed against the measured corpus, three of which involve no LLM inference
- [Implementation plan](docs/superpowers/plans/2026-08-14-go-wind-zh-en-translation.md) — 14 task-by-task steps with tests

## Scope rules

**Never translated:** `locales/`, `messages/`, `langs/`, `i18n/`, `*.arb`, `[locale]/`, `*zh-CN*`, `README*.ja*` — these are deliberately Chinese runtime resources.

**Never translated, regenerated instead:** `gen/`, `generated/`, `ent/` (except `ent/schema/`), `*.pb.go`, `*.pb.ts`, `migrate/schema.go`. The proto and ent schema sources are translated, then each repo's `make gen` propagates.

**Never altered:** any ASCII token that is camelCase, PascalCase, snake_case, dotted, a call site, a URL, or a printf verb.

## Doc layout

```
README.md          English (default)
README.zh-CN.md    original Chinese, moved via git mv so history follows
README.ja-JP.md    Japanese where present
docs/*.md          English default
docs/zh-CN/*.md    original Chinese
```

Every variant carries a switcher line: `[English](./README.md) · [简体中文](./README.zh-CN.md)`.

## Status

Planning complete. Implementation not started — Task 1 of the plan is the entry point.
