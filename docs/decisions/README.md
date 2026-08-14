# Architecture Decision Records

Decisions behind the `go-wind*` zh→en translation effort. Numbering is
sequential and per-repo, matching the convention used by the `go-admin*` family
(`docs/decisions/NNNN-title.md`).

Old ADRs are never deleted. When a decision changes, a new ADR supersedes it and
references it explicitly.

| # | Decision | Status |
|---|---|---|
| [0001](0001-deduplicated-segment-cache-over-per-file-llm-translation.md) | Deduplicate segments and cache them, rather than translating files with an LLM | Accepted |
| [0002](0002-translate-sources-regenerate-derived-artifacts.md) | Translate generator inputs, regenerate their outputs | Accepted |
| [0003](0003-deepl-free-with-chained-engine-fallback.md) | DeepL Free as the primary engine, behind a chained fallback | Accepted |
| [0004](0004-english-default-doc-layout.md) | English-default docs with Chinese preserved as a selectable variant | Accepted |
| [0005](0005-ast-extraction-with-cjk-span-narrowing.md) | Extract with an AST, narrow spans to the Chinese run, mask what remains | Accepted |
| [0006](0006-close-task-14-bulk-llm-pass.md) | Close Task 14's bulk LLM pass; pin quality misses in the dictionary instead | Accepted |
| [0007](0007-markdown-masking-policy-and-derived-target-repair.md) | Keep markdown masking as-is, but repair targets derived from translated text | Accepted |

## Reading order

ADR-0001 is the load-bearing decision — everything else follows from choosing a
deduplicated cache over per-file LLM translation. ADR-0002 shrinks the corpus,
ADR-0003 picks what does the translating, ADR-0005 makes it safe to apply to
code, and ADR-0004 covers the documentation layout specifically.

ADR-0006 and ADR-0007 close out the quality questions the fan-out left open, and
both are best read after ADR-0005 since both turn on its consequences. ADR-0006
supersedes ADR-0005's retained "optional LLM pass" and explains why span
narrowing makes that pass's own selection criterion meaningless. ADR-0007 keeps
ADR-0005's masking rules while fixing the one place where masking a region and
translating its source drifted apart.
