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

**Tasks 1-13 of the [implementation plan](docs/superpowers/plans/2026-08-14-go-wind-zh-en-translation.md) are done, and Task 14 is closed as descoped ([ADR-0006](docs/decisions/0006-close-task-14-bulk-llm-pass.md)) — 167/167 tests passing.** All 11 `go-wind*` repos have been translated and reviewed; nine have open PRs from the propagation sweep and two needed no change. The fan-out, review, and propagation passes surfaced and fixed 21 real bugs in `gwt` itself — see [HANDOFF.md](HANDOFF.md) for the full list, including two recurring runtime-i18n corruption patterns (self-referential language labels, locale-keyed message catalogs) guarded against via `dictionary.tsv` identity pins and a `classify.py` glob, a comment-splicing gap (`gwt/quality.py`) that glued acronyms and full-width punctuation directly onto translated words wherever Chinese needed no space but English does, an MT-quality miss (`180天` → `180Tian`) fixed with a dictionary pin, per-language string-literal escaping so a `.sql` literal is no longer escaped by Go/TypeScript rules, and translated headings orphaning their own in-page anchors (32 dead links across two repos, invisible to the gate until it gained a `broken_anchors` check). The last two were found by piloting the propagation re-run on the smallest repo before sweeping all eleven — a stale switcher removal leaving an empty `<p align="center">` wrapper, and a heading-slug bug that collapsed whitespace runs where GitHub maps each space to its own hyphen.

**The fixes have been propagated to the target repos**, and nine PRs are open for review (`#2` in admin-template, toolkit, plugins, ledger, uba, shop, cms and admin; `#1` in bootstrap, whose original pilot PR was never merged). `go-wind` and `go-wind-bi` needed no change — the current tool reproduces their merged output byte-for-byte. Residual Chinese fell sharply in every repo (go-wind-cms 221,912 → 13,363 characters; go-wind-admin 215,103 → 12,306), with no new broken links, no new broken anchors and no identifier drift against a pre-translation gate baseline. **The whole eleven-repo re-run needed zero translation-engine calls** — every one of the 43,100 segments was a cache hit, which is precisely what [ADR-0001](docs/decisions/0001-deduplicated-segment-cache-over-per-file-llm-translation.md) buys.

Two questions the fan-out left open are now decided rather than deferred. [ADR-0006](docs/decisions/0006-close-task-14-bulk-llm-pass.md) closes the planned bulk LLM quality pass: its selection criterion (`len(src) < 8`) turns out to match 58.7% of the corpus rather than the estimated 1-2%, because span narrowing deliberately produces short segments, and its cache write-back is unsafe against a cache with no per-kind dimension. [ADR-0007](docs/decisions/0007-markdown-masking-policy-and-derived-target-repair.md) accepts CJK inside markdown fenced code blocks permanently — 96% of the residual is fenced code or a correctly-skipped file — while fixing the one place where masking a region and translating its source had drifted apart.

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
| [0006](docs/decisions/0006-close-task-14-bulk-llm-pass.md) | Close Task 14's bulk LLM pass; pin quality misses in the dictionary instead |
| [0007](docs/decisions/0007-markdown-masking-policy-and-derived-target-repair.md) | Keep markdown masking as-is, but repair targets derived from translated text |

## Docs

- [Execution options](docs/superpowers/specs/2026-08-14-go-wind-translation-options.md) — spec; five approaches costed against the measured corpus, three of which involve no LLM inference
- [Implementation plan](docs/superpowers/plans/2026-08-14-go-wind-zh-en-translation.md) — 14 task-by-task steps with tests
- [Decision records](docs/decisions/README.md) — why the approach looks like this

## Scope rules

**Never translated:** `locales/`, `messages/`, `langs/`, `i18n/`, `*.arb`, `[locale]/`, any `*locale*/messages.*`-shaped catalog file, `*zh-CN*`, `README*.ja*`/`README*.zh*`/`README*.en*` (dot- and underscore-style, any case) — these are deliberately Chinese runtime resources or already-handled README language variants.

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

Each translated repo got one branch (`chore/i18n-en-default`) and one PR. See the Status section above for current per-repo state.
