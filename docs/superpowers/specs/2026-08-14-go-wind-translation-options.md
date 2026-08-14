# go-wind* zh→en Mass Translation — Execution Options

## Measured baseline (scanned 2026-08-14, 11 repos in `~/Documents/GitHub/dhiazfathra/`)

| Repo | files w/ CJK | dominant types |
|---|---:|---|
| go-wind-admin | 1644 | ts 518, go 419, vue 255, tsx 127, proto 93 |
| go-wind-cms | 1580 | go 518, ts 387, vue 167, proto 128, dart 100 |
| go-wind-ledger | 1128 | go 450, ts 210, vue 145, proto 124, dart 106 |
| go-wind-shop | 1126 | go 479, ts 227, vue 167, proto 119 |
| go-wind-uba | 1061 | go 444, ts 220, vue 155, proto 118 |
| go-wind-plugins | 251 | go 177, md 71 |
| go-wind-toolkit | 138 | go 73, ts 23, md 17 |
| go-wind-bootstrap | 70 | go 51, proto 15, md 4 |
| go-wind-admin-template | 21 | sh 8, yaml 4, proto 3 |
| go-wind, go-wind-bi | 4 | md only |
| **total** | **~7023** | |

**Character volume:** 1,373,775 CJK chars total — 251,977 in `.md`, 1,121,798 in code.

**Line volume:** 174,310 CJK-bearing lines, **61,059 unique** (2.85× dedup). Segment-level dedup lands
lower still — realistic unique payload after normalization ≈ **420–480k chars**.

That number is the whole ballgame: **the deduped corpus fits inside DeepL's 500k/month free tier**, and
sits at ~$8–10 on Google Cloud Translation after its own 500k free tier.

**Comment vs non-comment split** (line-leading heuristic):

| Type | comment lines | other lines |
|---|---:|---:|
| ts/vue/tsx | 29,394 | 4,894 |
| go | 28,418 | 25,242 |
| proto | 5,934 | 15,912 |

Frontend is ~86% comments (very safe). Go is ~53% comments; the rest is error messages, `ent` schema
`.Comment()` calls, and struct-tag descriptions. Proto is mostly *trailing* comments and
`openapi`/`gnostic` option strings — these need AST handling, not regex.

**Hard exclusion set** (deliberately Chinese, never touch):

```
**/locales/**  **/messages/**  **/langs/**  **/i18n/**  **/*.arb
**/*zh-CN*  **/*zh_CN*  **/*.zh.*  **/README*.ja*  **/README*.zh*
go-wind-*/frontend/**/src/app/[locale]/**
```
Verified present: `go-wind-admin/frontend/admin/{react,vue-element,vue-vben}/src/locales/zh-CN/`,
`go-wind-cms/frontend/{admin,app}/**/{locales,messages}/zh-CN/`, `go-wind-shop/frontend/**/locales/zh-CN/`,
`go-wind-{uba,ledger}/frontend/admin/**/locales/langs/zh-CN/`, Flutter `.arb` files.

---

## Shared architecture (all options use this — it is what makes any of them cheap)

Whole-file round-tripping through any translator is the expensive mistake. Instead:

```
1. EXTRACT   per-file, per-language-aware → list of {file, span, kind, text}
             kind ∈ {line-comment, block-comment, doc-comment, string-literal, md-block}
2. NORMALIZE strip leading //, /*, *, indentation; trim; keep the prefix for reassembly
3. DEDUP     SHA1(normalized text) → global segment table (2.85×+ reduction)
4. TRANSLATE only unseen hashes → engine of choice (see options below)
5. CACHE     append to segments.jsonl — permanent, resumable, re-runnable at zero cost
6. GLOSSARY  force-preserve terms: Kratos, ent, protobuf, gRPC, JWT, Casbin, Zanzibar, Keto,
             OIDC, Vben, Taro, minio, S3, and every identifier matching \b[A-Za-z_][A-Za-z0-9_]*\b
             that appears in surrounding code
7. SPLICE    write back byte-span replacements, deepest-offset-first, per file
8. VERIFY    compile/lint gate per repo (see Verification below)
```

Extractors that actually understand syntax (do not regex Go/proto):
- **Go** — `go/parser` + `go/ast` with `ParseComments`; comments come back as `*ast.CommentGroup`
  with exact `token.Pos`. Strings via `ast.BasicLit` with `Kind == token.STRING`. ~120 lines.
- **proto** — `github.com/yoheimuta/go-protoparser` or `protoc --descriptor_set_out` with
  `SourceCodeInfo` (gives leading/trailing comments with paths). ~100 lines.
- **ts/tsx/vue** — `typescript` compiler API `ts.getLeadingCommentRanges` + `@vue/compiler-sfc`
  for SFC blocks. Or `tree-sitter` for one uniform pass across ts/tsx/vue/dart/go.
- **md** — `remark`/`mdast`: translate text nodes, skip `code`/`inlineCode`/link URLs/frontmatter keys.
- **dart/cs/sql/sh/yaml** — comment-only pass; too few chars (~2% of corpus) to justify AST work.

**Recommendation: one `tree-sitter` extractor** covering go/ts/tsx/vue/dart/proto/md. Single Node or
Python script, ~400 lines, one grammar set, uniform span model. This is rung 5 of the ladder — the
grammars are already-solved dependencies.

---

## Option A — DeepL Free + AST extraction  ★ recommended, ~$0

**Cost:** $0 (deduped payload ≈ 450k chars < 500k/mo free tier). LLM tokens: ~0 for translation.
**Wall time:** ~4–6h, mostly the verification gate.
**Quality:** Best non-LLM zh→en available. Handles technical prose well.

1. Get free DeepL API key (`api-free.deepl.com`, no card required).
2. Build tree-sitter extractor → `segments.jsonl` (one pass over all 11 repos).
3. Translate unique segments via `/v2/translate`, batching 50 texts/request, `source_lang=ZH`,
   `target_lang=EN-US`, `preserve_formatting=1`, plus a **DeepL glossary** for the term list above.
4. Splice back, run the verification gate, commit per repo.
5. Docs handled per Doc Strategy below (same segment cache — md text nodes are just more segments).

**Why this wins:** zero marginal cost, no LLM inference, deterministic and re-runnable, and the
segment cache means a second pass over new commits is nearly free.

**Risk:** if deduped payload overshoots 500k, spill the remainder to next month or to Google's free
tier. Split by repo so the boundary is clean.

---

## Option B — Google Cloud Translation v3 + AST extraction — ~$8–18

Same pipeline, different engine. Use when you want it done in one sitting with no quota ceiling.

- v3 `translateText`, 1024 segments/request, `mimeType: text/plain`.
- **Glossary support is first-class** (upload a TSV of preserve-terms as a `Glossary` resource) —
  better than DeepL's for enforcing identifier preservation.
- Pricing: $20/M chars, first 500k/mo free → 1.37M raw ≈ $17.5; **deduped ≈ $0 (under free tier)**.
- Also supports `model: nmt` (cheap) vs `adaptive` — stick with `nmt`.

**Pick B over A if:** you want a single vendor for docs + code, or you want glossary enforcement.

---

## Option C — Fully offline, zero API, zero cost — Argos / OPUS-MT local

**Cost:** $0 forever, no quota, no network, no data leaving the machine.
**Wall time:** ~1h setup + ~2–4h inference on M-series CPU for 61k segments.
**Quality:** Noticeably below DeepL. Acceptable for comments, weak on terse technical fragments.

```bash
pip install argostranslate ctranslate2 sentencepiece
python -c "import argostranslate.package as p; p.update_package_index(); \
  p.install_from_path([x for x in p.get_available_packages() if x.from_code=='zh' and x.to_code=='en'][0].download())"
```

Or run `Helsinki-NLP/opus-mt-zh-en` converted to CTranslate2 (`ct2-transformers-converter`) for ~5×
throughput over raw transformers. Or `docker run libretranslate/libretranslate` and hit it with the
exact same client code as Option A — swap the HTTP endpoint, keep the whole pipeline.

**Pick C if:** the code must not leave the machine, or you want an unlimited-rerun baseline.

**Hybrid C+A (best quality/cost curve):** run C over *everything*, then route only the segments the
verification gate flags — plus all `.md` prose — through DeepL. Local pass eats 80% of volume at $0;
paid pass fixes the 20% that matters. Still $0 in practice.

---

## Option D — LLM inference, scoped to what MT genuinely can't do

MT engines are worse than an LLM at exactly three things here: terse dev-shorthand comments,
`README` prose that needs restructuring, and error-message strings where tone matters.

Scope LLM to **only** those, via the same segment table:
- segments < 8 chars (MT context-starved), or
- segments in `.md` H1/H2 blocks, or
- segments where the MT output round-trips (en→zh) to low similarity — an automatic quality flag.

Estimated: ~6–9k segments ≈ ~300k input tokens with batching (100 segments/call, code context omitted).
That is 1–2% of the naive whole-file approach.

**Naive LLM-only cost for contrast:** whole-file round trips over 7,023 files ≈ 12–20M in + 12–20M out.
Do not do this.

---

## Option E — Bulk mechanical, no translation engine at all (dictionary pass)

For the highest-frequency segments only. Extract top-N by occurrence count from the segment table:

```bash
rg '[\x{4e00}-\x{9fff}]' go-wind* -g '!.git' --no-filename -N | sed 's/^[[:space:]]*//' \
  | sort | uniq -c | sort -rn | head -500
```

The top ~500 unique lines almost certainly cover a large share of the 174k occurrences (boilerplate
`// 创建`, `// 更新`, `// 删除`, `// 查询列表`, field comments repeated across every ent schema).
Hand-curate or one-shot-translate those 500, apply as a `sed`-style dictionary, then send only the
remainder to Option A/B/C.

**Not a standalone option** — it is a cheap pre-pass that shrinks whatever you pick. Run it first.

---

## Doc strategy — English default, Chinese as selectable translation

Current state is inconsistent across repos: `README.md`(zh) + `README.en-US.md`,
`README_en.md`, `README.ja-JP.md`, `README.ja.md`, `README.en.md`, `README_EN.md`.

**Normalize to the `.<lang>.md` convention** (used by go-wind-cms/shop/ledger already, and the
convention Vben/Vue ecosystem uses):

```
README.md          ← English (default, new)
README.zh-CN.md    ← original Chinese (git mv, history preserved)
README.ja-JP.md    ← existing Japanese, renamed if needed
docs/*.md          ← English default
docs/zh-CN/*.md    ← original Chinese, git mv'd
```

Steps per repo:
1. `git mv README.md README.zh-CN.md` — **preserves history**, this matters.
2. If a `README.en*.md`/`README_en.md` already exists → `git mv` it to `README.md`, then diff it
   against a fresh translation of the zh original and merge in whatever the stale en version missed.
   Several of these en files are outdated relative to the zh source.
3. Otherwise generate `README.md` from the translated segments.
4. Prepend a language switcher line to **every** variant:
   ```markdown
   [English](./README.md) · [简体中文](./README.zh-CN.md) · [日本語](./README.ja-JP.md)
   ```
5. Same treatment for `docs/` in go-wind-{admin,cms,plugins,uba} and the two Flutter `docs/` dirs.
6. Leave `CLAUDE.md` / `AGENTS.md` / `SKILL.md` English-only — no zh variant needed, these are
   agent instruction files, translate in place.

**Do not** touch `frontend/**/locales/**` — that is the runtime i18n, already correct.

---

## Verification gate (non-negotiable, runs per repo before commit)

```bash
# 1. nothing outside the exclusion set still has CJK
rg -l '[\x{4e00}-\x{9fff}]' "$repo" -g '!.git' \
   -g '!**/locales/**' -g '!**/messages/**' -g '!**/langs/**' -g '!**/i18n/**' \
   -g '!*.arb' -g '!*zh-CN*' -g '!*.zh-CN.md' -g '!docs/zh-CN/**'

# 2. code still builds
cd "$repo/backend" && go build ./... && go vet ./...
cd "$repo/frontend" && pnpm -r build   # where applicable

# 3. protos still generate
buf generate   # or the repo's make proto target

# 4. no identifier drift — diff must not touch non-comment, non-string tokens
git diff -U0 | rg '^[+-]' | rg -v '^[+-]{3}' | rg '[A-Za-z_][A-Za-z0-9_]*\s*[:=(]' | less
```

Gate 4 is the important one. MT engines love to "helpfully" translate an identifier inside a comment
(`// GetUserList 获取用户列表` → `// Get User List get user list`). The glossary prevents most of it;
the diff review catches the rest.

**Branch per repo:** `chore/i18n-en-default`. 11 PRs, one per repo, reviewable independently.

---

## Recommended sequence

```
Option E pre-pass (top-500 dictionary)
  → Option A (DeepL Free, AST-extracted, deduped)          [$0, covers ~95%]
  → Option D scoped LLM pass on flagged + README prose      [~300k tokens]
  → verification gate → 11 PRs
```

Fallback if DeepL quota trips: Option B free tier, then Option C local for the tail.

**Sizing:** 11 repos are independent → fan out one agent per repo for the splice+verify stage after
the shared segment cache is populated. Extraction and translation are a single global pass — do not
parallelize those, the cache is the point.

---

## Effort estimate

| Phase | Effort |
|---|---|
| tree-sitter extractor (go/ts/vue/proto/md/dart) | ~400 LOC, 2–3h |
| translate client + cache + glossary | ~150 LOC, 1h |
| splicer + doc restructurer | ~200 LOC, 1–2h |
| translation run (Option A) | ~30 min wall |
| verification + fixes across 11 repos | 3–5h (parallelizable) |
| **total** | **~1.5 days**, ~$0 |
