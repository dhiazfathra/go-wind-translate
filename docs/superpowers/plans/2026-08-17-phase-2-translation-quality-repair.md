# Phase 2 — translation quality repair

## Why there is a Phase 2

Phase 1 (tasks 1-14) converged on coverage: residual Chinese fell from ~220k characters
per repo to ~12k, at zero engine cost, with no identifier drift. What it did not measure
was whether the English it produced was *right*.

A review pass over the latest PR in each of the eleven `go-wind*` repos
(`ZH_EN_TRANSLATION_REVIEW.md`, one per repo) found roughly 100 concrete defects. They
are not evenly spread — they cluster into three causes, and only the first is worth
fixing mechanically.

### Cause 1 — span narrowing strips the context the engine needed

[ADR-0005](../../decisions/0005-ast-extraction-with-cjk-span-narrowing.md) narrows a
segment to the Chinese run so identifiers never reach the engine. That is the right
call for safety and it is why nothing drifted. But it also hands DeepL `角色` with no
surrounding code, and DeepL answers "Character" — correct for a novel, wrong for RBAC.
The same mechanism produced 桶 → "Barrel", 会话 → "Conversation", 套餐 → "Set Meals",
表头 → "watch face", 天 → "Sky", 驱逐 → "Deportation".

These are **wrong terms, not awkward phrasing**, they are systematic (one bad segment
is reused everywhere its hash appears), and each has exactly one right answer in this
domain. That makes them mechanically fixable.

### Cause 2 — machine-translation garbling

Fragments like `"Yes API The sole source of"` or `"Ku Ju-ming"` are not a wrong term
substituted for a right one; the sentence structure is gone. There is no safe
find-and-replace for these. They are recorded per repo and left for a human or an LLM
pass with full file context.

### Cause 3 — cosmetic MT style

Capitalised mid-sentence fragments, run-together words. Meaning survives.
Out of scope, as in Phase 1's review.

## Decision

Fix cause 1 only, and fix it in the cache — the cache is the artifact
([ADR-0001](../../decisions/0001-deduplicated-segment-cache-over-per-file-llm-translation.md)),
so a repair there is inherited by every future run of every repo. Causes 2 and 3 stay
documented, not patched.

This deliberately does **not** re-open [ADR-0006](../../decisions/0006-close-task-14-bulk-llm-pass.md).
That ADR closed a bulk LLM pass selected by `len(src) < 8`, which matched 58.7% of the
corpus and wrote back engine output with no `kind` dimension. Phase 2's selector is a
closed list of term triples, review-derived, matching 396 of 43,100 records — under 1%.

## Mechanism

`corrections.tsv` holds `zh_term <TAB> wrong_en <TAB> correct_en`. A cache record is
rewritten only when its `src` contains `zh_term` **and** its `en` contains `wrong_en` at
a word boundary. The zh gate is what keeps 字符 → "Character encoding" intact while
fixing 角色 → "Character".

Terms that are only wrong in isolation get an exact-segment gate, written `=词`:
`执行` is "Enforcement" as a Code-of-Conduct heading and "Execute" in every other
sentence, so a substring rule would corrupt more than it repairs. Same for `固定`,
`目录`, `覆盖`.

`gwt/repair.py` rewrites the cache and emits the before/after pairs.
`gwt/propagate.py` applies those pairs to a target repo. It replaces literal English
rather than re-splicing, because `work/<repo>/occurrences.jsonl` records byte spans
against the *Chinese* tree — on an already-translated branch those spans no longer
exist. The spliced English is the only surviving handle. Pairs whose `before` is
shorter than 6 characters are skipped rather than risked (4 of 396); they collide with
prose the pipeline never wrote.

## Tasks

1. **Corrections table** — derive triples from the eleven review documents. *Done.*
2. **`gwt.repair`** — zh-gated term rewrite over the cache, with exact-segment support,
   under test. *Done — 5 tests.*
3. **`gwt.propagate`** — literal before/after application into a target repo, skipping
   generated / runtime-i18n / `zh-CN` paths. *Done.*
4. **Repair the cache** — 396 of 43,100 records rewritten, `engine` stamped
   `phase2-repair`. *Done.*
5. **Fan out to eleven repos** — apply the pairs on each repo's existing
   `zh-en-translation-review` branch, so the corrections land in the PR that reported
   them rather than opening a third one. Verify no runtime-i18n or generated file moved.
6. **Record what was not fixed** — each repo's `ZH_EN_TRANSLATION_REVIEW.md` gains a
   Phase 2 section separating what this pass repaired from what still needs a human.

## Verification

- `python3 -m pytest` green before any repo is touched.
- Per repo: `git diff --stat` must show no path under `gen/`, `generated/`, `locales/`,
  `messages/`, `i18n/`, `*.pb.*`, `*zh-CN*`.
- Per repo: no change to any identifier — the pairs only rewrite prose the splicer
  itself wrote.

## Consequences

The cache now carries a third engine value, `phase2-repair`, alongside `dictionary`,
`deepl` and `argos`. A future re-run inherits the corrected English for free, so the
next `go-wind*` repo translated will never see "Character" for 角色.

The corrections table is append-only in spirit: every future review finding that is a
term substitution belongs here rather than in a target repo, per the standing rule that
bugs are fixed in the tool.
