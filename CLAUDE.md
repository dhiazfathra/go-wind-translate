# CLAUDE.md

Conventions for agents working in this repo. Read [`docs/decisions/`](docs/decisions/README.md) before proposing changes to the pipeline — most design questions have already been decided there with evidence.

## What this repo is

Tooling (`gwt`) that translates Chinese to English across eleven sibling `go-wind*` repos. This repo holds the tool, the plan, and the segment cache. It does **not** hold the translated code — that lands in the target repos on `chore/i18n-en-default` branches.

Target repos live at `~/Documents/GitHub/dhiazfathra/go-wind*`, siblings of this one.

## Non-negotiables

These are decided. Do not re-litigate them in an implementation without writing a superseding ADR first.

- **The cache is the artifact.** `cache/segments.jsonl` is committed, never gitignored. Deleting or regenerating it throws away the only thing that is expensive to reproduce. ([ADR-0001](docs/decisions/0001-deduplicated-segment-cache-over-per-file-llm-translation.md))
- **Never translate generated files.** Translate `.proto` and `ent/schema/*.go`, then run the target repo's `make gen`. Anything under `gen/`, `generated/`, `ent/` (except `ent/schema/`), `*.pb.*`, `migrate/schema.go`, `wire_gen.go` is off limits. ([ADR-0002](docs/decisions/0002-translate-sources-regenerate-derived-artifacts.md))
- **Never touch runtime i18n.** `locales/`, `messages/`, `langs/`, `i18n/`, `*.arb`, `[locale]/`, `*zh-CN*` are deliberately Chinese. Modifying them is a bug, and the verification gate treats it as one.
- **Never let an identifier reach a translation engine.** Spans narrow to the Chinese run; whatever interleaving remains is masked with `<x>…</x>` and `ignore_tags`. ([ADR-0005](docs/decisions/0005-ast-extraction-with-cjk-span-narrowing.md))
- **Fix bugs in the tool, not in the target repos.** If a run produces bad output in `go-wind-cms`, the fix belongs in `gwt`, followed by `git checkout -- . && git clean -fd` in the target repo and a re-run. Hand-editing the target repo means the next ten repos inherit the bug. Re-runs are free because the cache is warm.

## Working conventions

- **TDD.** The [implementation plan](docs/superpowers/plans/2026-08-14-go-wind-zh-en-translation.md) is written as failing-test-first steps. Follow that order; every task ends with a passing test and a commit.
- **Run the tests before touching any target repo.** `python3 -m pytest` must be green. A splicer bug applied across 5,171 files is expensive to unwind.
- **Byte offsets, never character offsets.** Mixed-width UTF-8 makes character indexing a source of silent corruption.
- **Splice deepest-offset-first.** English is usually longer than Chinese; applying replacements in ascending order invalidates every subsequent offset.
- **Engines return `""` for a miss**, not the input and not `None`. That is what makes the dictionary → DeepL → Argos chain skip already-resolved segments.

## ADRs

New ADRs go in `docs/decisions/NNNN-title.md`, continuing the sequence. Match the existing heading set: `# ADR-NNNN: Title`, then `## Status`, `## Date`, `## Context`, `## Decision`, `## Alternatives Considered`, `## Consequences`.

Do not delete or rewrite an accepted ADR. Write a new one that supersedes it and says so in its `## Status`.

This convention matches the `go-admin*` sibling repos, which also use `docs/decisions/`. Note that some unrelated repos in the same parent directory use `docs/adr/` — that is not the convention here.

## Commits

Conventional commits, imperative summary, body in bullets explaining what and why:

```
<type>(<scope>): <summary>

- what changed
- why
```

Types: `feat` `fix` `refactor` `docs` `test` `chore` `style` `perf`

## Git identity

Commits in this repo must be authored with the email verified on the `dhiazfathra` GitHub account (the global git config default). Do **not** pass an inline `-c user.email=...` override — an earlier commit here was misattributed to a different GitHub account because the work email supplied that way is verified under a different account. GitHub resolves authorship by commit email, not by push credentials.

## Guards

Plain `git push --force` is blocked by a local guard. Use `--force-with-lease`, which is also the safer default.
