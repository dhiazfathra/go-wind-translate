# ADR-0007: Keep markdown masking as-is, but repair targets derived from translated text

## Status

Accepted. Extends [ADR-0005](0005-ast-extraction-with-cjk-span-narrowing.md)'s
markdown masking rule rather than superseding it.

## Date

2026-08-14

## Context

ADR-0005 masks fenced code, inline code, link targets, raw HTML, URLs, and
frontmatter out of markdown before anything reaches a translator: "prose only,
code and URLs masked out." Task 13's corpus-wide sweep then came back far above
the plan's "well under 1,000 per repo" expectation — 4 to roughly 24,000 — and
that gap was carried in `HANDOFF.md` as an open question about whether masking
was too aggressive.

Measured properly on `go-wind-admin`, excluding deliberately-non-English files
(`*.zh-CN.md`, `*.ja-JP.md`, …), `node_modules`, and `vendor`:

| Where the residual CJK is | chars |
|---|---:|
| Inside fenced code blocks | 13,090 |
| Prose, in files `classify.py` deliberately excludes | 7,241 |
| Prose, in files `gwt` considers translatable | **585** |

So 96% of it is either fenced code or a file the pipeline is correct to skip.
Only 585 characters sit in prose the pipeline actually processes, and sampling
those shows four distinct categories — every one of them masked deliberately:

1. **Fenced code.** Overwhelmingly ASCII directory-tree diagrams with inline
   Chinese comments: `├── app/ # 微服务主目录`.
2. **HTML comments** in issue and PR templates: `<!-- 勾选适用项 -->`.
3. **Inline code spans** naming literal values the documented code compares
   against: ``- **add**: `"add"`, `"新增"`, `"添加"` -> `add` ``. Translating
   `"新增"` here would make the documentation describe behaviour the code does
   not have.
4. **Link and anchor targets**: `[简体中文](./README.zh-CN.md)`,
   `[Architecture Overview](#架构概览)`.

Categories 1-3 confirm masking is right. Category 4 is where a real defect was
hiding.

### The defect: a masked target derived from text that *was* translated

A heading is prose, so it is translated. An in-page anchor is a link target, so
it is masked. Both decisions are individually correct, and together they break
the document:

```markdown
## 架构概览                    ->  ## Architecture Overview
- [Overview](#架构概览)         ->  - [Overview](#架构概览)     <- now resolves to nothing
```

Nothing caught this. `verify.broken_doc_links` skips any target starting with
`#` by design, and for `other.md#frag` checks only the file half. Measured in
the merged output:

| repo | broken in-page anchors |
|---|---:|
| go-wind-cms | 23, in 4 files |
| go-wind-admin | 9, in 2 files |
| go-wind-bootstrap | 0 |

This is not cosmetic in the way the acronym-glue artifacts were — a table of
contents that navigates nowhere is functionally broken documentation.

The general shape: **masking a region means the pipeline will not translate it,
but it does not mean the region is independent of what the pipeline translates.**
A fragment identifier is *derived* from heading text. Mask it, then change what
it derives from, and it silently rots.

## Decision

**Keep every masking rule from ADR-0005 unchanged. Add a post-splice repair pass
for targets whose value is derived from translated text, and a gate check that
fails when such a target no longer resolves.**

Concretely, three things, all shipped with this ADR:

1. `quality.repair_anchors(before, after)` runs after a `.md` file is spliced.
   It pairs headings positionally — splicing replaces bytes in place and never
   adds or removes a line, so the Nth heading before is the Nth heading after —
   computes each one's GitHub slug on both sides, and rewrites only anchors
   whose target matches a slug that actually changed. A differing heading count
   means the two versions are not the same document, so it returns the file
   untouched rather than mis-pair. An anchor pointing at something that was
   never a heading in this file is left alone rather than guessed at.

   It must run per *file*, not per occurrence: a slug derives from the whole
   heading line, which can hold several segments plus untranslated Latin runs
   (`## API 两层架构` → `#api-两层架构`), so it cannot be computed from any one
   segment's replacement.

2. `verify.broken_anchors` reports same-file `](#fragment)` links that no
   heading in that file resolves, and joins `run_gate`'s result under
   `broken_anchors`. Fenced and inline code are masked first, for the same
   reason `broken_doc_links` does it: documentation illustrates link syntax, and
   a gate that fires on illustrations is one reviewers learn to ignore.

3. Fenced-code CJK is **accepted permanently**, not deferred. See below.

### Why fenced code stays masked

Extending extraction into fenced blocks would mean deciding, per line, whether
a token is an illustrative comment or content that must survive byte-identical.
The blocks in this corpus are mostly not parseable code at all — ASCII tree
diagrams, shell transcripts, sample output, config fragments — so no grammar
resolves it and the decision falls to a heuristic.

The asymmetry of costs settles it. Leaving a Chinese comment in a directory
diagram is visible and harmless; a reader sees Chinese where they expected
English. Translating a line that was meant literally silently corrupts a
command someone copy-pastes, a filename, or a struct tag. ADR-0005 already
recorded this direction of erring — "an untranslated token is visible and
fixable; a renamed symbol is a silent bug" — and category 3 above shows the
same hazard in prose: `"新增"` is a literal the documented code matches on.

`residual_cjk` being non-empty is therefore expected, and its count is not a
defect measure. Ruling #8 in `HANDOFF.md` already says so; this ADR makes it a
decision rather than an observation.

## Alternatives Considered

### Translate headings but leave their anchors, and accept broken links

- Pros: no new code.
- Cons: 32 measured broken links across two repos, silently, with the gate
  blind to them. Documentation navigation is a feature.
- **Rejected.**

### Don't translate headings, so anchors stay valid

- Pros: trivially correct; no repair pass, no gate check.
- Cons: headings are the most reader-visible prose in a document. An
  English-default README ([ADR-0004](0004-english-default-doc-layout.md)) whose
  section titles are all Chinese defeats the point of the exercise.
- **Rejected.**

### Rewrite anchors from the cache's zh→en mapping instead of from heading lines

- Pros: no before/after pairing needed; works from data already in hand.
- Cons: a slug derives from an entire heading line, which routinely mixes
  translated CJK with untouched Latin (`## API 两层架构`). The mapping for one
  segment is not enough to compute the slug, and stitching several segments back
  together reimplements the splice that just ran.
- **Rejected** as reconstructing information the before/after files already hold
  exactly.

### Extend `extract_md.py` to translate comments inside fenced blocks

- Pros: would cut the largest residual-CJK category, ~13,000 chars in
  `go-wind-admin` alone.
- Cons: requires distinguishing "comment in an illustrative fence" from "content
  that must not change" using a heuristic over content that is frequently not
  code. A false positive rewrites a copy-pasteable command. The visible cost of
  *not* doing it is a reader seeing Chinese in a tree diagram.
- **Rejected permanently**, not deferred. `HANDOFF.md` previously carried this
  as an open item pending a design decision; this ADR is that decision.

### Convert Chinese headings' anchors to English but keep a Chinese alias

- Pros: any external link to the old Chinese fragment keeps working.
- Cons: needs an explicit `<a id>` anchor injected per heading, i.e. writing
  HTML into every translated document to serve inbound links that, for internal
  component READMEs, essentially do not exist.
- **Rejected** as disproportionate. Noted in case a public-facing doc ever needs it.

## Consequences

- **`run_gate` gains a `broken_anchors` key.** A baseline captured before this
  change has no such key, and `cmd_verify`'s baseline subtraction reads a
  missing key as an empty list — so pre-existing broken anchors will correctly
  surface as new findings on the next run rather than being silently suppressed.
  That is the desired behaviour here: the 32 known-broken links *should* appear.
- **The 32 broken anchors already in merged output are not fixed by this ADR.**
  They are fixed by re-running the pipeline over those repos, which is the
  pending propagation task in `HANDOFF.md`. This change means the re-run repairs
  them and the gate proves it.
- **Positional heading pairing is a real constraint on splicing.** It holds only
  because splice never adds or removes lines. Any future step that inserts
  content into a markdown file must run *before* splice — the same ordering
  constraint that already applies to switcher insertion (Ruling #1).
- **The slug function approximates GitHub's.** It lowercases, drops punctuation
  outside `\w\s-`, and hyphenates whitespace, keeping CJK verbatim. It does not
  implement duplicate-heading disambiguation (`-1`, `-2` suffixes). A document
  with two identically-titled headings whose anchors distinguish them by suffix
  is not handled; none exist in this corpus, and `broken_anchors` would report
  it rather than corrupt it.
- **"Masked" now explicitly does not mean "independent."** Any future masked
  region whose value derives from translatable text needs the same treatment.
  The known instances are heading anchors (handled here) and relative link paths
  under a file move (already handled by `docs_layout`'s link rewriting).
