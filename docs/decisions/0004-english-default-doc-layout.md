# ADR-0004: English-default docs with Chinese preserved as a selectable variant

## Status

Accepted.

## Date

2026-08-14

## Context

The brief is explicit: for documentation, English should become the *default*
and the existing Chinese should be *preserved as a translation the reader can
choose* — not overwritten.

The eleven repos currently disagree with each other about how to name language
variants. Observed in the wild:

| Pattern | Seen in |
|---|---|
| `README.md` (zh) + `README.en-US.md` | `go-wind-shop`, `go-wind-cms`, `go-wind-ledger` |
| `README.md` (zh) + `README_en.md` | `go-wind`, `go-wind-bootstrap`, `go-wind-plugins`, `go-wind-uba` |
| `README_EN.md` | `go-wind-toolkit/protoc-gen-go-redact` |
| `README.en.md` | `go-wind-toolkit/protoc-gen-typescript-http`, `protoc-gen-dart-http` |
| `README.ja-JP.md` | `go-wind-cms` |
| `README.ja.md` | `go-wind-toolkit/protoc-gen-typescript-http` |
| `README_ja.md` | `go-wind-bootstrap` |

Five spellings of "English" and three of "Japanese" across one project family.

Two further facts shape the decision:

### The convention is already settled in the sibling repo

`go-admin-translate` — the prior attempt — landed on exactly this layout:

```
README.md          English
README.zh-CN.md    Chinese
README.ja-JP.md    Japanese
```

That part of the prior work was right, and it matches the Vue/Vben ecosystem
convention that these frontends already follow. There is no reason to invent
something new.

### The existing English files are stale, and their links are already broken

`go-admin-translate/README.ja-JP.md` carries the switcher line
`[English](./README.en-US.md) | [中文](./README.md) | **日本語**`, but that repo
has no `README.en-US.md` — its English lives at `README.md`. The switcher was
written for the old layout and never updated when the files moved.

Several `README_en.md` files also predate their Chinese counterparts, so
promoting one to `README.md` without checking would silently ship an outdated
English document as the project's front page.

## Decision

**Normalize every repo to the `.<lang>.md` convention, with English at the
unsuffixed path, moving files with `git mv` so history follows.**

Target layout:

```
README.md          English (default)
README.zh-CN.md    original Chinese
README.ja-JP.md    Japanese, where it exists
docs/*.md          English default
docs/zh-CN/*.md    original Chinese
```

Rules:

1. `git mv README.md README.zh-CN.md` when the current default is Chinese. Using
   `git mv` rather than write-new-delete-old is what keeps `git log --follow`
   and blame intact on documents that have real revision history.
2. Any existing English variant — `README.en-US.md`, `README_en.md`,
   `README_EN.md`, `README.en.md` — is `git mv`'d to `README.md`, then **diffed
   against a fresh translation of the Chinese original** and updated with
   whatever it is missing. Promotion alone is not sufficient.
3. Japanese variants normalize to `README.ja-JP.md`.
4. Every variant gets an idempotent switcher line inserted after the H1:
   `[English](./README.md) · [简体中文](./README.zh-CN.md) · [日本語](./README.ja-JP.md)`
5. `CLAUDE.md`, `AGENTS.md`, `SKILL.md`, `MEMORY.md`, `CHANGELOG.md`,
   `CONTRIBUTING.md` are translated **in place** and never given a language
   variant. They are instructions for tools and contributors, not user-facing
   documentation; a Chinese variant of an agent instruction file has no reader.
6. `frontend/**/locales/**` is untouched. That is runtime i18n, not documentation.

Broken relative links become a verification gate
([ADR-0006 is not needed for this](0005-ast-extraction-with-cjk-span-narrowing.md) —
the check lives in `gwt.verify.broken_doc_links`), specifically because the
prior attempt shipped a switcher pointing at a file that does not exist.

## Alternatives Considered

### `docs/en/` and `docs/zh-CN/` parallel trees for everything, including READMEs

- Pros: uniform; scales to many languages; no filename-suffix parsing.
- Cons: GitHub renders `README.md` at the repo root as the project front page.
  Moving it into `docs/en/` means the repo has no rendered landing page, which
  is a real regression in the primary place these docs get read.
- **Rejected for READMEs, adopted for `docs/`.** The `docs/` tree has no
  equivalent auto-render behaviour, so the parallel-tree form is cleaner there.

### Replace the Chinese entirely

- Pros: simplest; one file per document; no switcher machinery.
- Cons: directly contradicts the brief, and discards work. These are upstream
  projects with Chinese-reading users; the Chinese README is an asset.
- **Rejected:** the requirement was explicit that Chinese be preserved as a
  selectable translation.

### Keep each repo's existing naming, translate in place

- Pros: no moves; no history questions; smallest diff.
- Cons: preserves five spellings of "English" across one project family, and
  leaves `README.md` Chinese — so English is not the default, which was the
  requirement.
- **Rejected:** normalization is the point.

### Write new files instead of `git mv`

- Pros: trivially simple.
- Cons: `git log --follow` and blame break on documents that have meaningful
  revision history.
- **Rejected:** `git mv` costs nothing and preserves it.

## Consequences

- **README history follows the Chinese content** to `README.zh-CN.md`, which is
  correct — that file is the continuation of the document that has the history.
  `README.md` becomes either a promoted existing English file (carrying *its*
  history) or a new file.
- **Promoted English files must be reconciled, not just moved.** Several are
  stale relative to the Chinese. The plan calls for diffing each against a fresh
  translation of `README.zh-CN.md` and merging the gaps. Skipping this ships an
  outdated front page.
- **A link-integrity gate is mandatory.** The switcher introduces relative links
  between files that are being moved in the same commit; the prior attempt got
  this wrong. `broken_doc_links` compares against a pre-run baseline so
  pre-existing breakage is not attributed to this work.
- **`ensure_switcher` must be idempotent.** It is run across eleven repos and
  potentially re-run after fixes; a non-idempotent version would stack duplicate
  switcher lines. Asserted by `test_ensure_switcher_is_idempotent`.
- **Nested READMEs are in scope.** Several packages carry their own
  (`go-wind-plugins/security/authn/jwt/README.md`,
  `go-wind-toolkit/protoc-gen-typescript-http/README.md`), and `plan_moves`
  walks every directory containing a `README*.md` rather than only the repo root.
- **Japanese is preserved but not extended.** Existing `README.ja*` files are
  renamed and linked; no new Japanese translations are produced.
