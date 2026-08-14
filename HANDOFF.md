# Handoff: zh->en translation tooling — Tasks 1-13 done, Task 14 slices 1-3 done

## State as of this handoff

- **Master** (`cfe6abf`) has the full `gwt` tooling: Tasks 1-11.
- **Task 12 done**: pilot run against `go-wind-bootstrap`, PR merged.
- **Task 13 done**: fanned out to all 10 remaining `go-wind*` repos. Every
  repo's `chore/i18n-en-default` PR has been reviewed and **squash-merged**:
  go-wind#1, go-wind-bi#1, go-wind-admin-template#1, go-wind-toolkit#1,
  go-wind-plugins#1, go-wind-ledger#1, go-wind-uba#1, go-wind-shop#1,
  go-wind-cms#1, go-wind-admin#1.
- This repo's own Task 12/13 PR (#2) and Task 14 slice 1 PR (recreated as
  #5 after #2's merge triggered GitHub's stacked-PR merge restriction on
  the original #3 — see Ruling #11 below) are both squash-merged into
  `master`.
- `cache/segments.jsonl` and `dictionary.tsv` here are up to date with all
  11 repos' resolved segments.
- 143/143 tests passing in this repo.

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

- **Task 14 slice 1 done** (branch `worktree-task14-llm-quality-pass`, PR
  against this branch): root-caused and fixed the `UserIDInvalid`/
  `URIToo long`/`HTTPThis version...` pattern. It isn't an MT translation
  error — the Chinese source has no space around a Latin identifier
  fragment (`用户ID无效`), extraction correctly narrows to the CJK-only
  spans either side of `ID`, and splicing the English back in place
  faithfully reproduces that same zero-width join, which English can't
  read. Fixed in `gwt/splice.py` + new `gwt/quality.py`:
  `pad_comment_boundary` inspects the literal bytes immediately before/after
  a comment-kind occurrence's span and inserts a space when a known acronym
  (ID, URI, API, HTTP, etc.) glues directly onto the translated word —
  scoped to `kind == "comment"` only, so it can never touch a real code
  identifier. 15 new regression tests, including the exact `用户ID无效`
  case and a multi-segment case (`查询API列表` → `Query API List`, both
  sides pad independently without double-spacing).

  **PR #3 CodeRabbit finding, fixed**: the first commit called
  `fix_spacing()` unconditionally in `cmd_translate`, before caching —
  but the cache is keyed by source hash and shared across every occurrence
  of that segment, including ones spliced into a `string`/`raw_string`
  span where the same Chinese term is a real identifier (e.g. `APIClient`).
  Rewriting the cached value would have silently corrupted those. Fixed:
  both `fix_spacing()` and `pad_comment_boundary()` now run only at splice
  time, only for `kind == "comment"`, never touching the cached value
  itself. 2 more regression tests confirm a cached `APIClient` value
  survives unchanged through both `string` and `raw_string` splicing.

  **Not done in this slice**: re-splicing the already-open target-repo PRs
  to apply this fix to their existing translated files — that means editing
  10 already-open PRs' branches and was judged out of scope for a
  tool-only fix PR; a follow-up run of `gwt run <repo>` after a
  `git checkout -- . && git clean -fd` reset would pick it up for free
  (cache is warm) next time any of those repos' translation gets touched.
- **Task 14 slice 2 done** (branch `worktree-task14-slice2`, merged): pinned
  `180天` → `180 days` in `dictionary.tsv` (was coming back from DeepL as
  the untranslated transliteration `180Tian`). Dictionary lookups are
  exact-match and checked before any MT engine, so this segment now never
  reaches DeepL. 1 new regression test.
- **Task 14 slice 3 done** (branch `worktree-task14-slice3`): full-width
  Chinese punctuation (`，。、；：（）！？`) glued directly onto a
  comment-kind translated span, same root cause as slice 1's acronym-glue
  fix — extraction narrows to the CJK-letter run only, so punctuation
  immediately outside it (e.g. the brackets in `（配置项）`) is never part
  of the segment and never touched by translation, leaving it stuck
  directly against the English word on the other side of the splice.
  `pad_comment_boundary` (`gwt/quality.py`) now pads a leading/trailing
  space whenever a full-width mark is glued to the translated span, on
  either boundary — unlike the acronym-glue check, the leading side has
  no capitalization gate: a full-width punctuation mark can never be
  part of a real code identifier, so the padding applies unconditionally
  (a lowercase-first translated phrase like `（response value` needed
  padding too, caught by post-merge review and fixed same-day, PR #7).
  Trailing-side padding still requires the translated text to end in a
  lowercase letter, matching the acronym case. 4 regression tests
  (unit-level in `test_quality.py`, one end-to-end splice test).
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
4. **`dictionary.tsv` now has 47 entries** (41 boilerplate + 2 identity
   language-label pins + 3 spender-tier pins + 1 `180天` MT-quality pin —
   see bugs 10-12 above and Task 14 slice 2).
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
11. **A PR whose base branch was retargeted by GitHub after its original
    base merged (base-branch deletion auto-retargets to the repo default
    branch) can get stuck as a "stacked PR"** — GitHub blocks both
    `mergePullRequest` (GraphQL) and the REST merge endpoint with
    "Merging stacked PRs via this endpoint is not supported", and
    `enablePullRequestAutoMerge` fails the same way. No async/queue
    endpoint resolves it headlessly. Fix: close the stuck PR and open a
    plain new PR from the same branch against the current default branch
    — content is identical, but it's no longer tracked as part of a stack
    and merges normally.

## How to resume (Task 14, optional)

1. All three known Task 14 quality patterns are now fixed (slices 1-3).
   What remains is the fenced-code-comment scope gap in the "Known,
   accepted scope limit" note above, if pursuing broader residual-CJK
   reduction.
2. If pursuing further: scope it as a new plan section or ADR before
   touching `extract_md.py` — the fenced-code-comment case especially
   needs a masking design decision, not just a quick patch.
3. All 11 `go-wind*` repos (target repos + this tool repo) have their
   Task 12/13/14 work merged to `master`/`chore/i18n-en-default` as
   applicable; no further push/PR action needed unless new CI feedback or
   review comments come back.
