# ADR-0005: Extract with an AST, narrow spans to the Chinese run, mask what remains

## Status

Accepted.

## Date

2026-08-14

## Context

The failure mode that ruins a bulk code translation is not a bad translation —
it is a *good* translation applied to the wrong bytes. A machine translation
engine handed this Go comment:

```go
// GetUserList 获取用户列表
```

will cheerfully return:

```go
// Get User List get the user list
```

`GetUserList` is a symbol. Renaming it inside a doc comment breaks the Go
convention that a doc comment begins with the identifier it documents, makes the
comment wrong, and — if the same thing happens inside a string literal used as a
map key or an i18n lookup — breaks the program.

The corpus makes this a high-volume risk rather than an edge case. Splitting
CJK-bearing lines by whether they start with a comment marker:

| Type | Comment lines | Other lines |
|---|---:|---:|
| ts / vue / tsx | 29,394 | 4,894 |
| go | 28,418 | 25,242 |
| proto | 5,934 | 15,912 |

Go is only ~53% comments. The remainder is error message strings, `ent` schema
`.Comment()` calls, and struct-tag descriptions — all places where an identifier
or a format verb sits adjacent to Chinese. Proto is mostly *trailing* comments
and `gnostic`/`openapi` option strings, where a regex over lines cannot reliably
tell a comment from a field definition.

There are two separable problems:

1. **Finding the translatable regions** — which bytes are comment or string, and
   which are code. This needs syntax awareness.
2. **Protecting code-like tokens that sit inside those regions** — identifiers,
   URLs, printf verbs, backticked code. This needs token-level masking.

## Decision

**Solve both, in that order: parse with tree-sitter to find regions, narrow each
region to its Chinese runs, then mask code-like tokens in what remains before
sending it to any engine.**

### Layer 1 — tree-sitter finds the regions

One extractor, one grammar set (`tree-sitter-language-pack`), a per-language map
of node type to segment kind:

```python
NODE_KINDS = {
    "go": {"comment": "comment",
           "interpreted_string_literal": "string",
           "raw_string_literal": "string"},
    "typescript": {"comment": "comment", "string_fragment": "string", ...},
    "proto": {"comment": "comment", "string": "string"},
    ...
}
```

A language whose grammar is unavailable degrades to a line-based comment
fallback rather than failing the run. `.vue`, `.dart`, and `.proto` degrade
acceptably because their Chinese is overwhelmingly in `//`-style comments.

Markdown is the deliberate exception: it gets a regex extractor that blanks
fenced code, inline code, link targets, raw HTML, URLs, and frontmatter. An AST
would provide exactly that and nothing more, for considerably more machinery.

### Layer 2 — spans narrow to the Chinese run

An occurrence's byte span covers **only the CJK run**, not the enclosing node.
For `// GetUserList 获取用户列表` the span covers `获取用户列表` alone.
`GetUserList` is never part of a segment, is never sent anywhere, and cannot be
altered by anything the engine returns.

This is the primary defence. It is asserted directly:

```python
def test_identifier_prefix_is_not_part_of_segment():
    segs, _ = extract_file(FIX, "sample.go")
    assert "用户仓储实现" in _texts(segs)
    assert not any("UserRepo" in s.src for s in segs)
```

### Layer 3 — masking protects what is left

Chinese and code do interleave inside a single run — `创建用户失败: %w`,
`已处理 {count} 条`, `基于 kratos 框架`. Before sending, each such token is
wrapped:

```
创建用户失败: <x>%w</x>
```

and DeepL is called with `tag_handling=xml`, `ignore_tags=["x"]`, which passes
wrapped content through byte-identical. The wrapper is stripped on return.

Protected patterns, in priority order: backticked code, URLs, printf verbs,
`{placeholder}` and `${placeholder}`, glossary terms, call sites (`name(`),
camelCase, PascalCase, snake_case, dotted paths. The glossary holds ~27
framework terms (`kratos`, `ent`, `Casbin`, `Zanzibar`, `Vben`, `Taro`, …) that
are lowercase enough to read as ordinary prose without it.

Ordinary English inside a Chinese comment is deliberately *not* masked —
`这是 a simple test 的说明` should translate normally.

### Layer 4 — the gate catches what slips

`gwt.verify.identifier_drift` inspects `git diff -U0` and reports any changed
line that is neither a comment nor Chinese-bearing yet contains an
assignment/call/declaration pattern. A pure comment translation produces no such
line. The pilot repo additionally gets a manual diff review before the fan-out.

## Alternatives Considered

### Regex over lines, no parser

- Pros: no dependency; trivial; fast.
- Cons: cannot distinguish a proto trailing comment from a field definition,
  cannot find multi-line block comments reliably, cannot tell a Go raw string
  from a comment containing `//`. With proto at 15,912 non-comment CJK lines,
  the ambiguous fraction is large.
- **Rejected as the primary mechanism, retained as the per-language fallback**
  where no grammar is available.

### One extractor per language, hand-written

- Pros: `go/parser` with `ParseComments` gives exact `token.Pos`; the TypeScript
  compiler API gives precise comment ranges; both are more faithful than a
  generic grammar.
- Cons: seven languages, seven toolchains, seven span models to reconcile —
  Go, TypeScript, Vue SFC, proto, Dart, C#, Markdown.
- **Rejected:** one tree-sitter pass covers all of them with a single span
  model. The grammars are an already-solved dependency, not new work.

### Whole-node spans plus masking, without narrowing

- Pros: simpler extraction; one span per comment node.
- Cons: makes masking the *only* line of defence for identifiers. A single
  masking-regex gap then rewrites a symbol somewhere in 5,171 files, and the
  diff is large enough that review will not reliably catch it.
- **Rejected:** narrowing means the common case never reaches the masking layer
  at all. Defence in depth is cheap here.

### Translate only comments, skip string literals entirely

- Pros: eliminates the riskiest category outright; no i18n-key hazard.
- Cons: leaves 25,242 CJK lines in Go alone — error messages users actually see,
  and `ent` `.Comment()` calls that become generated documentation.
- **Rejected:** the exclusion globs already remove genuine i18n resources
  ([ADR-0004](0004-english-default-doc-layout.md)), so what remains in strings is
  mostly user-visible text that should be translated.

## Consequences

- **Four independent layers must all fail for an identifier to be corrupted.**
  Span narrowing handles the common case, masking handles interleaving, the
  gate catches the rest, and the pilot review catches what the gate misses.
- **`tree-sitter-language-pack` is a hard dependency**, verified for grammar
  availability as an explicit first step before anything is built on it.
  Languages that report missing are demoted to the fallback and recorded.
- **The masking heuristic will occasionally over-protect** — an English word that
  happens to be camelCase inside prose stays untranslated. This is the correct
  direction to err: an untranslated token is visible and fixable; a renamed
  symbol is a silent bug.
- **Segments are short.** Narrowing to CJK runs produces many small segments
  rather than few large ones, which raises the dedup hit rate (identical short
  comments collapse) but costs some translation context. This is the specific
  reason a scoped LLM pass over segments under 8 characters is retained as an
  optional final step.
- **Byte offsets, not character offsets, throughout.** Mixed-width UTF-8 makes
  character indexing a source of subtle corruption. Splicing applies replacements
  deepest-offset-first so earlier spans stay valid as English (usually longer
  than Chinese) shifts everything after it.
- **Extraction is re-runnable and side-effect free**, so a fix to `NODE_KINDS` or
  to the masking patterns is applied by resetting the repo and re-running. With
  the cache already warm, that costs nothing.
