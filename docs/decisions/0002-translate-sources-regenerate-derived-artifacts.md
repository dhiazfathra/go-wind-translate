# ADR-0002: Translate generator inputs, regenerate their outputs

## Status

Accepted.

## Date

2026-08-14

## Context

A large share of the Chinese in these repos lives in files that no human wrote.
The `go-wind` backends are `go-kratos` services that generate code from `.proto`
definitions and from `ent` schema files; the frontends generate typed API clients
from the same protos.

Measured across all eleven repos:

| Category | CJK chars | Files |
|---|---:|---:|
| Generated artifacts | 329,635 | 1,590 |
| Everything else (real corpus) | 969,853 | 5,171 |
| **Total** | **1,373,775** | **7,023** |

Generated files are **24% of the corpus**.

The generated set is identifiable by path and suffix: `**/gen/**`,
`**/generated/**`, `*.pb.go`, `*.pb.ts`, `*.pb.dart`, `**/migrate/schema.go`,
`**/wire_gen.go`, and everything under `**/ent/**`.

Two observations make this decisive rather than merely wasteful:

### The same generated content is duplicated per frontend

`go-wind-admin` ships three admin frontends — React, Vue Element Plus, and
Vue Vben. Each has its own generated client:

```
frontend/admin/react/src/api/generated/admin/service/v1/index.ts        207 CJK lines
frontend/admin/vue-element/src/api/generated/admin/service/v1/index.ts  207 CJK lines
frontend/admin/vue-vben/apps/admin/src/api/generated/.../index.ts       207 CJK lines
```

Identical content, generated from one proto, translated three times under a
naive file-oriented approach.

### Translating generated files is reverted by the next build

`go-wind-cms/backend/Makefile` defines:

```make
gen: ent wire api openapi
```

Any translation applied directly to `backend/api/gen/**` or to
`internal/data/ent/**` is overwritten the next time a developer runs `make gen`.
The translation would silently disappear, and the repo would appear to regress
for no visible reason.

The prior `go-admin-translate` attempt did translate generated files. Its top
residual-Chinese file is `backend/.../ent/migrate/schema.go` at 643 CJK
characters — a file that is regenerated from `ent/schema/`, meaning the effort
spent there was doomed either way.

### One exception matters

`ent/schema/*.go` is **hand-written** — it is the input that `ent` reads, not an
output. Its `.Comment(...)` calls are the origin of the Chinese that appears in
generated ent code. A rule that excludes all of `**/ent/**` would skip the very
source that needs translating.

## Decision

**Never translate generated artifacts. Translate their generator inputs — `.proto`
files and `ent/schema/*.go` — then run each repo's own `make gen` to propagate.**

The classifier encodes this as an exclusion list with one exception:

```python
GENERATED_GLOBS = (
    "*/gen/*", "*/generated/*",
    "*.pb.go", "*.pb.ts", "*.pb.dart", "*_pb2.py",
    "*.g.dart", "*.freezed.dart",
    "*/migrate/schema.go", "*/wire_gen.go",
    "*/ent/*",
)
GENERATED_EXCEPTIONS = ("*/ent/schema/*",)   # hand-written; checked first
```

The pipeline runs `make gen` after splicing and before verification, so the
generated tree is rebuilt from the now-English sources within the same commit.

## Alternatives Considered

### Translate generated files too, for completeness

- Pros: no reliance on `make gen` succeeding; residual-CJK check trivially
  reaches zero; works even if a contributor never regenerates.
- Cons: 329,635 characters of avoidable work; triplicated across frontends;
  silently reverted by the next `make gen`; leaves the proto source Chinese so
  the problem returns on every regeneration.
- **Rejected:** it treats the symptom. The proto comment is the source of truth.

### Translate generated files *and* their sources

- Pros: correct in both states; no dependency on the generator being runnable.
- Cons: pays the 24% anyway; the two copies can drift if a translation is later
  revised in only one place.
- **Rejected:** the generator exists precisely to keep those in sync. Running it
  is cheaper and cannot drift.

### Exclude all of `**/ent/**` with no exception

- Pros: simpler glob list.
- Cons: skips `ent/schema/*.go`, the hand-written origin of every Chinese
  comment in the generated ent code. The English would never reach the generated
  output.
- **Rejected:** verified that `ent/schema/` files carry `.Comment("...")` calls
  with Chinese; e.g. seven such files under
  `go-wind-cms/backend/app/core/service/internal/data/ent/schema/`.

## Consequences

- **The corpus shrinks by 24%** before any translation happens — from 1,373,775
  to 969,853 characters. This is the single largest cost reduction in the plan,
  and it costs one glob list.
- **`make gen` becomes part of the pipeline**, not an afterthought. `gwt run`
  invokes it for any repo with a `backend/Makefile`. Repos without one
  (`go-wind-bootstrap`) simply have nothing to regenerate.
- **A repo whose `make gen` is broken will show residual Chinese** in its
  generated tree after a run. That is the correct signal: it means the
  regeneration step did not happen, and the fix is to repair `make gen`, not to
  hand-translate the output.
- **Reviewers must expect large generated diffs.** A translated proto comment
  produces changes across every generated client. These are legitimate and
  should be regenerated rather than hand-edited during review.
- **Ordering constraint:** splice must complete before `make gen` runs, and
  `make gen` must complete before verification. The CLI enforces this order.
- The exception mechanism (`GENERATED_EXCEPTIONS` checked before
  `GENERATED_GLOBS`) is a small piece of ordering-sensitive logic. It has a
  dedicated test (`test_ent_schema_beats_ent_exclusion`) because getting it
  backwards fails silently — the run would simply translate less.
