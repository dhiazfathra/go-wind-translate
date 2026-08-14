# Handoff: zh->en translation tooling — Tasks 1-13 done, Task 14 partially done

## State as of this handoff

- **Master** has the full `gwt` tooling plus every fix from Tasks 12-14.
  148/148 tests passing (`python3 -m pytest`, ~4s).
- **Tasks 1-11 done**: the tooling itself, merged in PR #1.
- **Task 12 done**: pilot run against `go-wind-bootstrap`, PR merged.
- **Task 13 done**: fanned out to all 10 remaining `go-wind*` repos. Every
  repo's `chore/i18n-en-default` PR has been reviewed and **squash-merged**:
  go-wind#1, go-wind-bi#1, go-wind-admin-template#1, go-wind-toolkit#1,
  go-wind-plugins#1, go-wind-ledger#1, go-wind-uba#1, go-wind-shop#1,
  go-wind-cms#1, go-wind-admin#1.
- **Task 14: three targeted quality slices done, the plan's own Task 14
  (bulk LLM re-translation) never run** — see "What's left" below. The three
  slices came out of post-merge review findings, not from the plan's Step 1-4
  script.
- This repo's own PRs are all squash-merged into `master`: **#2** (Task
  12/13), **#5** (Task 14 slice 1 — recreated after #2's merge triggered
  GitHub's stacked-PR merge restriction on the original #3, see Ruling #12),
  **#6** (slice 2), **#7** (slice 3), **#8** (doc correction after #7's
  review fix).
- `cache/segments.jsonl` (43,100 segments) and `dictionary.tsv` (47 entries)
  are up to date with all 11 repos' resolved segments. The cache is warm:
  any re-splice or re-run is free and offline.

## Bugs found across Task 12-13 (all fixed and merged — see `git log` / PR #2)

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

Follow-up hardening (2, each with regression tests):
17. `splice.py` applied Go/TS string-literal escaping to *every* language,
    corrupting `.sql` literals on all three characters involved (apostrophe,
    backslash, double quote). Fixed with `_escape_string(en, suffix)` —
    see item 3 under "What's left".
18. `cmd_verify` truncated its printed lists to 20 items per key, so a
    baseline captured by redirecting stdout silently stopped suppressing
    anything past the cap and every later finding read as "new". Added
    `--out`, which writes the untruncated result; stdout keeps the cap for
    readability.

## Task 14 slices done (post-merge review findings)

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

  **Not done in this slice**: re-splicing the target repos to apply this fix
  to their existing translated files. At the time that meant editing 10
  already-open PRs' branches, judged out of scope for a tool-only fix PR.
  Those PRs have since merged, so this is now Next step 1 below.
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
## What's left

Ordered by value. **Item 1 is the only remaining actionable engineering task**
and it needs target-repo pushes, so it needs the user's go-ahead. Item 2 is a
scoping decision the user should make. Items 3 and 5 were prerequisites for
item 1 and are now **done** (kept below for the record). Item 4 stays blocked
on an ADR.

### 1. Propagate the slice 1-3 fixes into the 11 target repos (highest value)

Every `gwt` fix from Task 14 landed **after** the target repos' PRs merged, so
the merged English in those repos still contains the artifacts the tool now
prevents. Verified live on `go-wind-cms` at the time of writing:

```
frontend/admin/apps/admin/src/utils/query.ts:138
  * Create a List QueryJSONFilter String            <- slice 1 (acronym glue)
.../views/app/site_setting/navigation/navigation-view.state.ts:66
  * According to the directionsIDGet the list of navigation items   <- slice 1
.../app/core/preferences/use-preferences.ts:74
  * @param mode Theme Mode (light/dark/auto）        <- slice 3 (full-width glue)
```

This is cosmetic-only (comments and doc prose, never identifiers or runtime
i18n), which is why it wasn't a merge blocker. But it is the whole point of
slices 1-3, and it is currently fixed in the tool and not in the output.

The re-run is **essentially free** — every already-resolved segment is a cache
hit, and `cmd_translate` only calls an engine for segments the cache doesn't
hold. Have `DEEPL_API_KEY` exported anyway: the `classify.py` glob fix from bug
10 changed which files are in scope, so a small number of genuinely new
segments is likely. Per repo:

```bash
# 1. capture a pre-run baseline so the gate reports only NEW defects.
#    Use --out, NOT a stdout redirect -- stdout caps each list at 20 items.
cd ~/Documents/GitHub/dhiazfathra/go-wind-translate
python3 -m gwt.cli verify <repo> --skip-build --out work/<repo>-before.json

# 2. reset the target to its PRE-TRANSLATION state (see caveat below)
cd ~/Documents/GitHub/dhiazfathra/<repo>
git checkout -b chore/i18n-quality-pass <pre-translation-sha>

# 3. re-run and gate
cd ~/Documents/GitHub/dhiazfathra/go-wind-translate
python3 -m gwt.cli run <repo> --engine deepl
python3 -m gwt.cli verify <repo> --baseline work/<repo>-before.json
```

Then rebuild (`make gen` where applicable — never hand-edit generated files,
[ADR-0002](docs/decisions/0002-translate-sources-regenerate-derived-artifacts.md))
and diff-review before pushing.

Two things to watch:

- **Reset caveat.** `git checkout -- . && git clean -fd` on a branch whose
  translation is already committed resets to the *translated* state, not the
  Chinese original. Re-splicing from there is a no-op at best, because
  `splice_file` hash-checks each occurrence and skips non-matching spans
  (Ruling #6). Branch off the **pre-translation** commit, or run
  `git revert`/`git checkout <pre-translation-sha> -- .` first. Getting this
  wrong looks like "the fix didn't apply" rather than an error.
- **The hand-edits from bugs 10-13 are not reproducible by the tool.** The
  `use-simple-locale/messages.ts` reverts and the go-wind-admin SQL block
  revert exist only in the merged history. Bug 10's root cause *is* fixed in
  `classify.py`, so a re-run won't re-break it; bugs 12-13's fixes live in
  `dictionary.tsv` so they hold too. Bug 13's `.sql` **quoting** damage was
  the one real blocker here and is now fixed in the tool (item 3), so the
  re-run no longer needs `postgresql-demo-data.sql` excluded. Its *locale
  mixup* half was a content revert and stays a manual check: confirm the
  `language_code='zh-CN'` rows come back Chinese, not English.

Sequence it smallest-repo-first, same as Task 13, and confirm with the user
before any push or PR against a target repo — that standing rule has not
changed.

### 2. Decide the fate of the plan's actual Task 14

The plan's [Task 14](docs/superpowers/plans/2026-08-14-go-wind-zh-en-translation.md)
(line ~2770) is a **bulk LLM re-translation**: select every segment under 8
characters (Step 1, expected 6,000-9,000 of them), re-translate in batches of
100 through an LLM with a code-comment-appropriate prompt, write back with
`Cache.put(h, src, en, "llm")`, then re-splice and re-verify all 11 repos.

**None of that has been run.** Slices 1-3 were targeted bugfixes for specific
defects review surfaced; they are not a substitute for the corpus-wide pass,
and the handoff should not be read as "Task 14 is done."

Two honest options — pick one and record it, don't leave it ambiguous:

- **Run it.** Step 1's selection script is ready to use as written. Cost is
  roughly 1-2% of translating the corpus. This subsumes item 1's re-splice
  (Step 3 is the same sweep), so if you're doing both, do this one and get
  item 1 for free.
- **Descope it.** Write an ADR recording that MT quality was judged good
  enough for a comment/doc corpus, that the three review-surfaced patterns
  were fixed at the tool level instead, and that the cache stays open to
  targeted `dictionary.tsv` pins (Ruling #4/#9) as future problems appear.
  This is the cheaper answer and is defensible — but it needs writing down,
  because the plan currently reads as unfinished.

### 3. `.sql` string-literal escaping in `splice.py` — DONE

Bug 13 above. `splice.py`'s `kind == "string"` escape path assumed Go/TS
quoting rules universally; standard SQL escapes a single quote by doubling it
(`''`), treats backslash as an ordinary byte, and uses double quotes for
*identifiers* rather than strings. So splicing English containing an
apostrophe into a `.sql` literal broke the file, and any double quote or
backslash in the translation was written into the data as visible garbage.
Originally fixed by hand in the one affected seed-data file; now fixed in the
tool.

**Fix**: new `_escape_string(en, suffix)` in `splice.py`, dispatching on the
**file suffix** rather than the occurrence's `kind`. `kind` records what
construct the span sits in, not whose quoting rules apply — splitting on it
alone is exactly what produced this bug. `.sql` doubles the apostrophe and
leaves backslash/double-quote alone; every other language keeps the bug-7
behaviour unchanged. 4 regression tests, including a guard that `.go` string
literals still get backslash escaping and that a `--` SQL comment is never
quote-escaped.

Known limit, deliberately not addressed: `.sql` has no tree-sitter grammar
here, so it goes through `_extract_lines`, which labels any non-comment
CJK-bearing line `"string"`. In practice non-comment CJK in these files is
always inside a `'...'` literal, so the doubling is right; a CJK run sitting
outside any literal would produce a stray `''`, but such a line wouldn't be
valid SQL to begin with.

### 4. Fenced-code-block CJK (accepted scope limit, not a bug)

See Ruling #8. The corpus-wide residual-CJK sweep (Task 13 Step 9, plan line
~2747) came back far above the plan's "well under 1,000 per repo" expectation
(range: 4 to ~24,000). Investigated on go-wind-admin: the dominant source is
CJK *inside markdown fenced code blocks* — e.g. ASCII directory-tree diagrams
in component READMEs (`Pro/README.md`, `Editor/README.md`) with inline Chinese
comments (`├── ProForm/  # 动态表单`). `extract_md.py` deliberately masks
fenced code blocks (ADR-0005: "prose only, code and URLs masked out"), so this
Chinese is structurally never extracted — not a splice failure, not a missed
dictionary entry, not a build/identifier/runtime-i18n risk.

**Do not patch `extract_md.py` for this without writing an ADR first.** The
masking rule it would change is the one ADR-0005 states explicitly, and
distinguishing "comment token in an illustrative code fence" from "actual
code" is a design decision with a real false-positive cost: translating
something a fence meant literally. The current `_SKIP` regex can't make that
distinction. Write the ADR, then the code. Ruled out of scope for Task 13 and
still out of scope for a quick patch.

### 5. Residual-CJK sweep command hygiene — DONE

The plan's Step 9 sweep didn't exclude `**/migrate/schema.go` (generated,
correctly never translated), `**/node_modules/**`, or `**/vendor/**`, so its
count included files that are never translation candidates. Never a
correctness issue — it just made the sweep's output misleading to whoever ran
it next, and invited reading a high count as a pipeline failure.

**Fix**: the three exclusions added to the Step 9 command in the plan, plus a
note directly under it recording that the sweep did **not** meet its stated
"well under 1,000 per repo" expectation when actually run (4 to ~24,000) and
pointing at item 4 for why that is by design rather than a bug.

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
11. **An `Occurrence`'s `kind` says what construct a span sits in, not whose
    syntax rules apply to it.** Escaping, quoting, and comment conventions
    are properties of the *language*, so they dispatch on the file suffix
    (`_escape_string` in `splice.py`), not on `kind`. Conflating the two is
    what let `.sql` literals get Go escaping (bug 17). `kind` is still the
    right switch for construct-shaped questions — comment-boundary padding
    genuinely only applies to comments.
12. **A PR whose base branch was retargeted by GitHub after its original
    base merged (base-branch deletion auto-retargets to the repo default
    branch) can get stuck as a "stacked PR"** — GitHub blocks both
    `mergePullRequest` (GraphQL) and the REST merge endpoint with
    "Merging stacked PRs via this endpoint is not supported", and
    `enablePullRequestAutoMerge` fails the same way. No async/queue
    endpoint resolves it headlessly. Fix: close the stuck PR and open a
    plain new PR from the same branch against the current default branch
    — content is identical, but it's no longer tracked as part of a stack
    and merges normally.

## How to resume

Nothing is mid-flight. There is no dirty worktree, no open PR, no failing
test, and no blocked step — every branch this project created is merged and
its worktree removed. Pick up from "What's left" above.

**First 10 minutes, whatever you pick:**

```bash
cd ~/Documents/GitHub/dhiazfathra/go-wind-translate
git pull --ff-only origin master   # local master goes stale fast; work happened in worktrees
python3 -m pytest -q               # must be 143/143 before touching anything
```

The pull matters: this repo's local checkout was stale by five merged commits
when this handoff was written, because every slice was built in a worktree and
merged on GitHub. `git log --oneline origin/master` is the truth, not the
working copy.

**Then, by item:**

- **Item 1 or 2** (target-repo re-splice, or the bulk LLM pass): both end in
  the same 11-repo sweep, so if you want both, do item 2 and item 1 comes
  free. Read item 1's two caveats before the first reset — the
  reset-to-translated-state trap silently produces a no-op that looks like a
  broken fix. Item 1's prerequisites (items 3 and 5) are already done.
- **Item 2** is a decision, not a task. Don't start the bulk LLM pass or
  write the descoping ADR without the user picking one.
- **Item 4** (fenced code blocks): write the ADR before any code.

**Standing rules that still apply** (see CLAUDE.md for the full set):

- Fix bugs in `gwt`, never by hand-editing a target repo — Ruling #10 carves
  out only the narrow "revert an already-fixed-in-tool mistranslation" case.
- `python3 -m pytest` green before any commit.
- `cache/segments.jsonl` is the artifact — committed, never regenerated,
  never gitignored ([ADR-0001](docs/decisions/0001-deduplicated-segment-cache-over-per-file-llm-translation.md)).
- Confirm with the user before any push or PR against a target `go-wind*`
  repo. Work inside this repo doesn't need that confirmation.
- Work in a worktree (`superpowers:using-git-worktrees`) off fresh `master`,
  one slice per PR. Commit before `ExitWorktree` — `discard_changes: true`
  discards uncommitted working-tree edits along with unmerged commits.
