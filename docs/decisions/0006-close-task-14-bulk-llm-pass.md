# ADR-0006: Close Task 14's bulk LLM pass; pin quality misses in the dictionary instead

## Status

Accepted. Supersedes the final consequence of
[ADR-0005](0005-ast-extraction-with-cjk-span-narrowing.md), which retained "a
scoped LLM pass over segments under 8 characters" as an optional final step.

## Date

2026-08-14

## Context

The [implementation plan](../superpowers/plans/2026-08-14-go-wind-zh-en-translation.md)'s
Task 14 specifies an optional quality pass: select every cached segment whose
source is under 8 characters, re-translate those in batches of 100 through an
LLM prompted for "concise English suitable for a code comment", write the
results back with `Cache.put(h, src, en, "llm")`, then re-splice and re-verify
all eleven repos.

It has never been run. Three things measured against the finished corpus argue
it should not be.

### The selection criterion doesn't select a tail — it selects the majority

The plan expects "on the order of 6,000–9,000 segments — roughly 1–2% of the
token cost of translating the files themselves." Actual count against the
committed cache:

| | count | share |
|---|---:|---:|
| Total cached segments | 43,100 | |
| Source under 8 characters | **25,311** | **58.7%** |

The estimate is off by 3-4×, and not by accident. ADR-0005 chose to narrow
every span to its CJK run precisely so an identifier adjacent to Chinese can
never reach a translation engine, and it recorded the consequence: "Narrowing
to CJK runs produces many small segments rather than few large ones." Short
segments are not a low-context minority produced by sloppy extraction; they are
the *designed output* of the safety mechanism. `len(src) < 8` therefore
describes the median segment, not a tail worth special handling.

The plan's criterion and its own extraction strategy are in conflict. One of
the two has to give, and it is not going to be ADR-0005.

### The cache has no `kind` dimension, so a comment-tuned rewrite is unsafe

A cache record is exactly `{h, src, en, engine}`. There is no occurrence kind.
One English string per source hash serves *every* occurrence of that text —
comment, interpreted string literal, raw string literal alike.

This hazard has already been hit once and fixed. The CodeRabbit review on PR #3
(shipped as #5) caught `fix_spacing()` being applied in `cmd_translate` before
caching: a comment-readability fix, written into a value also spliced into
string literals, where the same Chinese term is a real identifier. The
regression test that now guards it is concrete — `接口客户端` caches as
`APIClient`, and both the `string` and `raw_string` splice paths must return it
byte-identical.

Task 14 Step 2 is that same bug at corpus scale, and by construction rather
than by oversight: a prompt that says "suitable for a code comment" optimizes
for one kind and writes for all of them. Measured exposure in the current
cache — 1,968 short segments already translate to a single bare token, and
seven of those are identifier-shaped:

```
鸿蒙   -> HarmonyOS      访问地址 -> URL
抖音   -> TikTok         问题解答 -> FAQ
钉钉   -> DingTalk       行      -> OK
微信   -> WeChat
```

Each is correct as it stands. An LLM asked to make short segments read better
as comment prose is more likely to expand these than to leave them alone.

### The observed MT defect rate does not justify the churn

Across eleven repos and 5,171 files, a review pass — CodeRabbit on every PR,
plus reviewer subagents on the four large repos, plus manual diff review on the
pilot — surfaced exactly three systematic quality patterns:

1. Acronyms glued to translated words (`UserIDInvalid`). **Not an MT error** —
   a splice-boundary artifact, i.e. a bug in this tool. Fixed in `gwt/quality.py`.
2. Full-width punctuation glued to translated words (`(light/dark/auto）`).
   **Not an MT error** — same root cause, same fix.
3. `180天` returned as `180Tian`. A genuine MT miss. Fixed with one line in
   `dictionary.tsv`.

One MT-quality defect in 43,100 segments, found by layered review. Re-writing
58.7% of an already-reviewed, already-merged corpus to chase that rate is not a
favourable trade, and the re-splice would put a fresh large diff in front of
reviewers across eleven repos with no measured defect for them to look for.

## Decision

**Do not run the bulk LLM pass. Handle quality misses as they are found, with
exact-match `dictionary.tsv` pins.**

Task 14 is closed as descoped. The three targeted fixes already shipped (two
tool bugs, one dictionary pin) are what that task's budget bought, and they
were driven by observed defects rather than by a blanket re-translation.

`dictionary.tsv` is the mechanism because it is everything the bulk pass is
not: checked before any engine and authoritative on an exact match, one
reviewable line per decision, deterministic, offline, permanent, and equally
able to express an identity pin ("leave this exactly as it is") as a
correction. Rulings #4 and #9 in `HANDOFF.md` already establish it as the right
tool for "translate this exact segment to exactly this."

## Alternatives Considered

### Run Task 14 exactly as written

- Pros: follows the plan; the plan's step 1 script works as-is; token cost is
  genuinely modest.
- Cons: rewrites 58.7% of the corpus rather than the intended 1-2%; writes
  comment-tuned values into a cache shared with string-literal occurrences,
  which is a known-and-already-fixed bug class; generates a large re-splice
  diff across eleven merged repos against a measured defect rate of one.
- **Rejected.** The cost is real, the benefit is unmeasured, and the mechanism
  is unsafe in a way the project has already been burned by once.

### Run it, but only over hashes that appear *exclusively* in comment occurrences

- Pros: sidesteps the shared-cache hazard entirely — if no `string`-kind
  occurrence shares the hash, a comment-tuned value can't corrupt one. The data
  needed is available at translate time, since `Segment` does carry `kind`.
- Cons: needs a corpus-wide occurrence census as a precondition, and that
  census is invalidated by any later extraction change. It also still buys
  nothing measurable — the safety objection falls away but the "one defect in
  43,100" objection does not.
- **Rejected on cost/benefit, not on feasibility.** This is the design to
  revisit if a future review ever does surface a systematic MT-quality problem.
  Recorded here so it doesn't have to be re-derived.

### Give the cache a `kind` dimension, then re-translate per kind

- Pros: the structurally correct fix if per-kind translations are ever genuinely
  needed.
- Cons: `cache/segments.jsonl` is a permanent committed artifact
  ([ADR-0001](0001-deduplicated-segment-cache-over-per-file-llm-translation.md))
  and 43,100 records long; changing its schema is a migration, not an edit. It
  would also lower the dedup hit rate that makes the cache cheap, since the same
  text would be translated once per kind.
- **Rejected** as far more machinery than the problem justifies.

### Use an LLM as a reviewer over the corpus rather than as a translator

- Pros: keeps the cache untouched, so there is no shared-value hazard and no
  re-splice; produces a list of suspect segments a human can turn into
  dictionary pins; scales the layered review that actually found all three real
  patterns.
- Cons: still a large token spend, and the three patterns it would have been
  looking for have already been found and fixed by the review passes that ran.
- **Not rejected — deferred.** This is the shape a genuine future quality effort
  should take: it feeds the dictionary mechanism instead of bypassing it. Worth
  a new ADR if the corpus grows or new repos join.

## Consequences

- **`dictionary.tsv` becomes the sole quality-correction mechanism**, and is
  expected to grow one line at a time as problems are observed. It is at 47
  entries. Growth is a healthy signal, not scope creep.
- **The plan's Task 14 section is now historical.** It stays in place — the plan
  is a record of what was decided when — but Step 1's estimate is wrong by
  3-4× and Step 2's write-back is unsafe. Anyone reading it needs this ADR
  first, so the plan links here.
- **A quality regression now depends on review catching it**, since nothing
  sweeps the corpus proactively. That matched reality for Tasks 12-13, where
  layered review found every pattern that was found at all. If a future run
  skips the reviewer-subagent pass, this decision gets weaker and should be
  revisited.
- **ADR-0005's "optional final step" consequence no longer holds.** Span
  narrowing still produces short segments and still costs translation context;
  that cost is now simply accepted rather than earmarked for a later pass.
- **Short segments stay short in the cache forever.** If a future decision does
  want more context per segment, that is an extraction change (ADR-0005's
  territory) with a full re-translation behind it — not a post-hoc cache
  rewrite.
