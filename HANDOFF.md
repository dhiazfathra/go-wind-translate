# Handoff: zh->en translation tooling — resume at Task 13

## State as of this handoff

- **Master** (`cfe6abf`) has the full `gwt` tooling: Tasks 1-11 of the
  [implementation plan](docs/superpowers/plans/2026-08-14-go-wind-zh-en-translation.md),
  built via `superpowers:subagent-driven-development` and merged in
  [PR #1](https://github.com/dhiazfathra/go-wind-translate/pull/1).
- **Task 12 done** (this worktree, branch `worktree-zh-en-translation-task12`):
  pilot run against `go-wind-bootstrap` with a real `DEEPL_API_KEY`. Found
  and fixed three real bugs in `gwt` (see "Bugs found in Task 12" below).
  104/104 tests passing. `go-wind-bootstrap` committed locally on
  `chore/i18n-en-default` — **not yet pushed/PR'd**, pending confirmation
  (project convention: confirm before push/PR against target repos).
  `cache/segments.jsonl` committed here with bootstrap's 904 segments.
- The prior working worktree (`.claude/worktrees/zh-en-translation`) has been
  removed — its content is fully in master (squash-merged), nothing was lost.
- The SDD ledger for Tasks 1-11 (`.superpowers/sdd/2026-08-14-go-wind-zh-en-translation/progress.md`)
  lived in that worktree and was discarded with it; the rulings it recorded
  are captured below so they aren't lost.

## Bugs found in Task 12 (fixed in this worktree's commits)

1. `docs_layout.apply_moves` archived `README.md` -> `README.zh-CN.md` and
   always recreated `README.md` at the old path for in-place translation —
   but when a real `README_en.md` variant also existed to promote onto
   `README.md`, the recreate collided with `git mv`. Fixed: skip the
   recreate when another move in the batch targets that same path.
2. `classify.EXCLUDE_GLOBS` excluded dot-style README language variants
   (`README.ja.md`) but not underscore-style (`README_ja.md`), so a
   preserved-Japanese README leaked into extraction and crashed
   `splice_repo` once `docs_layout` renamed it away. Fixed: added the
   underscore/uppercase variants.
3. `verify.identifier_drift`'s `_CODE_LINE` heuristic (word followed by
   `:`/`=`/`(`) fires on ordinary markdown prose (e.g. "Direction:`cmd ->
   x`"), not just code. Fixed: scope the diff to non-markdown files.

## What's left (from the plan)

- **Task 12 Step 7** — push `go-wind-bootstrap`'s `chore/i18n-en-default`
  branch and open its PR. Held pending user confirmation (target-repo
  push/PR is explicitly gated, per this file's own prior instruction).
- **Task 13** — fan out to the other 10 `go-wind*` repos, smallest-first.
  Includes a DeepL-quota check before the four large repos, and one
  reviewer-subagent-per-repo for the large diffs.
- **Task 14** (optional) — scoped LLM quality pass over short/prose
  segments MT handles poorly (~1-2% of corpus). DeepL's output on the
  bootstrap pilot is grammatically rough in a few Go doc comments
  (word-for-word phrasing, stray full-width punctuation) — worth
  revisiting here.

Full task text with exact commands: `docs/superpowers/plans/2026-08-14-go-wind-zh-en-translation.md`,
starting at "Task 13: Fan out to the remaining ten repos".

## Rulings carried forward from Tasks 1-11

These were decided during implementation and are load-bearing for anyone
resuming — re-litigating them would just reproduce the same investigation:

1. **`cmd_run` pipeline order is `extract -> docs -> translate -> splice`**,
   not the plan's original `extract -> translate -> splice -> docs`. The
   original order spliced English into `README.md` before the docs-move
   step checked `has_cjk()`, so the Chinese original was never archived to
   `README.zh-CN.md` — a real bug in the plan's own reference code, fixed
   and verified. Don't revert this ordering.
2. **`mask.py`'s identifier patterns use explicit lookarounds
   `(?<![A-Za-z0-9_])...(?![A-Za-z0-9_])`, not `\b`.** Python's `re` treats
   CJK ideographs as `\w`, so `\b` doesn't create a boundary between Chinese
   text and an adjacent identifier with no space (e.g. `GetUserList获取用户列表`).
   This was a live identifier-leak bug, fixed and covered by tests. If any
   future module adds its own regex near a CJK/Latin boundary, check for
   this same trap.
3. **`gwt/verify.py`'s `broken_doc_links` uses its own narrower `_mask_md()`**
   (code/HTML only), not `extract_md._mask` — the latter also blanks link
   targets, which would make link-checking permanently blind. Don't
   "simplify" this by reusing `extract_md._mask`.
4. **`dictionary.tsv` has 41 entries, not the plan's ~400.** Deliberately
   scoped down (one-time optimization, not correctness-critical) — fine to
   grow later but not a blocker.
5. **`cmd_verify`/`run_gate` support an optional baseline** (`--baseline`)
   to suppress pre-existing repo defects (e.g. already-broken doc links)
   so the gate only reports regressions the translation run introduced.
   Used for Task 12: baseline captured before the pilot run, passed back in
   on the "after" check.
6. **`splice_file` skips (doesn't crash on, doesn't overwrite) an occurrence
   whose current file bytes no longer hash-match what was recorded** —
   protects against corruption from a stale `occurrences.jsonl`. If a later
   task sees unexpectedly low splice counts, check for this skip path before
   assuming the extractor missed something.
7. **`cmd_translate` raises if an engine returns a different number of
   results than inputs**, before writing anything to the cache — a length
   mismatch would otherwise silently corrupt `cache/segments.jsonl`
   (permanent, committed, never regenerated).
8. **`residual_cjk` can be legitimately non-empty by design, not just as an
   accepted gap.** Two sources recur across repos: (a) the language
   switcher's own labels (`简体中文`, `日本語`) name each language in its
   native script — that's the point, not a miss; (b) `extract_md.py`
   deliberately masks fenced code blocks (`_SKIP` regexes), so CJK
   comments *inside* markdown code fences are never extracted or
   translated — a documented scope limit (ADR-0005's "prose only, code and
   URLs masked out"), not a bug to chase. Confirmed on `go-wind-bootstrap`:
   both of its residual_cjk entries are exactly these two cases.

## How to resume

1. Get a `DEEPL_API_KEY` and confirm it works: `export DEEPL_API_KEY='<key>:fx'`.
2. Start a fresh worktree (`superpowers:using-git-worktrees`) off latest
   `master` — this handoff assumes Task 12's branch has been merged there
   first (`superpowers:finishing-a-development-branch`).
3. Run `superpowers:subagent-driven-development` (or
   `superpowers:executing-plans`) against
   `docs/superpowers/plans/2026-08-14-go-wind-zh-en-translation.md`,
   starting at **Task 13**. Tasks 1-12 are done; don't re-dispatch them.
4. Task 13 pushes branches and opens PRs against the **target** `go-wind*`
   repos (siblings of this one), not this one — confirm with the user
   before any push/PR against those, same as was done for PR #1 here and
   held for Task 12 Step 7.
