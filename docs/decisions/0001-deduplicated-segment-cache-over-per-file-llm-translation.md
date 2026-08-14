# ADR-0001: Deduplicate segments and cache them, rather than translating files with an LLM

## Status

Accepted.

## Date

2026-08-14

## Context

Eleven `go-wind*` repositories carry Chinese comments, documentation, and string
literals. The task is to render them in English without destroying the runtime
i18n resources that are *supposed* to be Chinese.

The obvious approach — point an agent at the repos and have it translate files —
has already been tried on a sibling repo, and the result is measurable.

### The prior attempt

`go-admin-translate` is a fork of `go-admin` created for exactly this purpose. Its
history shows five translation commits on a `translate-chinese-to-english` branch:

```
ac37994 feat(i18n): translate styling and README documentation
4f1c3ac feat(i18n): comprehensive Chinese-to-English translation
9f88016 feat(i18n): translate proto definitions from Chinese to English
5ecf773 docs: translate Chinese comments and docs to English (#1)
fcfbc75 docs: translate Chinese comments and docs to English
```

Counting the Chinese characters that remain outside the deliberately-Chinese
`locales/` tree:

| Repo | CJK chars outside i18n resources |
|---|---|
| `go-admin` (untouched source) | 83,829 |
| `go-admin-translate` (after 5 translation commits) | **75,224** |

Roughly 90% of the Chinese survived a translation effort explicitly aimed at it,
across 1,031 files. The commit named "comprehensive" was not.

This is not a failure of prompt quality. It is a structural property of
per-file translation at this scale:

1. **No memory between files.** The comment `// 创建用户` appears in dozens of
   files across all eleven repos. Per-file translation re-derives it every time,
   paying full cost per occurrence and producing inconsistent wording.
2. **No resumability.** A run that dies partway leaves no record of what was
   done. The next run starts over.
3. **No convergence signal.** Nothing measures what is left, so "done" is
   declared by exhaustion rather than by evidence.
4. **Regression on merge.** `go-admin-translate`'s final commit is
   `c7e1001 Merge remote-tracking branch 'origin/master'`, which pulled fresh
   Chinese back in. With no cache, re-translating after an upstream merge costs
   as much as the first pass, so it does not happen.

### The corpus, measured

Scanning all eleven repos:

| Measure | Value |
|---|---|
| CJK chars, total | 1,373,775 |
| …in generated files (see [ADR-0002](0002-translate-sources-regenerate-derived-artifacts.md)) | 329,635 |
| …in runtime i18n resources (must stay Chinese) | excluded |
| **Real translatable corpus** | **969,853 chars / 5,171 files** |
| CJK-bearing lines | 174,310 |
| Unique after Unicode-NFC + whitespace normalization | **61,059** |

The dedup ratio is **2.85× at line granularity**, and higher at segment
granularity once a comment's leading `//` and indentation are stripped. The five
large repos (`go-wind-admin`, `-cms`, `-shop`, `-uba`, `-ledger`) share a common
`go-kratos` backend scaffold and a common Vben frontend scaffold, so most of
their boilerplate comments are literally the same strings.

Deduplicated payload lands at roughly 420–480k characters.

## Decision

**Extract translatable segments, deduplicate them by content hash, translate each
unique segment exactly once, and persist the result in a committed cache.**

Concretely:

```
extract  → per-file AST pass yields (byte span, text) occurrences
normalize→ NFC + collapse whitespace
hash     → SHA-1 of normalized text is the segment identity
dedup    → 174,310 occurrences collapse to ~61,000 segments
translate→ only segments absent from the cache are sent anywhere
cache    → cache/segments.jsonl, committed to git
splice   → write translations back by byte span, deepest offset first
```

The cache record is `{"h", "src", "en", "engine"}`. It is committed, not
gitignored: it *is* the artifact. The tooling is regenerable; 61,000 reviewed
translations are not.

## Alternatives Considered

### Per-file LLM translation (the prior attempt)

- Pros: no tooling to build; handles any language without a grammar; best raw
  quality on prose.
- Cons: costs 12–20M input plus 12–20M output tokens across 7,023 files;
  no dedup, so identical comments are paid for repeatedly; no resumability;
  no convergence measurement; re-running after an upstream merge costs full price.
- **Rejected:** empirically does not converge. `go-admin-translate` is the
  experiment and 75,224 residual characters is the result.

### Per-file machine translation, no cache

- Pros: much cheaper than LLM; simple to implement.
- Cons: still pays per occurrence rather than per unique string; still has no
  resumability; sending whole files to an MT engine mangles code, since the
  engine cannot tell a comment from an identifier.
- **Rejected:** the cache is nearly free to add and removes the two worst
  properties.

### Cache keyed on raw text rather than normalized text

- Pros: trivially simple; no normalization bugs.
- Cons: `\t// 创建用户` and `  // 创建用户` and `// 创建用户` become three
  separate cache entries. Indentation variance alone would inflate the segment
  count substantially.
- **Rejected:** NFC plus whitespace collapse is ~3 lines and materially improves
  the hit rate.

## Consequences

- **Re-runs after upstream merges are nearly free.** Only genuinely new segments
  cost anything. This is the specific property whose absence caused the prior
  attempt to regress on merge, and it is the main reason to build tooling at all.
- **Translation becomes deterministic and reviewable.** The same Chinese always
  produces the same English across all eleven repos. A wording fix is one edit to
  `cache/segments.jsonl` plus a re-splice, not a hunt through 5,171 files.
- **Convergence is measurable.** Residual CJK outside the exclusion set is a
  number that must approach zero, so "done" is evidence rather than exhaustion.
- **The engine becomes swappable.** Because translation is a
  `list[str] -> list[str]` call over unique segments, the engine choice is a
  late, reversible decision (see
  [ADR-0003](0003-deepl-free-with-chained-engine-fallback.md)).
- **Cost of the approach:** roughly 1,400 lines of tooling plus tests, against
  approximately zero marginal translation cost. The prior attempt spent far more
  in tokens and did not finish.
- **A wrong translation propagates everywhere that segment appears.** This is the
  flip side of consistency. Mitigated by the fact that fixing it also propagates
  everywhere, from a single edit.
- **`cache/segments.jsonl` will be a large committed file** (~61,000 lines). It
  is sorted by hash on write so diffs stay readable and merges stay tractable.
