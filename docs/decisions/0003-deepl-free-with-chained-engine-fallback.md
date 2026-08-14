# ADR-0003: DeepL Free as the primary engine, behind a chained fallback

## Status

Accepted.

## Date

2026-08-14

## Context

With deduplication in place ([ADR-0001](0001-deduplicated-segment-cache-over-per-file-llm-translation.md))
and generated files excluded ([ADR-0002](0002-translate-sources-regenerate-derived-artifacts.md)),
the payload that actually needs translating is roughly **420–480k unique
characters**. That number determines which engines are viable.

### What the candidates cost at this volume

| Engine | Free allowance | Cost after | Cost for ~450k unique chars |
|---|---|---|---|
| DeepL Free | 500k chars/month | n/a (hard stop) | **$0** |
| Google Cloud Translation v3 | 500k chars/month | $20/M | **$0** |
| Argos / OPUS-MT, local | unlimited | none | **$0** |
| LLM inference, per segment | none | per-token | ~300k tokens if scoped |
| LLM inference, per file | none | per-token | 12–20M in + 12–20M out |

Three of the four are free at this volume. The decision is therefore about
**quality and operational risk**, not price.

### Quality ordering, zh→en technical prose

DeepL is the strongest general-purpose zh→en engine for this material. Google
Cloud Translation v3 is close, and has first-class glossary support (a `Glossary`
resource uploaded as TSV) which DeepL matches via `ignore_tags`. Argos/OPUS-MT
runs entirely offline and is noticeably weaker, particularly on terse fragments,
but has no quota and no network dependency at all.

An LLM beats all of them on short, context-starved fragments and on prose that
needs restructuring rather than sentence mapping — but at a cost that only makes
sense when scoped to those cases specifically.

### The high-frequency tail is trivially cheap

Counting repeated CJK-bearing lines across the corpus:

```bash
rg '[一-鿿]' go-wind* -g '!.git' --no-filename -N \
  | sed 's/^[[:space:]]*//' | sort | uniq -c | sort -rn | head -400
```

The top few hundred are `ent` field comments and CRUD boilerplate — `创建`,
`更新`, `删除`, `查询列表`, `创建时间` — repeated across every schema in every
repo. These need no translation engine at all; a hand-curated TSV resolves them
with zero network calls, and resolving them first shrinks whatever runs next.

## Decision

**Chain engines in ascending order of cost, and stop at the first one that
resolves each segment.**

```
dictionary (local TSV, $0, instant)
  → DeepL Free  (500k/month, best quality)
    → Argos     (offline, unlimited, weaker)
```

All engines implement one protocol:

```python
class Engine(Protocol):
    name: str
    def translate(self, texts: list[str]) -> list[str]:
        """One output per input. Empty string means 'no translation'."""
```

Returning `""` for a miss is what makes chaining work: the orchestrator removes
resolved segments from the pending set after each engine, so a segment the
dictionary handles is never sent to DeepL, and a segment DeepL handles is never
sent to Argos. This is asserted directly by
`test_translate_chains_engines_and_stops_at_first_hit`.

DeepL is called with `tag_handling=xml` and `ignore_tags=["x"]`, which is how
identifier preservation is enforced (see
[ADR-0005](0005-ast-extraction-with-cjk-span-narrowing.md)).

The `engine` field is recorded on every cache entry, so it is always possible to
tell which segments came from which source and re-do a subset later.

## Alternatives Considered

### Google Cloud Translation v3 as primary

- Pros: equivalent quality; explicit `Glossary` resource; no hard stop at the
  free-tier boundary — it just starts billing at $20/M, so a run never blocks.
- Cons: requires a GCP project, billing account, and service-account
  credentials. DeepL Free needs an email address and no card.
- **Rejected as primary, retained as a documented fallback.** It is one file
  behind the `Engine` protocol if DeepL's quota ever proves insufficient. The
  cache and splicer need no changes to accommodate it.

### Argos / OPUS-MT as primary

- Pros: $0 forever, no quota, no network, nothing leaves the machine — the right
  choice if the code could not be sent to a third party.
- Cons: measurably weaker output, especially on the short fragments that make up
  much of a comment corpus.
- **Rejected as primary, retained as the quota fallback.** These are private
  repos but not sensitive ones, so the confidentiality argument does not
  outweigh the quality gap. If that assessment changes, switching is a one-flag
  change: `gwt run <repo> --engine argos`.

### LLM for the whole corpus

- Pros: best quality everywhere; no glossary or masking machinery needed.
- Cons: 12–20M input plus 12–20M output tokens; and
  [ADR-0001](0001-deduplicated-segment-cache-over-per-file-llm-translation.md)
  documents that this approach did not converge when it was actually attempted.
- **Rejected**, except as a scoped quality pass over the ~6–9k segments shorter
  than 8 characters, where MT is genuinely context-starved. That subset is
  roughly 1–2% of the whole-corpus token cost.

### Single engine, no chain

- Pros: simpler orchestration; one code path.
- Cons: sends thousands of `创建时间`-class segments to a metered API for no
  benefit; leaves no graceful path when quota runs out mid-fan-out.
- **Rejected:** the chain is about 15 lines and removes both problems.

## Consequences

- **Translation cost is $0** at the measured volume, with no card on file.
- **Quota is a real operational constraint, not a theoretical one.** 450k against
  a 500k monthly ceiling has little headroom. The plan checks
  `DeepLEngine.usage()` before the four largest repos and switches to Argos if
  usage exceeds ~70%. Because the cache is permanent, a mid-fan-out engine
  switch costs nothing already translated.
- **Fan-out order matters.** Repos run smallest-first so the cache is warm before
  the expensive repos run. The five large repos share a scaffold, so the last
  ones should see above 50% cache hits.
- **Mixed-provenance output.** A single file may contain dictionary, DeepL, and
  Argos output. The `engine` field makes this auditable, and re-running a subset
  through a better engine is an edit to the cache plus a re-splice.
- **The dictionary needs seeding**, which is the one place an LLM is worth
  spending before the main run: ~400 short strings in a single batch. Expected to
  resolve 15–35% of unique segments at zero API cost.
- **Adding a fourth engine is a new file and a registry line.** Nothing else in
  the pipeline is aware of which engine produced a translation.
