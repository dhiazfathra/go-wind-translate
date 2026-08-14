# Handoff: zh->en translation tooling — Tasks 1-13 done, resume at Task 14 (optional)

## State as of this handoff

- **Master** (`cfe6abf`) has the full `gwt` tooling: Tasks 1-11.
- **Task 12 done**: pilot run against `go-wind-bootstrap`. Pushed and PR'd
  ([go-wind-bootstrap#1](https://github.com/dhiazfathra/go-wind-bootstrap/pulls)).
- **Task 13 done**: fanned out to all 10 remaining `go-wind*` repos. Every
  repo is committed on `chore/i18n-en-default`, pushed, and has an open,
  self-assigned PR:
  go-wind#1, go-wind-bi#1, go-wind-admin-template#1, go-wind-toolkit#1,
  go-wind-plugins#1, go-wind-ledger#1, go-wind-uba#1, go-wind-shop#1,
  go-wind-cms#1, go-wind-admin#1.
- `cache/segments.jsonl` and `dictionary.tsv` here are up to date with all
  11 repos' resolved segments.
- 121/121 tests passing in this repo.

## Bugs found across Task 12-13 (fixed in this worktree's commits — see git log)

Task 12 (3 bugs): `docs_layout.apply_moves` recreate/rename collision;
`classify.EXCLUDE_GLOBS` missing underscore-style README language variants;
`verify.identifier_drift`'s `_CODE_LINE` heuristic firing on markdown prose.

Task 13, `gwt` code bugs (6, each with a regression test):
4. `docs_layout` link rewriting: relative markdown links weren't adjusted
   when a file moved to a different directory depth (archival).
5. `_is_stale_switcher` false positives/negatives on existing switcher lines.
6. `classify.EXCLUDE_GLOBS` missing README ja/zh underscore-and-case variants.
7. `splice.py` didn't escape translated content going into a Go string
   literal (`"`/`\`), corrupting the source.
8. `verify.identifier_drift` treated single-quoted strings (PowerShell,
   shell) as code skeleton, not literal content — false positive.
9. `verify.identifier_drift`'s masking was line-local, so a multi-line Go
   raw string (backtick-delimited, common for embedded email/prompt
   templates) had each interior line misread as isolated code — rewrote to
   be hunk/line-number aware with precomputed multi-line-opaque ranges.

Task 13, target-repo content findings (4, from a reviewer-subagent pass on
the four large repos — 2 fixed with a `gwt` code change, 2 fixed by hand
with a `dictionary.tsv` pin, none of these four have a new pytest test
since they're data/content, not `gwt` logic):
10. **Runtime i18n violation**, recurring across go-wind-cms/shop/uba:
    `use-simple-locale/messages.ts`'s `Record<Locale, ...>` catalog keyed by
    locale code doesn't match any `EXCLUDE_GLOBS` (dir isn't literally named
    `locales`/`messages`) — the pipeline translated the `zh-CN` block's
    *values* to English, corrupting what that locale renders. Fixed in
    `classify.py` (glob for `*locale*/messages.*` etc.) and by hand-reverting
    the already-translated files (cache stays warm, no re-run needed).
11. **Self-referential language-name labels mistranslated wherever hardcoded
    in code** (`简体中文` → `"Simplified Chinese"`), independent of file
    location — found in `LocaleSwitcher`, `MobileNav`, `Header`,
    `useLocale` hooks, shared `SUPPORT_LANGUAGES` constants, `LangSelect`
    across cms/admin. Structural glob exclusion doesn't scale to this (it's
    not a special directory, just a literal that happens to name a
    language). Fixed properly: pinned `简体中文`/`繁體中文` as identity
    mappings in `dictionary.tsv` (checked before DeepL, wins on exact
    match) — stops recurrence in any future run.
12. **Domain-slang mistranslation** in go-wind-uba: `大课长`/`中课长`/`小课长`
    (gaming spender-tier slang, literally "big/mid/small section chief")
    translated by DeepL into nonsensical corporate titles ("Chief Section
    Chief" etc.) across `analytics_repo.go` (clickhouse+doris),
    `analytics.proto`, generated `openapi.yaml`, and `demo-data.sql`. Pinned
    correct translations (Big/Mid/Small Spender) in `dictionary.tsv`, fixed
    by hand in the six affected files.
13. **SQL seed-data locale mixup + broken quoting** in go-wind-admin:
    `postgresql-demo-data.sql`'s `sys_dict_entry_i18n` rows tagged
    `language_code='zh-CN'` had their content translated to English
    (duplicating the `en-US` rows under the Chinese key — same class as bug
    10 but in SQL, not TS) *and* the translation broke SQL string-literal
    quoting (doubled leading quotes, unescaped apostrophe in `Yu'ebao`).
    Reverting the whole block to Chinese fixed both at once. This surfaced
    a real `splice.py` gap: string-literal escaping assumes Go/TS quoting
    rules universally — a `.sql` file's single-quote escape convention
    (`''`) is different and untouched by the `kind == "string"` escape path
    (see bug 7). Not fixed generically this round (scope: this was one
    seed-data file, not identifier-risk-bearing); worth hardening if `.sql`
    translation becomes routine.

`gwt`/PR #2 bugs found by CodeRabbit review (3, each with a regression test):
14. `splice.py`'s bug-7 escaping (backslash/quote) applied to *both* Go
    interpreted and raw (backtick-delimited) string literals, but a raw
    string treats those characters literally — the escaping corrupted
    content like a Windows path (`C:\tmp`) or an embedded quote when spliced
    into a raw string. Split `NODE_KINDS["go"]` into `"string"`
    (interpreted, escaped) vs `"raw_string"` (unescaped; translations
    containing a backtick are skipped rather than emitted as broken source,
    since a raw string can't represent one).
15. `verify.identifier_drift`'s bug-9 fix (masking multi-line raw-string
    interior lines) also masked the opening/closing *delimiter* lines
    entirely, so a real identifier rename sharing a line with the delimiter
    (`var tmpl = \`Hello`) was silently skipped. Fixed: only interior lines
    are fully skipped; boundary lines get their literal-content side masked
    (via a new `_mask_multiline_boundary`) and still run through
    `_pair_verdict`, so a genuine rename is still caught.
16. `docs_layout._is_stale_switcher`'s `_looks_like_label` accepted *any*
    markdown-link-shaped segment as a language label, so a real two-item nav
    line like `[README](./README.md) | [Changelog](./CHANGELOG.md)` read as
    a stale switcher and `ensure_switcher` would have deleted it. Fixed:
    a link segment must target a README-variant filename, not just look
    like a markdown link.

## What's left

- **Task 14 (optional, not started)**: scoped LLM quality pass over
  short/prose segments MT handles poorly. Confirmed recurring patterns
  worth targeting:
  - Missing spaces around inline placeholders/acronyms in proto/Go comments
    (`UserIDInvalid`, `URIToo long`, `180Tian` for "180 days") — cosmetic,
    comment-only, appears in most `*.proto`/`admin_error.proto`-style files
    across every repo.
  - Full-width Chinese punctuation left adjacent to translated text in a
    few comments (e.g. stray `、`/`（）`).
- **Known, accepted scope limit (not a bug — see Ruling #8 below, extended)**:
  the corpus-wide residual-CJK sweep (Task 13 Step 9, plan line ~2747) came
  back far above the plan's "well under 1,000 per repo" expectation (range:
  4 to ~24,000). Investigated on go-wind-admin: the dominant source is CJK
  *inside markdown fenced code blocks* — e.g. ASCII directory-tree diagrams
  in component READMEs (`Pro/README.md`, `Editor/README.md`) with inline
  Chinese comments (`├── ProForm/  # 动态表单`). `extract_md.py` deliberately
  masks fenced code blocks (ADR-0005: "prose only, code and URLs masked
  out"), so this Chinese is structurally never extracted — not a splice
  failure, not a missed dictionary entry, not a build/identifier/runtime-i18n
  risk. The plan's own Step 9 sweep command doesn't exclude
  `**/migrate/schema.go` (a generated file, correctly never translated) or
  `**/node_modules/**`/`**/vendor/**`, which inflates the count further but
  isn't the dominant factor. Extending `extract_md.py` to selectively
  translate inline comments within fenced code blocks (without touching
  the code itself) is real work — masking would need to distinguish
  "comment token in an illustrative code fence" from "actual code", which
  the current `_SKIP` regex can't do. Ruled out of scope for Task 13;
  flagged here for whoever picks up Task 14 or a Task 15.
- **PR follow-ups per this repo's original standing instructions** (not yet
  done this round): re-run `no-mistakes` and `/autofix` against this
  repo's own PR (the `gwt` tool's accumulated bugfix commits from Task 13
  aren't yet reflected in PR #2's description — only Task 12's fixes are).

## Rulings carried forward (Tasks 1-13)

1. **`cmd_run` pipeline order is `extract -> docs(moves only) -> translate
   -> splice -> switchers`.** Switcher insertion moved to *after* splice
   this round — inserting it before splice shifts every subsequent byte
   offset, corrupting hash-matched spans. Don't reorder this.
2. **`mask.py`'s identifier patterns use explicit lookarounds
   `(?<![A-Za-z0-9_])...(?![A-Za-z0-9_])`, not `\b`** — CJK counts as `\w`
   in Python's `re`, so `\b` doesn't separate Chinese text from an adjacent
   identifier with no space.
3. **`gwt/verify.py`'s `broken_doc_links` uses its own narrower `_mask_md()`**
   (code/HTML only) — don't swap in `extract_md._mask`, which also blanks
   link targets.
4. **`dictionary.tsv` now has 46 entries** (41 boilerplate + 2 identity
   language-label pins + 3 spender-tier pins — see bugs 10-12 above).
   Dictionary lookups are exact-match, checked before DeepL, and win —
   this is the correct place to pin any future "translate this exact
   segment to exactly this" cases, including identity (no-op) pins.
5. **`cmd_verify`/`run_gate` support an optional baseline** (`--baseline`)
   to suppress pre-existing repo defects so the gate only reports
   regressions the translation run introduced. Used for every repo in
   Task 13.
6. **`splice_file` skips an occurrence whose current file bytes no longer
   hash-match what was recorded** — protects against stale-occurrence
   corruption.
7. **`cmd_translate` raises on an engine result-count mismatch** before
   writing to the cache.
8. **`residual_cjk` can be legitimately non-empty by design.** Confirmed
   sources: (a) language-switcher labels naming each language in its own
   script; (b) CJK inside markdown fenced code blocks (masked by design,
   see "What's left" above — this is the dominant source, larger than
   originally scoped in Task 12's bootstrap-only observation).
9. **A literal string that names a language in its own script (`简体中文`)
   or that carries un-translatable domain slang must be pinned in
   `dictionary.tsv`, not chased with `classify.py` glob exclusions.**
   Glob exclusions work for "this whole file/directory is deliberately
   Chinese"; they don't work for "this one hardcoded string, wherever it
   appears in otherwise-translatable code, must not be touched." Dictionary
   identity/override pins are the right tool for that shape of problem.
10. **Never hand-edit a target repo to work around a `gwt` bug you haven't
    fixed in the tool** — but a hand-edit to *revert a specific
    already-fixed-in-tool mistranslation* (after the cache and classify/
    dictionary fix are committed here) is fine and faster than a full
    repo re-run, since the cache stays warm for next time regardless.

## How to resume (Task 14, optional)

1. Read the "What's left" section above for the two concrete quality
   patterns worth an LLM pass, and the fenced-code-comment scope gap if
   pursuing broader residual-CJK reduction.
2. If pursuing Task 14: scope it as a new plan section or ADR before
   touching `extract_md.py` — the fenced-code-comment case especially
   needs a masking design decision, not just a quick patch.
3. All 10 target-repo PRs are open and self-assigned; no further push/PR
   action needed unless CI feedback or review comments come back on them.
