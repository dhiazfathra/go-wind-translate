# Handoff: zh->en translation tooling — Tasks 1-13 done, Task 14 closed as descoped

## State as of this handoff

- **Master** has the full `gwt` tooling plus every fix from Tasks 12-14.
  167/167 tests passing (`python3 -m pytest`, ~4s), `ruff check .` clean.
- **Tasks 1-11 done**: the tooling itself, merged in PR #1.
- **Task 12: pilot run done, but its PR is still OPEN.**
  `go-wind-bootstrap#1` was never merged — an earlier version of this
  handoff claimed it was, which was wrong. It is now updated with the
  quality-pass re-run (force-pushed onto `chore/i18n-en-default`, since the
  PR was unmerged and the re-run supersedes its single commit).
- **Task 13 done**: fanned out to all 10 remaining `go-wind*` repos. Every
  repo's `chore/i18n-en-default` PR has been reviewed and **squash-merged**:
  go-wind#1, go-wind-bi#1, go-wind-admin-template#1, go-wind-toolkit#1,
  go-wind-plugins#1, go-wind-ledger#1, go-wind-uba#1, go-wind-shop#1,
  go-wind-cms#1, go-wind-admin#1.
- **Propagation done** (was item 1 below): the accumulated tool fixes have
  been re-applied to every target repo. Eight new PRs (`#2` in
  admin-template, toolkit, plugins, ledger, uba, shop, cms, admin) plus
  bootstrap's updated `#1`. `go-wind` and `go-wind-bi` needed **no change**
  — the current tool reproduces their merged output byte-for-byte.
- **Task 14 is CLOSED as descoped** by
  [ADR-0006](docs/decisions/0006-close-task-14-bulk-llm-pass.md). Its bulk LLM
  re-translation was never run and will not be; the three targeted quality
  slices that shipped came from post-merge review findings instead. See
  item 2 under "What's left" for the measurements behind that call.
- **Markdown masking policy settled** by
  [ADR-0007](docs/decisions/0007-markdown-masking-policy-and-derived-target-repair.md),
  which also fixed a real defect it surfaced (bug 19: translated headings
  orphaning their in-page anchors).
- This repo's own PRs are all squash-merged into `master`: **#2** (Task
  12/13), **#5** (Task 14 slice 1 — recreated after #2's merge triggered
  GitHub's stacked-PR merge restriction on the original #3, see Ruling #13),
  **#6** (slice 2), **#7** (slice 3), **#8** (doc correction after #7's
  review fix), **#9** (per-language string escaping, `verify --out`).
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

Follow-up hardening (5, each with regression tests):
17. `splice.py` applied Go/TS string-literal escaping to *every* language,
    corrupting `.sql` literals on all three characters involved (apostrophe,
    backslash, double quote). Fixed with `_escape_string(en, suffix)` —
    see item 3 under "What's left".
18. `cmd_verify` truncated its printed lists to 20 items per key, so a
    baseline captured by redirecting stdout silently stopped suppressing
    anything past the cap and every later finding read as "new". Added
    `--out`, which writes the untruncated result; stdout keeps the cap for
    readability.
19. **Translating a markdown heading orphaned every in-page anchor pointing
    at it**, and the gate was blind to it: `broken_doc_links` skips any
    `#`-prefixed target by design. A heading is prose (translated); an
    anchor is a link target (masked) — both correct individually, broken
    together. Measured in merged output: 23 dead links in go-wind-cms
    (4 files), 9 in go-wind-admin (2 files), 0 in go-wind-bootstrap. Fixed
    with `quality.repair_anchors` (post-splice, per markdown file) plus a
    new `verify.broken_anchors` gate check. See
    [ADR-0007](docs/decisions/0007-markdown-masking-policy-and-derived-target-repair.md).
    Verified end-to-end against the genuine pre-translation file from
    go-wind-cms's git history: 7 broken anchors in that file become 0, with
    correct mappings (`#架构概览` → `#architecture-overview`), and only the
    7 anchor lines change.

Both of the following were caught by **piloting the propagation re-run on
`go-wind-bootstrap` before touching any other repo** — the direct argument
for piloting rather than sweeping all eleven at once:

20. `ensure_switcher` deleted a stale switcher line by index with no
    awareness of the `<p align="center">` wrapper several repos centre it
    in, leaving an empty centred paragraph — visible cruft in the rendered
    README and a regression against the previous translation, which had
    left the whole block alone. Fixed with `_stale_span`, which takes the
    wrapper when the stale line is its sole content (a wrapper holding
    badges or a tagline keeps its tags) plus one surrounding blank line so
    removal doesn't leave a doubled blank.
21. `heading_slug` collapsed whitespace *runs* to one hyphen; GitHub maps
    **each** whitespace character to its own hyphen. Only equivalent when a
    heading has no punctuation between words — and `### Repeated / Map
    Fields` drops the `/`, leaving two adjacent spaces, so the real
    fragment is `repeated--map-fields`. `broken_anchors` reported three
    perfectly valid anchors in go-wind-toolkit as broken. `repair_anchors`
    was not observed to corrupt anything (a mis-computed old slug simply
    fails to match, so no rewrite happens) but could have mapped an anchor
    onto a wrong new slug, so this is a correctness fix, not gate noise.

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

**Everything in this list is now closed.** Items 3 and 5 were fixed, items 2
and 4 decided in ADR-0006 and ADR-0007, item 6 recorded as a known limitation,
and item 1 — the propagation re-run — is done. What is left is review of the
nine open target-repo PRs, plus the two follow-ups named at the end.

### 1. Propagate the accumulated fixes to the target repos — DONE

Every `gwt` fix from Task 14 onward landed *after* the target repos' PRs
merged, so their English output still carried the defects the tool now
prevents. Re-ran the pipeline for all eleven repos from each one's
pre-translation commit, with a gate baseline captured beforehand so
pre-existing repo defects could not be mistaken for regressions.

**The cache was unchanged by every run** — 43,100 segments, all hits, no engine
call, no `DEEPL_API_KEY` needed. This is what "the cache is the artifact"
([ADR-0001](docs/decisions/0001-deduplicated-segment-cache-over-per-file-llm-translation.md))
buys: a full eleven-repo re-translation for free, offline.

| repo | residual CJK (chars) | diff vs merged | PR |
|---|---|---|---|
| go-wind | 1,184 -> 7 | none | — none needed |
| go-wind-bi | 598 -> 4 | none | — none needed |
| go-wind-admin-template | 2,544 -> 0 | 3 files | #2 |
| go-wind-toolkit | 19,662 -> 219 | 7 files | #2 |
| go-wind-plugins | 74,456 -> 4,720 | 26 files | #2 |
| go-wind-ledger | 135,094 -> 6,399 | 119 files | #2 |
| go-wind-uba | 156,574 -> 3,293 | 131 files | #2 |
| go-wind-shop | 167,117 -> 7,976 | 114 files | #2 |
| go-wind-cms | 221,912 -> 13,363 | 157 files | #2 |
| go-wind-admin | 215,103 -> 12,306 | 138 files | #2 |
| go-wind-bootstrap | (pilot) | 5 files | #1, force-pushed |

`go-wind` and `go-wind-bi` reproduce their merged output exactly — the fixes
touch nothing in them, so no PR was opened. That is a useful signal, not a
failure.

**Gate verdict across all eleven: no new broken links, no new broken anchors,
no identifier drift.** Every apparent rise in `broken_links` is the *same*
pre-existing broken target now also present in the `README.zh-CN.md` archival
copy the doc move creates by design (ADR-0004) — verified by diffing the
before/after finding lists, not by assuming. Same for the one apparent new
broken anchor in cms: a stale `#三层架构详解` in the *Chinese source*, left over
from that repo's own three-tier-to-two-tier refactor, duplicated into the
archival copy.

**Two real bugs surfaced from the pilot alone** (bugs 20 and 21 above) — both
would have shipped into eleven repos had the sweep gone straight through.

### 2. The plan's actual Task 14 — DECIDED: closed, do not run

Resolved by
[ADR-0006](docs/decisions/0006-close-task-14-bulk-llm-pass.md). Task 14's bulk
LLM re-translation is descoped. Three measurements settled it:

- **Its selection criterion is broken.** Step 1 expects 6,000-9,000 segments
  under 8 characters ("1-2% of the token cost"); the real count is **25,311 of
  43,100 (58.7%)**. ADR-0005's span narrowing deliberately produces short
  segments, so `len(src) < 8` picks the median segment, not a low-context tail.
- **Its write-back is unsafe as specified.** A cache record is
  `{h, src, en, engine}` — no occurrence kind. One English value serves every
  occurrence of a hash, comment and string literal alike. A comment-tuned
  rewrite through `Cache.put` is the bug already fixed once in PR #3/#5
  (`接口客户端` → `APIClient` must survive a `string` splice byte-identical).
- **The defect rate doesn't justify it.** Across 11 repos and 5,171 files,
  layered review found three systematic patterns; two were splice-boundary
  artifacts (tool bugs, not MT errors) and one was a real MT miss fixed with a
  dictionary pin. One MT-quality defect in 43,100 segments.

`dictionary.tsv` pins are the quality mechanism from here on (Rulings #4/#9).
ADR-0006 records two paths worth revisiting if a future review ever *does*
surface a systematic MT problem — restricting a pass to comment-only hashes, or
using an LLM as a reviewer that feeds the dictionary rather than as a translator
that bypasses it — so neither has to be re-derived.

**This supersedes ADR-0005's retained "optional LLM pass over segments under 8
characters."** Item 1 is therefore a plain re-splice, not a subset of a larger
LLM sweep.

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

### 4. Markdown masking — DECIDED, and it surfaced a real bug

Resolved by
[ADR-0007](docs/decisions/0007-markdown-masking-policy-and-derived-target-repair.md).
Measuring the residual honestly (excluding `*.zh-CN.md`/`*.ja-JP.md` variants,
`node_modules`, `vendor`) on go-wind-admin:

| where the residual CJK is | chars |
|---|---:|
| inside fenced code blocks | 13,090 |
| prose, in files `classify.py` deliberately excludes | 7,241 |
| prose, in files `gwt` considers translatable | **585** |

96% is fenced code or a correctly-skipped file. Sampling the remaining 585
chars found four categories, all masked deliberately: fenced code, HTML
comments in issue/PR templates, inline code naming literals the documented code
compares against (translating `"新增"` would make the doc describe behaviour
the code doesn't have), and link/anchor targets.

**Decision: fenced-code CJK is accepted permanently, not deferred.** A reader
seeing Chinese in a tree diagram is visible and harmless; translating a line a
fence meant literally silently corrupts a copy-pasteable command. ADR-0005
already errs in that direction and this keeps it. `residual_cjk` being
non-empty is expected, and its count is not a defect measure.

**But the fourth category was hiding a real defect** — see bug 19 above. A
heading is prose (translated), an anchor is a link target (masked); both correct
alone, broken together, and `broken_doc_links` skips `#` targets so nothing
caught it. Fixed with `repair_anchors` + a `broken_anchors` gate check. The
general rule, now in ADR-0007: **masking a region means the pipeline won't
translate it, not that the region is independent of what the pipeline does
translate.**

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

### 6. `_mask_md` mis-tracks nested fences (known, low priority, NOT blocking)

Found while dogfooding the gate against this repo's own docs. `_mask_md` toggles
fenced-block state on any line starting with ``` — including one *quoted inside*
another fence. The plan file has a Python test fixture whose string contains
`"```markdown\n"`, which flips the masker off mid-block and leaks the example
links that follow:

```
broken_doc_links('.') -> [('docs/superpowers/plans/2026-08-14-...md', './README.md'),
                          (... , './README.ja-JP.md')]
```

Both are illustrations inside a code fence, so both are false positives — the
exact failure mode `broken_doc_links` masks code to avoid.

Not fixed here, and not urgent: the gate runs against *target* repos, and this
instance is in this repo's own plan. But a target repo's docs showing markdown
examples inside fences would hit it too, so it's worth a fix if the gate ever
starts crying wolf. Proper handling means tracking fence delimiter *length and
character* (CommonMark: a closing fence must be at least as long as the opener
and use the same character), not a boolean toggle. `broken_anchors` inherits the
same masker and therefore the same limitation.

### Follow-up: single-char CJK between two Latin runs

`// PostgreSQL到Protobuf的类型映射` still comes out as
`// PostgreSQL ToProtobufType Mapping`. Extraction narrows to `到` and
`的类型映射` correctly; `pad_comment_boundary` pads the left boundary because
`PostgreSQL` ends in the known acronym `SQL`, but not the right, because
`Protobuf` is not a known acronym. Better than the merged
`PostgreSQLToProtobufType Mapping`, still wrong.

Fixing it means padding **any** Latin/English boundary in a comment rather than
only known acronyms. That is likely safe — with span narrowing, adjacent Latin
is by definition outside the segment, and identifiers in this corpus never
contain CJK, so `GetUserList获取用户列表` -> `GetUserList Get the user list` is
the desired result. But it is a deliberate widening of a rule whose docstring
currently argues *for* the narrow version, so it needs its own change, its own
tests, and its own review — not a quiet edit during a propagation sweep.

### Follow-up: full-width punctuation in markdown prose

`pad_comment_boundary` is `kind == "comment"` only, so markdown prose keeps
source punctuation: `_examples/ddd/README.md` ends a translated English
sentence with `HTTP API。`. Cosmetic, and out of scope for a comment-focused
rule, but visible in rendered docs.

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
8. **`residual_cjk` can be legitimately non-empty by design, and its count is
   not a defect measure** ([ADR-0007](docs/decisions/0007-markdown-masking-policy-and-derived-target-repair.md)).
   Confirmed sources: (a) language-switcher labels naming each language in its
   own script; (b) CJK inside markdown fenced code blocks — the dominant
   source, masked by design and now permanently accepted; (c) HTML comments
   and inline code spans naming literals the documented code matches on.
   Measured split on go-wind-admin: 96% of the residual is fenced code or a
   file `classify.py` correctly skips.
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
11. **Masking a region means the pipeline won't *translate* it — not that the
    region is independent of what the pipeline does translate**
    ([ADR-0007](docs/decisions/0007-markdown-masking-policy-and-derived-target-repair.md)).
    A heading anchor is derived from heading text; mask the anchor, translate
    the heading, and the link rots silently (bug 19). Known instances, both
    now handled: heading anchors (`quality.repair_anchors`) and relative link
    paths under a file move (`docs_layout`'s link rewriting). Any new masked
    region whose value derives from translatable text needs the same
    treatment plus a gate check — masking alone is not a correctness argument.
12. **An `Occurrence`'s `kind` says what construct a span sits in, not whose
    syntax rules apply to it.** Escaping, quoting, and comment conventions
    are properties of the *language*, so they dispatch on the file suffix
    (`_escape_string` in `splice.py`), not on `kind`. Conflating the two is
    what let `.sql` literals get Go escaping (bug 17). `kind` is still the
    right switch for construct-shaped questions — comment-boundary padding
    genuinely only applies to comments.
13. **A PR whose base branch was retargeted by GitHub after its original
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

**Nine target-repo PRs are open and awaiting review** — that is the only thing
in flight. No dirty worktree, no failing test, no blocked step in this repo.

```bash
cd ~/Documents/GitHub/dhiazfathra/go-wind-translate
git pull --ff-only origin master   # local master goes stale fast; work happens in worktrees
python3 -m pytest -q               # must be 167/167 before touching anything
ruff check .                       # must be clean (scope to tests/ gwt/ if stale
                                   # worktree dirs under .claude/ pollute the run)
```

The pull matters: this repo's local checkout was once stale by five merged
commits, because every slice is built in a worktree and merged on GitHub.
`git log --oneline origin/master` is the truth, not the working copy.

**The open PRs**, all titled `chore(i18n): re-run translation with accumulated
tool fixes`:

| repo | PR |
|---|---|
| go-wind-bootstrap | #1 (the Task 12 pilot, force-pushed — never merged) |
| go-wind-admin-template, go-wind-toolkit, go-wind-plugins, go-wind-ledger | #2 each |
| go-wind-uba, go-wind-shop, go-wind-cms, go-wind-admin | #2 each |

Reviewing them: the diffs are large (up to 157 files) but repetitive — almost
every line is a boundary-space insertion or an anchor fragment rewrite. Spot-check
a few of each shape rather than reading all of it, and lean on the gate result
recorded in item 1, which was taken against a pre-translation baseline.

**Everything in "What's left" is closed.** Items 3 and 5 were fixed, items 2 and
4 decided in ADR-0006 and ADR-0007, item 6 recorded as a known limitation, item 1
executed. Do not reopen a closed item without a superseding ADR — the
measurements behind each decision are recorded there so they don't have to be
re-derived.

**The two named follow-ups are the only new work on the table**, and both widen
an existing rule deliberately, so both want their own change and review: padding
any Latin boundary in a comment rather than only known acronyms, and full-width
punctuation in markdown prose.

**Standing rules that still apply** (see CLAUDE.md for the full set):

- Fix bugs in `gwt`, never by hand-editing a target repo — Ruling #10 carves
  out only the narrow "revert an already-fixed-in-tool mistranslation" case.
- **Pilot a sweep on one small repo before running it across all eleven.** The
  propagation pass found two real bugs (20, 21) in the pilot alone, both of
  which would otherwise have shipped everywhere at once.
- `python3 -m pytest` green before any commit.
- `cache/segments.jsonl` is the artifact — committed, never regenerated,
  never gitignored ([ADR-0001](docs/decisions/0001-deduplicated-segment-cache-over-per-file-llm-translation.md)).
  A full eleven-repo re-run needed zero engine calls, which is the whole point.
- Confirm with the user before any push or PR against a target `go-wind*`
  repo. Work inside this repo doesn't need that confirmation.
- Work in a worktree (`superpowers:using-git-worktrees`) off fresh `master`,
  one slice per PR. Commit before `ExitWorktree` — `discard_changes: true`
  discards uncommitted working-tree edits along with unmerged commits.
- Verify a PR body survived `no-mistakes` **programmatically, at the byte
  level**. It replaced the body on 3 of 4 runs, and `diff` in this shell is
  wrapped by `rtk` and rendered a false all-clear on one of them. Assert on
  several distinctive substrings, not one — a single marker can survive in the
  pipeline's own echoed intent text and give a false pass.
