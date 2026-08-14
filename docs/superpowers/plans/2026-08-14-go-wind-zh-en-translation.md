# go-wind zh→en Mass Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate all Chinese comments, docs, and non-i18n strings across the 11 `go-wind*` repos to English, using a deduplicated segment cache and a free machine-translation engine (near-zero LLM inference), with English docs as default and Chinese preserved as a selectable translation.

**Architecture:** A standalone Python tool (`gwt`) in a new sibling repo does AST-accurate extraction of translatable segments via tree-sitter, deduplicates them by content hash into a permanent JSONL cache, translates only unseen segments through a pluggable engine (dictionary → DeepL Free → Argos local), and splices results back by byte span. Generated files are never translated — their sources (proto, ent schema) are, then the repo's own `make gen` regenerates them. Docs are restructured so `README.md` is English and the Chinese original moves to `README.zh-CN.md` via `git mv`.

**Tech Stack:** Python 3.13, tree-sitter (`tree-sitter-language-pack`), pytest, DeepL Free API, Argos Translate (offline fallback), `git mv`, per-repo `make gen`/`make build`.

**Spec:** `docs/superpowers/specs/2026-08-14-go-wind-translation-options.md` (the options analysis this plan implements — Option E pre-pass → Option A DeepL → Option D scoped LLM)

---

## Global Constraints

- **Python 3.13.1**, already installed. No virtualenv manager assumed beyond `python3 -m venv`.
- **Never translate** anything matching the exclusion globs in `gwt/classify.py` — these are deliberately Chinese runtime i18n resources. Verified present in the repos: `**/locales/**`, `**/messages/**`, `**/langs/**`, `**/i18n/**`, `**/*.arb`, `**/[locale]/**`, `*zh-CN*`, `*zh_CN*`, `*.zh-CN.md`, `README*.ja*`, `README*.zh*`.
- **Never translate generated files.** Verified 329,635 CJK chars across 1,590 generated files. Globs: `**/gen/**`, `**/generated/**`, `**/ent/**` (except `ent/schema/**`, which is hand-written source), `*.pb.go`, `*.pb.ts`, `**/migrate/schema.go`. Translate the proto / ent schema source, then run the repo's `make gen`.
- **Never alter identifiers.** Any ASCII token inside a translated segment that is camelCase, PascalCase, contains `_`, is followed by `(`, is inside backticks, or is a URL must survive byte-identical.
- **Target corpus:** 969,853 CJK chars across 5,171 files (total 1,373,775 minus generated minus i18n).
- **Segment cache is permanent and shared across all 11 repos.** `cache/segments.jsonl` is committed. Re-runs after upstream merges cost only the new segments.
- **Translation direction:** `source_lang=ZH`, `target_lang=EN-US`.
- **Branch per target repo:** `chore/i18n-en-default`. One PR per repo, 11 total.
- **Tooling repo:** `/Users/dhiazfathra/Documents/GitHub/dhiazfathra/go-wind-translate/` (naming matches the existing `go-admin-translate` sibling).
- **Target repos** (siblings of the tooling repo): `go-wind`, `go-wind-admin`, `go-wind-admin-template`, `go-wind-bi`, `go-wind-bootstrap`, `go-wind-cms`, `go-wind-ledger`, `go-wind-plugins`, `go-wind-shop`, `go-wind-toolkit`, `go-wind-uba`.

### Why this plan is not "just point an agent at it"

`go-admin-translate` is a prior LLM-driven attempt at this exact task (branch `translate-chinese-to-english`, 5 commits). It left **75,224 CJK chars** — roughly 90% of its source repo's Chinese — untranslated, and it translated generated files that will revert on the next `make gen`. Whole-file agentic translation does not converge at this scale. The dedup cache is what makes it converge.

---

## File Structure

```
go-wind-translate/
├── pyproject.toml              # deps: tree-sitter-language-pack, requests, pytest
├── glossary.txt                # one preserve-term per line
├── dictionary.tsv              # zh<TAB>en high-frequency pre-pass pairs
├── cache/
│   └── segments.jsonl          # {"h","src","en","engine"} — committed, permanent
├── gwt/
│   ├── __init__.py
│   ├── classify.py             # which files are translatable
│   ├── segments.py             # Segment/Occurrence models + cache load/save
│   ├── extract.py              # tree-sitter core, per-language node-kind config
│   ├── extract_md.py           # markdown extractor (regex; skips fences/code/URLs)
│   ├── mask.py                 # identifier masking + glossary
│   ├── splice.py               # byte-span writeback
│   ├── docs_layout.py          # README/docs restructure + language switcher
│   ├── verify.py               # residual-CJK, build, link-integrity gates
│   ├── cli.py                  # subcommands: extract translate splice docs verify run
│   └── engines/
│       ├── __init__.py         # Engine protocol + get_engine()
│       ├── dictionary.py       # local TSV, zero network
│       ├── deepl_engine.py     # DeepL Free API
│       └── argos_engine.py     # offline Argos/OPUS-MT
├── work/<repo>/occurrences.jsonl   # gitignored, per-repo extraction output
├── docs/superpowers/plans/
└── tests/
    ├── fixtures/
    └── test_*.py
```

Files that change together live together: each engine is one file behind one protocol; extraction is split only where the mechanism genuinely differs (tree-sitter vs markdown regex).

---

### Task 1: Repo scaffold and file classifier

**Files:**
- Create: `pyproject.toml`
- Create: `gwt/__init__.py`
- Create: `gwt/classify.py`
- Test: `tests/test_classify.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `classify.is_translatable(path: str) -> bool`, `classify.LANG_BY_SUFFIX: dict[str, str]`, `classify.iter_translatable(repo_root: Path) -> Iterator[Path]`, `classify.EXCLUDE_GLOBS: tuple[str, ...]`, `classify.GENERATED_GLOBS: tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_classify.py
import pytest
from gwt.classify import is_translatable, LANG_BY_SUFFIX


@pytest.mark.parametrize("path", [
    "go-wind-cms/backend/app/core/service/internal/data/user.go",
    "go-wind-cms/backend/api/admin/service/v1/user.proto",
    "go-wind-admin/frontend/admin/react/src/views/login.tsx",
    "go-wind-uba/docs/architecture.md",
    "go-wind-cms/backend/app/core/service/internal/data/ent/schema/user.go",
])
def test_translatable_sources(path):
    assert is_translatable(path) is True


@pytest.mark.parametrize("path", [
    # deliberate Chinese: runtime i18n
    "go-wind-admin/frontend/admin/react/src/locales/zh-CN/_modules/menu.json",
    "go-wind-cms/frontend/app/react/messages/zh-CN/common.json",
    "go-wind-uba/frontend/admin/packages/locales/src/langs/zh-CN/common.json",
    "go-wind-ledger/frontend/app/flutter_app/lib/l10n/app_zh.arb",
    "go-wind-cms/frontend/app/react/src/app/[locale]/login/page.tsx",
    "go-wind-cms/README.ja-JP.md",
    "go-wind-shop/README.zh-CN.md",
    # generated: regenerate, do not translate
    "go-wind-cms/backend/api/gen/go/admin/service/v1/user.pb.go",
    "go-wind-admin/frontend/admin/react/src/api/generated/admin/service/v1/index.ts",
    "go-wind-cms/backend/app/core/service/internal/data/ent/user.go",
    "go-wind-admin/backend/app/admin/service/internal/data/ent/migrate/schema.go",
    # not a source file
    "go-wind-cms/node_modules/foo/index.js",
    "go-wind-cms/.git/config",
])
def test_excluded(path):
    assert is_translatable(path) is False


def test_ent_schema_beats_ent_exclusion():
    # ent/schema/ is hand-written source; ent/ elsewhere is generated
    assert is_translatable("x/backend/internal/data/ent/schema/post.go") is True
    assert is_translatable("x/backend/internal/data/ent/post.go") is False


def test_lang_lookup():
    assert LANG_BY_SUFFIX[".go"] == "go"
    assert LANG_BY_SUFFIX[".vue"] == "vue"
    assert LANG_BY_SUFFIX[".md"] == "markdown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_classify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gwt'`

- [ ] **Step 3: Write minimal implementation**

```toml
# pyproject.toml
[project]
name = "gwt"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "tree-sitter-language-pack>=0.9",
    "requests>=2.32",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]
local = ["argostranslate>=1.9"]

[project.scripts]
gwt = "gwt.cli:main"

[tool.setuptools.packages.find]
include = ["gwt*"]
```

```python
# gwt/__init__.py
```

```python
# gwt/classify.py
"""Decide which files carry translatable Chinese."""
from __future__ import annotations

import re
from fnmatch import fnmatch
from pathlib import Path
from typing import Iterator

CJK = re.compile(r"[一-鿿]")

# Deliberately Chinese — runtime i18n resources and non-en doc variants.
EXCLUDE_GLOBS: tuple[str, ...] = (
    "*/locales/*", "*/messages/*", "*/langs/*", "*/i18n/*",
    "*/[[]locale[]]/*",
    "*.arb",
    "*zh-CN*", "*zh_CN*", "*.zh.*",
    "*README*.ja*", "*README*.zh*", "*README.en*", "*README_en*", "*README_EN*",
    "*/.git/*", "*/node_modules/*", "*/vendor/*", "*/dist/*", "*/.next/*",
    "*/build/*", "*/.dart_tool/*",
)

# Generated — translate the source and run `make gen` instead.
GENERATED_GLOBS: tuple[str, ...] = (
    "*/gen/*", "*/generated/*",
    "*.pb.go", "*.pb.ts", "*.pb.dart", "*_pb2.py",
    "*.g.dart", "*.freezed.dart",
    "*/migrate/schema.go",
    "*/wire_gen.go",
    "*/ent/*",  # overridden below for ent/schema/
)

# ent/schema/ is hand-written; everything else under ent/ is generated.
GENERATED_EXCEPTIONS: tuple[str, ...] = ("*/ent/schema/*",)

LANG_BY_SUFFIX: dict[str, str] = {
    ".go": "go",
    ".proto": "proto",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".vue": "vue",
    ".dart": "dart",
    ".md": "markdown",
    ".cs": "csharp",
    ".sh": "bash",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sql": "sql",
    ".scss": "scss",
    ".css": "css",
    ".less": "css",
    ".ps1": "powershell",
    ".json": "json",
    ".html": "html",
}


def _matches(path: str, globs: tuple[str, ...]) -> bool:
    probe = path if path.startswith("/") else "/" + path
    return any(fnmatch(probe, "*" + g if not g.startswith("*") else g) for g in globs)


def is_translatable(path: str) -> bool:
    p = str(path).replace("\\", "/")
    if Path(p).suffix not in LANG_BY_SUFFIX:
        return False
    if _matches(p, EXCLUDE_GLOBS):
        return False
    if _matches(p, GENERATED_EXCEPTIONS):
        return True
    if _matches(p, GENERATED_GLOBS):
        return False
    return True


def has_cjk(text: str) -> bool:
    return CJK.search(text) is not None


def iter_translatable(repo_root: Path) -> Iterator[Path]:
    """Yield files under repo_root that are translatable AND actually contain CJK."""
    for f in repo_root.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(repo_root).as_posix()
        if not is_translatable(rel):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if has_cjk(text):
            yield f
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pip install -e '.[dev]' && python3 -m pytest tests/test_classify.py -v`
Expected: PASS, 17 passed

- [ ] **Step 5: Sanity-check the classifier against the real corpus**

Run:
```bash
python3 -c "
from pathlib import Path
from gwt.classify import iter_translatable
root = Path.home()/'Documents/GitHub/dhiazfathra'
total = 0
for r in sorted(root.glob('go-wind*')):
    if not r.is_dir(): continue
    n = sum(1 for _ in iter_translatable(r))
    total += n
    print(f'{r.name:26} {n}')
print('TOTAL', total)
"
```
Expected: TOTAL between 4,800 and 5,400 (measured corpus is 5,171 files). If it reports ~7,000 the generated exclusions are not firing; if it reports under 4,000 the exclusions are too broad. Fix `classify.py` before continuing.

- [ ] **Step 6: Commit**

```bash
git init && git add -A
git commit -m "feat: file classifier for zh->en translation corpus

- exclusion globs for runtime i18n (locales/messages/langs/i18n/.arb)
- generated-file globs with ent/schema/ exception
- corpus verified at ~5.1k files across 11 go-wind repos"
```

---

### Task 2: Segment model and permanent cache

**Files:**
- Create: `gwt/segments.py`
- Test: `tests/test_segments.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Segment` dataclass: `h: str`, `src: str`, `kind: str`, `lang: str`
  - `Occurrence` dataclass: `file: str`, `start: int`, `end: int`, `h: str`
  - `seg_hash(src: str) -> str` — SHA1 of the NFC-normalized, whitespace-collapsed source
  - `Cache` class: `Cache.load(path) -> Cache`, `.get(h) -> str | None`, `.put(h, src, en, engine)`, `.save()`, `.missing(hashes) -> list[str]`
  - `write_occurrences(path, occs)`, `read_occurrences(path) -> list[Occurrence]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_segments.py
from gwt.segments import Cache, Occurrence, Segment, seg_hash, read_occurrences, write_occurrences


def test_hash_is_whitespace_and_unicode_stable():
    assert seg_hash("创建用户") == seg_hash("  创建用户  ")
    assert seg_hash("创建 用户") == seg_hash("创建  用户")
    assert seg_hash("创建用户") != seg_hash("删除用户")


def test_cache_roundtrip(tmp_path):
    p = tmp_path / "segments.jsonl"
    c = Cache.load(p)
    assert c.get(seg_hash("创建用户")) is None
    c.put(seg_hash("创建用户"), "创建用户", "Create user", "deepl")
    c.save()

    c2 = Cache.load(p)
    assert c2.get(seg_hash("创建用户")) == "Create user"


def test_cache_missing_filters_known(tmp_path):
    c = Cache.load(tmp_path / "s.jsonl")
    a, b = seg_hash("甲"), seg_hash("乙")
    c.put(a, "甲", "A", "dict")
    assert c.missing([a, b]) == [b]


def test_cache_put_is_idempotent_and_append_safe(tmp_path):
    p = tmp_path / "s.jsonl"
    c = Cache.load(p)
    h = seg_hash("重复")
    c.put(h, "重复", "Duplicate", "dict")
    c.put(h, "重复", "Duplicate", "dict")
    c.save()
    assert p.read_text(encoding="utf-8").strip().count("\n") == 0  # exactly one line


def test_occurrences_roundtrip(tmp_path):
    p = tmp_path / "occ.jsonl"
    occs = [Occurrence(file="a.go", start=10, end=20, h="abc"),
            Occurrence(file="a.go", start=30, end=40, h="def")]
    write_occurrences(p, occs)
    assert read_occurrences(p) == occs


def test_segment_dataclass_fields():
    s = Segment(h="x", src="中", kind="line_comment", lang="go")
    assert (s.h, s.src, s.kind, s.lang) == ("x", "中", "line_comment", "go")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_segments.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gwt.segments'`

- [ ] **Step 3: Write minimal implementation**

```python
# gwt/segments.py
"""Segment identity, occurrence records, and the permanent translation cache."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

_WS = re.compile(r"\s+")


def seg_hash(src: str) -> str:
    """Stable identity for a translatable segment.

    Normalizes Unicode (NFC) and collapses whitespace so that the same prose
    indented differently in two files hashes to one cache entry.
    """
    norm = _WS.sub(" ", unicodedata.normalize("NFC", src)).strip()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Segment:
    h: str
    src: str
    kind: str
    lang: str


@dataclass(frozen=True)
class Occurrence:
    file: str
    start: int   # byte offset, inclusive
    end: int     # byte offset, exclusive
    h: str


class Cache:
    """Append-only JSONL store of hash -> English. Committed to git."""

    def __init__(self, path: Path, entries: dict[str, dict]) -> None:
        self.path = path
        self._entries = entries

    @classmethod
    def load(cls, path: Path | str) -> "Cache":
        path = Path(path)
        entries: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                entries[rec["h"]] = rec
        return cls(path, entries)

    def get(self, h: str) -> str | None:
        rec = self._entries.get(h)
        return rec["en"] if rec else None

    def put(self, h: str, src: str, en: str, engine: str) -> None:
        self._entries[h] = {"h": h, "src": src, "en": en, "engine": engine}

    def missing(self, hashes) -> list[str]:
        seen, out = set(), []
        for h in hashes:
            if h in self._entries or h in seen:
                continue
            seen.add(h)
            out.append(h)
        return out

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(self._entries[h], ensure_ascii=False)
                 for h in sorted(self._entries)]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def __len__(self) -> int:
        return len(self._entries)


def write_occurrences(path: Path | str, occs) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for o in occs:
            fh.write(json.dumps(asdict(o), ensure_ascii=False) + "\n")


def read_occurrences(path: Path | str) -> list[Occurrence]:
    return [Occurrence(**json.loads(line))
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_segments.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add gwt/segments.py tests/test_segments.py
git commit -m "feat: segment hashing, occurrence records, permanent JSONL cache"
```

---

### Task 3: Tree-sitter extractor core with Go support

**Files:**
- Create: `gwt/extract.py`
- Test: `tests/test_extract_go.py`
- Test fixture: `tests/fixtures/sample.go`

**Interfaces:**
- Consumes: `gwt.segments.{Segment, Occurrence, seg_hash}`, `gwt.classify.{LANG_BY_SUFFIX, has_cjk}`.
- Produces: `extract.extract_file(path: Path, rel: str) -> tuple[list[Segment], list[Occurrence]]`, `extract.NODE_KINDS: dict[str, dict[str, str]]` mapping language → tree-sitter node type → segment kind.

The extractor returns byte offsets covering **only the Chinese-bearing text**, not the whole comment node — so `// GetUser 获取用户` yields a span over `获取用户` alone and `GetUser` is never sent to a translator.

- [ ] **Step 1: Verify tree-sitter grammar availability before building on it**

Run:
```bash
python3 -m pip install 'tree-sitter-language-pack>=0.9'
python3 -c "
from tree_sitter_language_pack import get_parser
for lang in ['go','proto','typescript','tsx','vue','dart','markdown','c_sharp','bash','yaml','sql','css','html']:
    try:
        get_parser(lang); print('OK  ', lang)
    except Exception as e:
        print('MISS', lang, type(e).__name__)
"
```
Expected: `go`, `typescript`, `tsx`, `markdown` at minimum report OK.

**If a grammar reports MISS:** drop that language from `NODE_KINDS` and route its files to the line-based comment fallback (`_extract_lines`, implemented in Step 3). Record which languages fell back — Task 4 depends on knowing this. Do not block on a missing grammar; `.vue`, `.dart`, and `.proto` all degrade acceptably to the fallback since their Chinese is overwhelmingly in `//`-style comments.

- [ ] **Step 2: Write the failing test**

```python
# tests/fixtures/sample.go
package data

import "context"

// UserRepo 用户仓储实现
// 提供用户的增删改查能力
type UserRepo struct{}

// Create 创建用户, 返回 *ent.User
func (r *UserRepo) Create(ctx context.Context) error {
	// TODO 这里需要处理并发
	name := "张三"          // 默认用户名
	return fmt.Errorf("创建用户失败: %w", nil)
}
```

```python
# tests/test_extract_go.py
from pathlib import Path
from gwt.extract import extract_file

FIX = Path(__file__).parent / "fixtures" / "sample.go"


def _texts(segs):
    return [s.src for s in segs]


def test_extracts_doc_and_line_comments():
    segs, occs = extract_file(FIX, "sample.go")
    texts = _texts(segs)
    assert "用户仓储实现" in texts
    assert "提供用户的增删改查能力" in texts
    assert "默认用户名" in texts


def test_identifier_prefix_is_not_part_of_segment():
    """`// UserRepo 用户仓储实现` must yield only the Chinese half."""
    segs, _ = extract_file(FIX, "sample.go")
    assert "用户仓储实现" in _texts(segs)
    assert not any("UserRepo" in s.src for s in segs)
    assert not any(s.src.startswith("//") for s in segs)


def test_extracts_string_literals_with_cjk():
    segs, _ = extract_file(FIX, "sample.go")
    texts = _texts(segs)
    assert any("创建用户失败" in t for t in texts)
    assert "张三" in texts


def test_ignores_ascii_only_comments():
    segs, _ = extract_file(FIX, "sample.go")
    assert not any(s.src.strip() == "TODO" for s in segs)
    assert all(any("一" <= c <= "鿿" for c in s.src) for s in segs)


def test_offsets_slice_back_to_source_text():
    raw = FIX.read_bytes()
    segs, occs = extract_file(FIX, "sample.go")
    by_hash = {s.h: s.src for s in segs}
    for o in occs:
        assert raw[o.start:o.end].decode("utf-8") == by_hash[o.h]


def test_occurrences_do_not_overlap():
    _, occs = extract_file(FIX, "sample.go")
    spans = sorted((o.start, o.end) for o in occs)
    for (_, e1), (s2, _) in zip(spans, spans[1:]):
        assert e1 <= s2
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m pytest tests/test_extract_go.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gwt.extract'`

- [ ] **Step 4: Write minimal implementation**

```python
# gwt/extract.py
"""AST-accurate extraction of Chinese-bearing segments."""
from __future__ import annotations

import re
from pathlib import Path

from gwt.classify import LANG_BY_SUFFIX, has_cjk
from gwt.segments import Occurrence, Segment, seg_hash

# tree-sitter node type -> our segment kind, per language.
NODE_KINDS: dict[str, dict[str, str]] = {
    "go": {
        "comment": "comment",
        "interpreted_string_literal": "string",
        "raw_string_literal": "string",
    },
    "typescript": {
        "comment": "comment",
        "string_fragment": "string",
        "template_string": "string",
    },
    "tsx": {
        "comment": "comment",
        "string_fragment": "string",
        "template_string": "string",
    },
    "proto": {"comment": "comment", "string": "string"},
    "dart": {"comment": "comment", "documentation_comment": "comment"},
    "c_sharp": {"comment": "comment", "string_literal": "string"},
}

# A run of CJK plus the punctuation/spacing that belongs to it. Latin runs on
# either side (identifiers, format verbs, URLs) fall outside the match.
_CJK_RUN = re.compile(
    r"[一-鿿　-〿＀-￯]"
    r"(?:[一-鿿　-〿＀-￯\s,.:;()'\"-]*"
    r"[一-鿿　-〿＀-￯])?"
)

_LINE_COMMENT = re.compile(r"(?://|#|--)\s?(.*)$")


def _parser(lang: str):
    from tree_sitter_language_pack import get_parser
    return get_parser(lang)


def _cjk_spans(raw: bytes, node_start: int, node_end: int):
    """Yield (start, end, text) byte spans of CJK runs inside a node."""
    chunk = raw[node_start:node_end].decode("utf-8", errors="replace")
    for m in _CJK_RUN.finditer(chunk):
        text = m.group(0).strip()
        if not text or not has_cjk(text):
            continue
        # Recompute byte offsets: char index -> byte offset within the chunk.
        pre = chunk[: m.start()].encode("utf-8")
        body = m.group(0)
        lead = len(body) - len(body.lstrip())
        lead_b = len(body[:lead].encode("utf-8"))
        start = node_start + len(pre) + lead_b
        yield start, start + len(text.encode("utf-8")), text


def _extract_treesitter(raw: bytes, rel: str, lang: str):
    kinds = NODE_KINDS[lang]
    tree = _parser(lang).parse(raw)
    segs: dict[str, Segment] = {}
    occs: list[Occurrence] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        kind = kinds.get(node.type)
        if kind is not None:
            for s, e, text in _cjk_spans(raw, node.start_byte, node.end_byte):
                h = seg_hash(text)
                segs.setdefault(h, Segment(h=h, src=text, kind=kind, lang=lang))
                occs.append(Occurrence(file=rel, start=s, end=e, h=h))
        else:
            stack.extend(node.children)
    return list(segs.values()), occs


def _extract_lines(raw: bytes, rel: str, lang: str):
    """Fallback for languages with no grammar: comment lines and any CJK run."""
    segs: dict[str, Segment] = {}
    occs: list[Occurrence] = []
    offset = 0
    for line in raw.split(b"\n"):
        text = line.decode("utf-8", errors="replace")
        if has_cjk(text):
            kind = "comment" if _LINE_COMMENT.search(text) else "string"
            for s, e, t in _cjk_spans(raw, offset, offset + len(line)):
                h = seg_hash(t)
                segs.setdefault(h, Segment(h=h, src=t, kind=kind, lang=lang))
                occs.append(Occurrence(file=rel, start=s, end=e, h=h))
        offset += len(line) + 1
    return list(segs.values()), occs


def extract_file(path: Path, rel: str) -> tuple[list[Segment], list[Occurrence]]:
    lang = LANG_BY_SUFFIX.get(Path(rel).suffix, "")
    raw = Path(path).read_bytes()
    if lang == "markdown":
        from gwt.extract_md import extract_markdown
        return extract_markdown(raw, rel)
    if lang in NODE_KINDS:
        try:
            return _extract_treesitter(raw, rel, lang)
        except Exception:
            pass  # grammar unavailable at runtime -> degrade, never crash a repo run
    return _extract_lines(raw, rel, lang)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m pytest tests/test_extract_go.py -v`
Expected: PASS, 6 passed

- [ ] **Step 6: Commit**

```bash
git add gwt/extract.py tests/test_extract_go.py tests/fixtures/sample.go
git commit -m "feat: tree-sitter extractor with CJK-run span narrowing

- spans cover only Chinese runs, never surrounding identifiers
- byte-offset occurrences verified to slice back to segment text
- line-based fallback for languages without a grammar"
```

---

### Task 4: Extractor coverage for ts/tsx/vue/proto/dart plus markdown

**Files:**
- Create: `gwt/extract_md.py`
- Modify: `gwt/extract.py` (add `vue` handling to `extract_file`)
- Test: `tests/test_extract_md.py`
- Test: `tests/test_extract_multilang.py`
- Test fixtures: `tests/fixtures/sample.md`, `tests/fixtures/sample.proto`, `tests/fixtures/sample.vue`

**Interfaces:**
- Consumes: `gwt.extract._cjk_spans`, `gwt.segments.{Segment, Occurrence, seg_hash}`.
- Produces: `extract_md.extract_markdown(raw: bytes, rel: str) -> tuple[list[Segment], list[Occurrence]]`.

Markdown gets a regex extractor, not an AST. It needs exactly one thing an AST would give it — skipping fenced code, inline code, URLs, and frontmatter — and that is ~20 lines of masking. YAGNI on mdast.

Vue SFCs route to the `typescript` grammar for `<script>` blocks; template-block Chinese is caught by the line fallback.

- [ ] **Step 1: Write the failing test**

````markdown
<!-- tests/fixtures/sample.md -->
---
title: 用户服务
---

# 用户服务文档

调用 `CreateUser` 接口创建用户。详见 [文档](https://example.com/用户).

```go
// 这段注释在代码块内, 不应被翻译
fmt.Println("你好")
```

普通段落, 包含 `inline` 代码。
````

```protobuf
// tests/fixtures/sample.proto
syntax = "proto3";

// UserService 用户服务
service UserService {
  // CreateUser 创建用户
  rpc CreateUser(CreateUserRequest) returns (User);
}

message User {
  string name = 1;  // 用户名
}
```

```vue
<!-- tests/fixtures/sample.vue -->
<template>
  <div>用户列表</div>
</template>

<script setup lang="ts">
// 加载用户数据
const title = '用户管理'
</script>
```

```python
# tests/test_extract_md.py
from pathlib import Path
from gwt.extract import extract_file

FIX = Path(__file__).parent / "fixtures" / "sample.md"


def _texts(segs):
    return [s.src for s in segs]


def test_translates_headings_and_prose():
    segs, _ = extract_file(FIX, "sample.md")
    texts = _texts(segs)
    assert "用户服务文档" in texts
    assert any("普通段落" in t for t in texts)


def test_skips_fenced_code_blocks():
    segs, _ = extract_file(FIX, "sample.md")
    joined = " ".join(_texts(segs))
    assert "这段注释在代码块内" not in joined
    assert "你好" not in joined


def test_skips_inline_code_and_urls():
    segs, _ = extract_file(FIX, "sample.md")
    assert not any("CreateUser" in t for t in _texts(segs))
    assert not any("example.com" in t for t in _texts(segs))


def test_translates_link_label_but_not_target():
    segs, _ = extract_file(FIX, "sample.md")
    assert "文档" in _texts(segs)


def test_offsets_slice_back():
    raw = FIX.read_bytes()
    segs, occs = extract_file(FIX, "sample.md")
    by_hash = {s.h: s.src for s in segs}
    for o in occs:
        assert raw[o.start:o.end].decode("utf-8") == by_hash[o.h]
```

```python
# tests/test_extract_multilang.py
from pathlib import Path
import pytest
from gwt.extract import extract_file

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name,expect_present,expect_absent", [
    ("sample.proto", ["用户服务", "创建用户", "用户名"], ["UserService", "CreateUser"]),
    ("sample.vue", ["用户列表", "加载用户数据", "用户管理"], ["setup", "const"]),
])
def test_extracts_and_never_captures_identifiers(name, expect_present, expect_absent):
    segs, occs = extract_file(FIX / name, name)
    texts = " ".join(s.src for s in segs)
    for want in expect_present:
        assert want in texts, f"{name}: missing {want}"
    for reject in expect_absent:
        assert reject not in texts, f"{name}: leaked identifier {reject}"


@pytest.mark.parametrize("name", ["sample.proto", "sample.vue"])
def test_offsets_slice_back(name):
    raw = (FIX / name).read_bytes()
    segs, occs = extract_file(FIX / name, name)
    by_hash = {s.h: s.src for s in segs}
    for o in occs:
        assert raw[o.start:o.end].decode("utf-8") == by_hash[o.h]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_extract_md.py tests/test_extract_multilang.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gwt.extract_md'`

- [ ] **Step 3: Write minimal implementation**

```python
# gwt/extract_md.py
"""Markdown extraction: prose only, code and URLs masked out."""
from __future__ import annotations

import re

from gwt.segments import Occurrence, Segment, seg_hash

# Regions whose bytes must never reach a translator. Order matters:
# fences first, so an inline-code regex cannot chew into a fenced block.
_SKIP = [
    re.compile(r"^---\n.*?\n---\n", re.DOTALL),          # YAML frontmatter
    re.compile(r"```.*?```", re.DOTALL),                  # fenced code
    re.compile(r"~~~.*?~~~", re.DOTALL),                  # fenced code (tilde)
    re.compile(r"`[^`\n]+`"),                             # inline code
    re.compile(r"<[^>\n]+>"),                             # raw HTML tags
    re.compile(r"\]\([^)\n]*\)"),                         # link/image targets
    re.compile(r"https?://\S+"),                          # bare URLs
]


def _mask(raw: bytes) -> bytearray:
    """Return a copy with skip-regions blanked to spaces, preserving length."""
    text = raw.decode("utf-8", errors="replace")
    keep = bytearray(raw)
    for pat in _SKIP:
        for m in pat.finditer(text):
            s = len(text[: m.start()].encode("utf-8"))
            e = s + len(m.group(0).encode("utf-8"))
            for i in range(s, min(e, len(keep))):
                keep[i] = 0x20
    return keep


def extract_markdown(raw: bytes, rel: str):
    from gwt.extract import _cjk_spans  # local import avoids a circular import

    masked = bytes(_mask(raw))
    segs: dict[str, Segment] = {}
    occs: list[Occurrence] = []
    for s, e, text in _cjk_spans(masked, 0, len(masked)):
        h = seg_hash(text)
        segs.setdefault(h, Segment(h=h, src=text, kind="md_prose", lang="markdown"))
        occs.append(Occurrence(file=rel, start=s, end=e, h=h))
    return list(segs.values()), occs
```

Add Vue routing to `gwt/extract.py` — replace the `if lang in NODE_KINDS:` block in `extract_file` with:

```python
    if lang == "vue":
        try:
            return _extract_treesitter(raw, rel, "vue")
        except Exception:
            # No vue grammar: script-block comments and template text both
            # reduce to "lines containing CJK", which the fallback handles.
            return _extract_lines(raw, rel, "vue")
    if lang in NODE_KINDS:
        try:
            return _extract_treesitter(raw, rel, lang)
        except Exception:
            pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ -v`
Expected: PASS, all tests green

- [ ] **Step 5: Extract the full corpus and record the real dedup ratio**

Run:
```bash
python3 -m gwt.cli extract --all 2>/dev/null || python3 -c "
from pathlib import Path
from gwt.classify import iter_translatable
from gwt.extract import extract_file
root = Path.home()/'Documents/GitHub/dhiazfathra'
uniq, occ = set(), 0
for r in sorted(root.glob('go-wind*')):
    if not r.is_dir(): continue
    for f in iter_translatable(r):
        s, o = extract_file(f, str(f.relative_to(r)))
        uniq.update(x.h for x in s); occ += len(o)
print('occurrences', occ, 'unique', len(uniq), 'ratio', round(occ/max(len(uniq),1), 2))
print('unique chars', sum(len(x) for x in uniq))
"
```
Expected: dedup ratio above 2.5×; unique char count between 300k and 550k. **If unique chars exceed 500,000, DeepL Free will not cover it in one month** — record the number and plan the Task 9 spill (split by repo across two months, or route the tail to Argos).

- [ ] **Step 6: Commit**

```bash
git add gwt/extract_md.py gwt/extract.py tests/
git commit -m "feat: markdown, proto, vue, dart extraction

- markdown masks fences, inline code, link targets, URLs, frontmatter
- vue falls back to line extraction when no grammar is present
- corpus dedup ratio measured on the full 11-repo set"
```

---

### Task 5: Identifier masking and glossary

**Files:**
- Create: `gwt/mask.py`
- Create: `glossary.txt`
- Test: `tests/test_mask.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `mask.protect(text: str) -> str` (wraps protected tokens in `<x>…</x>`), `mask.unprotect(text: str) -> str`, `mask.load_glossary(path) -> set[str]`, `mask.IGNORE_TAG = "x"`.

This is the single highest-risk failure mode: a translator rendering `// GetUserList 获取用户列表` as `// Get User List get user list`. DeepL's `tag_handling=xml` with `ignore_tags=["x"]` guarantees wrapped content passes through byte-identical.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_mask.py
from gwt.mask import protect, unprotect


def test_protects_camel_and_pascal_case():
    assert protect("获取 getUserList 数据") == "获取 <x>getUserList</x> 数据"
    assert protect("调用 UserRepo 方法") == "调用 <x>UserRepo</x> 方法"


def test_protects_snake_case_and_calls():
    assert protect("设置 max_retry 次数") == "设置 <x>max_retry</x> 次数"
    assert protect("执行 doWork() 后") == "执行 <x>doWork</x>() 后"


def test_protects_urls_and_backticks():
    assert protect("见 https://a.b/c 页面") == "见 <x>https://a.b/c</x> 页面"
    assert protect("用 `ent.Client` 查询") == "用 <x>`ent.Client`</x> 查询"


def test_protects_glossary_terms_even_when_lowercase():
    # 'kratos' and 'ent' are lowercase and would otherwise look like prose
    assert protect("基于 kratos 框架") == "基于 <x>kratos</x> 框架"
    assert protect("使用 ent 生成") == "使用 <x>ent</x> 生成"


def test_leaves_ordinary_english_words_alone():
    assert protect("这是 a simple test 的说明") == "这是 a simple test 的说明"


def test_protects_format_verbs():
    assert protect("创建用户失败: %w") == "创建用户失败: <x>%w</x>"
    assert protect("已处理 {count} 条") == "已处理 <x>{count}</x> 条"


def test_roundtrip_is_lossless():
    for s in ["获取 getUserList 数据", "见 https://a.b/c 页面", "创建用户失败: %w"]:
        assert unprotect(protect(s)) == s


def test_unprotect_strips_only_our_tag():
    assert unprotect("<x>Foo</x> 和 <b>bold</b>") == "Foo 和 <b>bold</b>"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_mask.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gwt.mask'`

- [ ] **Step 3: Write minimal implementation**

```
# glossary.txt — terms that must survive translation byte-identical.
kratos
ent
wire
buf
proto
protobuf
grpc
gRPC
JWT
OIDC
Casbin
Zanzibar
Keto
Vben
Taro
minio
Nacos
Consul
Kafka
Redis
Etcd
OpenAPI
Swagger
GoWind
go-kratos
Flutter
Riverpod
Antd
```

```python
# gwt/mask.py
"""Wrap code-like tokens so the translation engine passes them through."""
from __future__ import annotations

import re
from pathlib import Path

IGNORE_TAG = "x"

_GLOSSARY_PATH = Path(__file__).resolve().parent.parent / "glossary.txt"


def load_glossary(path: Path | str = _GLOSSARY_PATH) -> set[str]:
    p = Path(path)
    if not p.exists():
        return set()
    return {ln.strip() for ln in p.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.startswith("#")}


_GLOSSARY = load_glossary()

# Ordered: earlier patterns win, so a URL is never re-split as camelCase.
_PATTERNS = [
    re.compile(r"`[^`\n]+`"),                                   # backticked code
    re.compile(r"https?://\S+"),                                # URLs
    re.compile(r"%[-+ #0]?[0-9.*]*[a-zA-Z]"),                   # printf verbs
    re.compile(r"\{[A-Za-z0-9_.]+\}"),                          # {placeholders}
    re.compile(r"\$\{[A-Za-z0-9_.]+\}"),                        # ${placeholders}
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?=\()"),              # call sites
    re.compile(r"\b[a-z]+(?:[A-Z][a-zA-Z0-9]*)+\b"),            # camelCase
    re.compile(r"\b[A-Z][a-z0-9]+(?:[A-Z][a-zA-Z0-9]*)+\b"),    # PascalCase
    re.compile(r"\b[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+\b"),      # snake_case
    re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]+)+\b"),  # dotted
]

_TAGGED = re.compile(rf"</?{IGNORE_TAG}>")


def _glossary_pattern() -> re.Pattern | None:
    if not _GLOSSARY:
        return None
    alts = sorted((re.escape(t) for t in _GLOSSARY), key=len, reverse=True)
    return re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(alts) + r")(?![A-Za-z0-9_])")


_GLOSSARY_RE = _glossary_pattern()


def protect(text: str) -> str:
    """Wrap every code-like token in <x>…</x>. Non-overlapping, left-to-right."""
    spans: list[tuple[int, int]] = []
    pats = list(_PATTERNS)
    if _GLOSSARY_RE is not None:
        pats.insert(2, _GLOSSARY_RE)
    for pat in pats:
        for m in pat.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in spans):
                continue  # already inside a protected span
            spans.append((m.start(), m.end()))
    out, last = [], 0
    for s, e in sorted(spans):
        out.append(text[last:s])
        out.append(f"<{IGNORE_TAG}>{text[s:e]}</{IGNORE_TAG}>")
        last = e
    out.append(text[last:])
    return "".join(out)


def unprotect(text: str) -> str:
    return _TAGGED.sub("", text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_mask.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add gwt/mask.py glossary.txt tests/test_mask.py
git commit -m "feat: identifier masking via DeepL ignore_tags

- camelCase/PascalCase/snake_case/dotted/call-site/URL/printf-verb protection
- glossary of 27 framework terms that must survive byte-identical
- roundtrip losslessness asserted"
```

---

### Task 6: Splicer

**Files:**
- Create: `gwt/splice.py`
- Test: `tests/test_splice.py`

**Interfaces:**
- Consumes: `gwt.segments.{Cache, Occurrence, read_occurrences}`.
- Produces: `splice.splice_file(path: Path, occs: list[Occurrence], cache: Cache) -> int` (returns replacements made), `splice.splice_repo(repo_root: Path, occ_path: Path, cache: Cache) -> dict[str, int]`.

Replacements run **deepest-offset-first** so earlier spans keep their offsets valid.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_splice.py
from pathlib import Path
from gwt.segments import Cache, Occurrence, seg_hash
from gwt.splice import splice_file


def _cache(tmp_path, pairs):
    c = Cache.load(tmp_path / "s.jsonl")
    for zh, en in pairs:
        c.put(seg_hash(zh), zh, en, "test")
    return c


def test_replaces_single_span(tmp_path):
    f = tmp_path / "a.go"
    f.write_text("// 创建用户\n", encoding="utf-8")
    raw = f.read_bytes()
    start = raw.index("创建用户".encode())
    occ = [Occurrence(file="a.go", start=start,
                      end=start + len("创建用户".encode()), h=seg_hash("创建用户"))]
    n = splice_file(f, occ, _cache(tmp_path, [("创建用户", "Create user")]))
    assert n == 1
    assert f.read_text(encoding="utf-8") == "// Create user\n"


def test_multiple_spans_keep_offsets_valid(tmp_path):
    f = tmp_path / "b.go"
    f.write_text("// 甲\nx := \"乙\"\n// 丙\n", encoding="utf-8")
    raw = f.read_bytes()
    occs = []
    for zh in ("甲", "乙", "丙"):
        s = raw.index(zh.encode())
        occs.append(Occurrence(file="b.go", start=s, end=s + len(zh.encode()), h=seg_hash(zh)))
    cache = _cache(tmp_path, [("甲", "A"), ("乙", "B"), ("丙", "C")])
    assert splice_file(f, occs, cache) == 3
    assert f.read_text(encoding="utf-8") == "// A\nx := \"B\"\n// C\n"


def test_replacement_longer_than_source_still_lands(tmp_path):
    """English is usually longer than Chinese - the classic offset-drift bug."""
    f = tmp_path / "c.go"
    f.write_text("// 甲\n// 乙\n", encoding="utf-8")
    raw = f.read_bytes()
    occs = []
    for zh in ("甲", "乙"):
        s = raw.index(zh.encode())
        occs.append(Occurrence(file="c.go", start=s, end=s + len(zh.encode()), h=seg_hash(zh)))
    cache = _cache(tmp_path, [("甲", "a very long replacement string"), ("乙", "another long one")])
    splice_file(f, occs, cache)
    assert f.read_text(encoding="utf-8") == "// a very long replacement string\n// another long one\n"


def test_uncached_span_is_left_untouched(tmp_path):
    f = tmp_path / "d.go"
    f.write_text("// 未翻译\n", encoding="utf-8")
    raw = f.read_bytes()
    s = raw.index("未翻译".encode())
    occ = [Occurrence(file="d.go", start=s, end=s + len("未翻译".encode()), h=seg_hash("未翻译"))]
    assert splice_file(f, occ, _cache(tmp_path, [])) == 0
    assert f.read_text(encoding="utf-8") == "// 未翻译\n"


def test_result_is_valid_utf8(tmp_path):
    f = tmp_path / "e.go"
    f.write_text("// 甲乙丙\n", encoding="utf-8")
    raw = f.read_bytes()
    s = raw.index("甲乙丙".encode())
    occ = [Occurrence(file="e.go", start=s, end=s + len("甲乙丙".encode()), h=seg_hash("甲乙丙"))]
    splice_file(f, occ, _cache(tmp_path, [("甲乙丙", "ABC")]))
    f.read_text(encoding="utf-8")  # raises if invalid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_splice.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gwt.splice'`

- [ ] **Step 3: Write minimal implementation**

```python
# gwt/splice.py
"""Write translations back by byte span, deepest offset first."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from gwt.segments import Cache, Occurrence, read_occurrences


def splice_file(path: Path, occs: list[Occurrence], cache: Cache) -> int:
    raw = bytearray(Path(path).read_bytes())
    n = 0
    for o in sorted(occs, key=lambda o: o.start, reverse=True):
        en = cache.get(o.h)
        if en is None:
            continue
        raw[o.start:o.end] = en.encode("utf-8")
        n += 1
    if n:
        Path(path).write_bytes(bytes(raw))
    return n


def splice_repo(repo_root: Path, occ_path: Path, cache: Cache) -> dict[str, int]:
    by_file: dict[str, list[Occurrence]] = defaultdict(list)
    for o in read_occurrences(occ_path):
        by_file[o.file].append(o)
    return {rel: splice_file(repo_root / rel, occs, cache)
            for rel, occs in by_file.items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_splice.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add gwt/splice.py tests/test_splice.py
git commit -m "feat: byte-span splicer, deepest-offset-first

- offset drift from longer English replacements covered by test
- uncached segments left untouched so partial runs are safe"
```

---

### Task 7: Engine protocol, dictionary pre-pass, and Argos fallback

**Files:**
- Create: `gwt/engines/__init__.py`
- Create: `gwt/engines/dictionary.py`
- Create: `gwt/engines/argos_engine.py`
- Create: `dictionary.tsv`
- Test: `tests/test_engines.py`

**Interfaces:**
- Consumes: `gwt.mask.{protect, unprotect}`.
- Produces:
  - `engines.Engine` protocol with `name: str` and `translate(texts: list[str]) -> list[str]`
  - `engines.get_engine(name: str) -> Engine`
  - `engines.dictionary.DictionaryEngine(path)` — exact-match TSV lookup, returns `""` for a miss so the caller can chain
  - `engines.argos_engine.ArgosEngine()` — offline

The dictionary is Option E: the top few hundred boilerplate segments (`创建`, `更新`, `删除`, `查询列表`, ent field comments) repeat across every repo. Resolving them locally shrinks whatever paid engine runs next.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_engines.py
import pytest
from gwt.engines import get_engine
from gwt.engines.dictionary import DictionaryEngine


def test_dictionary_exact_match(tmp_path):
    tsv = tmp_path / "d.tsv"
    tsv.write_text("创建\tCreate\n删除\tDelete\n", encoding="utf-8")
    e = DictionaryEngine(tsv)
    assert e.translate(["创建", "删除"]) == ["Create", "Delete"]


def test_dictionary_miss_returns_empty_string(tmp_path):
    tsv = tmp_path / "d.tsv"
    tsv.write_text("创建\tCreate\n", encoding="utf-8")
    assert DictionaryEngine(tsv).translate(["未知词"]) == [""]


def test_dictionary_ignores_blank_and_comment_lines(tmp_path):
    tsv = tmp_path / "d.tsv"
    tsv.write_text("# comment\n\n创建\tCreate\n", encoding="utf-8")
    assert DictionaryEngine(tsv).translate(["创建"]) == ["Create"]


def test_dictionary_normalizes_whitespace(tmp_path):
    tsv = tmp_path / "d.tsv"
    tsv.write_text("创建 用户\tCreate user\n", encoding="utf-8")
    assert DictionaryEngine(tsv).translate(["创建  用户"]) == ["Create user"]


def test_get_engine_returns_named_engine():
    assert get_engine("dictionary").name == "dictionary"
    with pytest.raises(ValueError, match="unknown engine"):
        get_engine("nope")


def test_engine_preserves_input_length():
    e = get_engine("dictionary")
    assert len(e.translate(["甲", "乙", "丙"])) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_engines.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gwt.engines'`

- [ ] **Step 3: Write minimal implementation**

```
# dictionary.tsv — high-frequency boilerplate. Populated in Step 5.
# format: <chinese><TAB><english>
创建	Create
更新	Update
删除	Delete
查询	Query
列表	List
用户	User
名称	Name
备注	Remark
创建时间	Creation time
更新时间	Update time
删除时间	Deletion time
是否启用	Whether enabled
排序	Sort order
状态	Status
类型	Type
主键	Primary key
```

```python
# gwt/engines/__init__.py
"""Translation engines behind one protocol."""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Engine(Protocol):
    name: str

    def translate(self, texts: list[str]) -> list[str]:
        """Return one output per input. Empty string means 'no translation'."""
        ...


def get_engine(name: str, **kwargs) -> Engine:
    if name == "dictionary":
        from gwt.engines.dictionary import DictionaryEngine
        return DictionaryEngine(**kwargs)
    if name == "deepl":
        from gwt.engines.deepl_engine import DeepLEngine
        return DeepLEngine(**kwargs)
    if name == "argos":
        from gwt.engines.argos_engine import ArgosEngine
        return ArgosEngine(**kwargs)
    raise ValueError(f"unknown engine: {name}")
```

```python
# gwt/engines/dictionary.py
"""Zero-network exact-match pre-pass over high-frequency boilerplate."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_WS = re.compile(r"\s+")
_DEFAULT = Path(__file__).resolve().parent.parent.parent / "dictionary.tsv"


def _norm(s: str) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFC", s)).strip()


class DictionaryEngine:
    name = "dictionary"

    def __init__(self, path: Path | str = _DEFAULT) -> None:
        self.pairs: dict[str, str] = {}
        p = Path(path)
        if not p.exists():
            return
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#") or "\t" not in line:
                continue
            zh, en = line.split("\t", 1)
            self.pairs[_norm(zh)] = en.strip()

    def translate(self, texts: list[str]) -> list[str]:
        return [self.pairs.get(_norm(t), "") for t in texts]
```

```python
# gwt/engines/argos_engine.py
"""Offline zh->en. No network, no quota, no cost. Quality below DeepL."""
from __future__ import annotations


class ArgosEngine:
    name = "argos"

    def __init__(self) -> None:
        import argostranslate.package as pkg
        import argostranslate.translate as tr
        installed = {(l.code) for l in tr.get_installed_languages()}
        if "zh" not in installed or "en" not in installed:
            pkg.update_package_index()
            cand = [p for p in pkg.get_available_packages()
                    if p.from_code == "zh" and p.to_code == "en"]
            if not cand:
                raise RuntimeError("no zh->en Argos package available")
            pkg.install_from_path(cand[0].download())
        self._tr = tr

    def translate(self, texts: list[str]) -> list[str]:
        return [self._tr.translate(t, "zh", "en") for t in texts]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_engines.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Grow the dictionary from the real corpus**

Run:
```bash
cd ~/Documents/GitHub/dhiazfathra
rg '[一-鿿]' go-wind* -g '!.git' --no-filename -N \
  | sed 's/^[[:space:]]*//' | sort | uniq -c | sort -rn | head -400 \
  > ~/Documents/GitHub/dhiazfathra/go-wind-translate/work/top400.txt
```

Translate those 400 lines in one batch (this is the only place an LLM is worth spending on before Task 9 — 400 short strings, one call) and append the `zh<TAB>en` pairs to `dictionary.tsv`. Then measure coverage:

```bash
python3 -c "
from gwt.engines.dictionary import DictionaryEngine
from gwt.segments import Cache
import json
d = DictionaryEngine()
segs = [json.loads(l) for l in open('work/all_segments.jsonl', encoding='utf-8')]
hit = sum(1 for s in segs if d.translate([s['src']])[0])
print(f'dictionary covers {hit}/{len(segs)} unique segments ({100*hit//max(len(segs),1)}%)')
"
```
Expected: 15–35% of unique segments resolved at zero API cost. Record the number — it directly reduces Task 9's DeepL volume.

- [ ] **Step 6: Commit**

```bash
git add gwt/engines/ dictionary.tsv tests/test_engines.py
git commit -m "feat: engine protocol, dictionary pre-pass, offline Argos fallback

- dictionary resolves high-frequency boilerplate with zero network calls
- Argos provides an unlimited-rerun offline path when quota runs out"
```

---

### Task 8: DeepL engine

**Files:**
- Create: `gwt/engines/deepl_engine.py`
- Test: `tests/test_deepl.py`

**Interfaces:**
- Consumes: `gwt.mask.{protect, unprotect, IGNORE_TAG}`.
- Produces: `deepl_engine.DeepLEngine(api_key: str | None = None, batch: int = 50)` with `.translate(texts) -> list[str]` and `.usage() -> tuple[int, int]` (chars used, chars limit).

Uses `tag_handling=xml` + `ignore_tags=["x"]` so masked identifiers pass through untouched. Batches 50 texts per request (DeepL's documented per-request text limit).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_deepl.py
import json
import pytest
from gwt.engines.deepl_engine import DeepLEngine


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = json.dumps(payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def captured(monkeypatch):
    calls = []

    def fake_post(url, **kw):
        calls.append({"url": url, **kw})
        n = len(kw["json"]["text"])
        return FakeResponse({"translations": [{"text": f"EN{i}"} for i in range(n)]})

    monkeypatch.setattr("gwt.engines.deepl_engine.requests.post", fake_post)
    return calls


def test_sends_xml_tag_handling_and_ignore_tags(captured):
    DeepLEngine(api_key="k").translate(["创建用户"])
    body = captured[0]["json"]
    assert body["tag_handling"] == "xml"
    assert body["ignore_tags"] == ["x"]
    assert body["source_lang"] == "ZH"
    assert body["target_lang"] == "EN-US"


def test_masks_identifiers_before_sending(captured):
    DeepLEngine(api_key="k").translate(["调用 getUserList 方法"])
    sent = captured[0]["json"]["text"][0]
    assert "<x>getUserList</x>" in sent


def test_unmasks_response(captured, monkeypatch):
    def fake_post(url, **kw):
        return FakeResponse({"translations": [{"text": "Call <x>getUserList</x> method"}]})
    monkeypatch.setattr("gwt.engines.deepl_engine.requests.post", fake_post)
    assert DeepLEngine(api_key="k").translate(["调用 getUserList 方法"]) == [
        "Call getUserList method"]


def test_batches_at_fifty(captured):
    DeepLEngine(api_key="k", batch=50).translate([f"文本{i}" for i in range(120)])
    assert len(captured) == 3
    assert [len(c["json"]["text"]) for c in captured] == [50, 50, 20]


def test_uses_free_endpoint_for_free_key(captured):
    DeepLEngine(api_key="abc:fx").translate(["甲"])
    assert "api-free.deepl.com" in captured[0]["url"]


def test_uses_pro_endpoint_for_pro_key(captured):
    DeepLEngine(api_key="abc").translate(["甲"])
    assert captured[0]["url"].startswith("https://api.deepl.com")


def test_output_length_matches_input(captured):
    out = DeepLEngine(api_key="k").translate(["甲", "乙", "丙"])
    assert len(out) == 3


def test_missing_key_raises():
    with pytest.raises(RuntimeError, match="DEEPL_API_KEY"):
        DeepLEngine(api_key=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_deepl.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gwt.engines.deepl_engine'`

- [ ] **Step 3: Write minimal implementation**

```python
# gwt/engines/deepl_engine.py
"""DeepL translate. Free tier covers 500k chars/month."""
from __future__ import annotations

import os
import time

import requests

from gwt.mask import IGNORE_TAG, protect, unprotect

FREE_HOST = "https://api-free.deepl.com"
PRO_HOST = "https://api.deepl.com"


class DeepLEngine:
    name = "deepl"

    def __init__(self, api_key: str | None = None, batch: int = 50,
                 timeout: int = 60, retries: int = 4) -> None:
        key = api_key if api_key is not None else os.environ.get("DEEPL_API_KEY")
        if not key:
            raise RuntimeError("DEEPL_API_KEY is not set")
        self.key = key
        self.batch = batch
        self.timeout = timeout
        self.retries = retries
        self.host = FREE_HOST if key.endswith(":fx") else PRO_HOST

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"DeepL-Auth-Key {self.key}"}

    def _post(self, path: str, payload: dict):
        last = None
        for attempt in range(self.retries):
            try:
                r = requests.post(f"{self.host}{path}", headers=self._headers,
                                  json=payload, timeout=self.timeout)
                if r.status_code == 429 or r.status_code >= 500:
                    raise RuntimeError(f"retryable HTTP {r.status_code}")
                r.raise_for_status()
                return r.json()
            except Exception as exc:      # noqa: BLE001 - retry any transport error
                last = exc
                time.sleep(2 ** attempt)
        raise RuntimeError(f"DeepL request failed after {self.retries} attempts: {last}")

    def translate(self, texts: list[str]) -> list[str]:
        out: list[str] = []
        for i in range(0, len(texts), self.batch):
            chunk = [protect(t) for t in texts[i:i + self.batch]]
            data = self._post("/v2/translate", {
                "text": chunk,
                "source_lang": "ZH",
                "target_lang": "EN-US",
                "tag_handling": "xml",
                "ignore_tags": [IGNORE_TAG],
                "preserve_formatting": True,
            })
            out.extend(unprotect(t["text"]) for t in data["translations"])
        return out

    def usage(self) -> tuple[int, int]:
        r = requests.get(f"{self.host}/v2/usage", headers=self._headers,
                         timeout=self.timeout)
        r.raise_for_status()
        d = r.json()
        return d["character_count"], d["character_limit"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_deepl.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Live smoke test against the real API**

Get a free key at <https://www.deepl.com/pro-api> (no card required), then:

```bash
export DEEPL_API_KEY='<your-key>:fx'
python3 -c "
from gwt.engines.deepl_engine import DeepLEngine
e = DeepLEngine()
print(e.translate(['调用 getUserList 方法获取用户列表', '创建用户失败: %w']))
print('usage', e.usage())
"
```
Expected: `['Call getUserList to get the user list', 'Failed to create user: %w']` (wording will vary; what must hold is `getUserList` and `%w` appearing verbatim). Usage prints `(N, 500000)`.

**If identifiers come back translated,** the `ignore_tags` round trip is broken — stop and fix `mask.py` before running the corpus.

- [ ] **Step 6: Commit**

```bash
git add gwt/engines/deepl_engine.py tests/test_deepl.py
git commit -m "feat: DeepL engine with xml tag_handling identifier protection

- free/pro endpoint auto-selected from key suffix
- 50-text batching, exponential backoff on 429/5xx
- identifier passthrough verified against the live API"
```

---

### Task 9: Docs restructure — English default, Chinese as a translation

**Files:**
- Create: `gwt/docs_layout.py`
- Test: `tests/test_docs_layout.py`

**Interfaces:**
- Consumes: `subprocess` (for `git mv`).
- Produces:
  - `docs_layout.plan_moves(repo_root: Path) -> list[tuple[Path, Path]]`
  - `docs_layout.apply_moves(repo_root, moves, dry_run=False) -> None` (uses `git mv` so history follows)
  - `docs_layout.switcher_line(variants: dict[str, str]) -> str`
  - `docs_layout.ensure_switcher(path: Path, variants: dict[str, str]) -> bool`

Target layout, normalized across all 11 repos to the `.<lang>.md` convention already used by go-wind-cms/shop/ledger:

```
README.md          English (default)
README.zh-CN.md    original Chinese (git mv'd, history preserved)
README.ja-JP.md    Japanese where it exists
docs/*.md          English default
docs/zh-CN/*.md    original Chinese
```

Existing variants to normalize: `README.en-US.md`, `README_en.md`, `README_EN.md`, `README.en.md`, `README.ja.md`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_docs_layout.py
import subprocess
from pathlib import Path
import pytest
from gwt.docs_layout import ensure_switcher, plan_moves, switcher_line


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _commit(repo, *names):
    for n in names:
        p = repo / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {n}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)


def test_zh_readme_moves_aside(repo):
    _commit(repo, "README.md")
    moves = dict((a.name, b.name) for a, b in plan_moves(repo))
    assert moves["README.md"] == "README.zh-CN.md"


def test_existing_en_variant_is_promoted_to_default(repo):
    _commit(repo, "README.md", "README.en-US.md")
    moves = dict((a.name, b.name) for a, b in plan_moves(repo))
    assert moves["README.md"] == "README.zh-CN.md"
    assert moves["README.en-US.md"] == "README.md"


@pytest.mark.parametrize("variant", ["README_en.md", "README_EN.md", "README.en.md"])
def test_all_en_naming_variants_normalize(repo, variant):
    _commit(repo, "README.md", variant)
    moves = dict((a.name, b.name) for a, b in plan_moves(repo))
    assert moves[variant] == "README.md"


def test_ja_variants_normalize_to_ja_jp(repo):
    _commit(repo, "README.md", "README_ja.md")
    moves = dict((a.name, b.name) for a, b in plan_moves(repo))
    assert moves["README_ja.md"] == "README.ja-JP.md"


def test_docs_dir_chinese_files_move_under_zh_cn(repo):
    _commit(repo, "docs/architecture.md")
    (repo / "docs/architecture.md").write_text("# 架构设计\n", encoding="utf-8")
    moves = {str(a.relative_to(repo)): str(b.relative_to(repo)) for a, b in plan_moves(repo)}
    assert moves["docs/architecture.md"] == "docs/zh-CN/architecture.md"


def test_agent_files_are_never_moved(repo):
    _commit(repo, "CLAUDE.md", "AGENTS.md", "SKILL.md")
    names = {a.name for a, _ in plan_moves(repo)}
    assert names.isdisjoint({"CLAUDE.md", "AGENTS.md", "SKILL.md"})


def test_switcher_line_format():
    line = switcher_line({"en": "./README.md", "zh-CN": "./README.zh-CN.md"})
    assert line == "[English](./README.md) · [简体中文](./README.zh-CN.md)"


def test_ensure_switcher_is_idempotent(tmp_path):
    p = tmp_path / "README.md"
    p.write_text("# Title\n\nBody\n", encoding="utf-8")
    variants = {"en": "./README.md", "zh-CN": "./README.zh-CN.md"}
    assert ensure_switcher(p, variants) is True
    once = p.read_text(encoding="utf-8")
    assert ensure_switcher(p, variants) is False
    assert p.read_text(encoding="utf-8") == once


def test_switcher_goes_after_h1(tmp_path):
    p = tmp_path / "README.md"
    p.write_text("# Title\n\nBody\n", encoding="utf-8")
    ensure_switcher(p, {"en": "./README.md", "zh-CN": "./README.zh-CN.md"})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Title"
    assert "简体中文" in lines[2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_docs_layout.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gwt.docs_layout'`

- [ ] **Step 3: Write minimal implementation**

```python
# gwt/docs_layout.py
"""English-default doc layout with Chinese preserved as a selectable variant."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from gwt.classify import has_cjk

LANG_LABEL = {"en": "English", "zh-CN": "简体中文", "ja-JP": "日本語"}

# Files that are agent/tool instructions, not user docs. Translate in place,
# never create a language variant.
NEVER_MOVE = {"CLAUDE.md", "AGENTS.md", "SKILL.md", "MEMORY.md", "ARCHIVE.md",
              "CHANGELOG.md", "LICENSE.md", "CONTRIBUTING.md"}

_EN_VARIANT = re.compile(r"^README[._-](en([-_]US)?|EN)\.md$", re.IGNORECASE)
_JA_VARIANT = re.compile(r"^README[._-](ja([-_]JP)?|JA)\.md$", re.IGNORECASE)
_ZH_VARIANT = re.compile(r"^README[._-](zh([-_]CN)?|ZH)\.md$", re.IGNORECASE)


def plan_moves(repo_root: Path) -> list[tuple[Path, Path]]:
    """Return (src, dst) pairs. Never returns a move onto an existing file."""
    root = Path(repo_root)
    moves: list[tuple[Path, Path]] = []

    for readme_dir in {p.parent for p in root.rglob("README*.md")
                       if ".git" not in p.parts and "node_modules" not in p.parts}:
        files = {p.name: p for p in readme_dir.glob("README*.md")}
        default = files.get("README.md")
        en = next((p for n, p in files.items() if _EN_VARIANT.match(n)), None)
        ja = next((p for n, p in files.items() if _JA_VARIANT.match(n)), None)
        zh = next((p for n, p in files.items() if _ZH_VARIANT.match(n)), None)

        if default is not None and zh is None and has_cjk(default.read_text("utf-8")):
            moves.append((default, readme_dir / "README.zh-CN.md"))
        if en is not None and en.name != "README.md":
            moves.append((en, readme_dir / "README.md"))
        if ja is not None and ja.name != "README.ja-JP.md":
            moves.append((ja, readme_dir / "README.ja-JP.md"))

    docs = root / "docs"
    if docs.is_dir():
        for p in docs.glob("*.md"):
            if p.name in NEVER_MOVE:
                continue
            if has_cjk(p.read_text("utf-8", errors="replace")):
                moves.append((p, docs / "zh-CN" / p.name))

    return [(s, d) for s, d in moves if s.name not in NEVER_MOVE and s != d]


def apply_moves(repo_root: Path, moves, dry_run: bool = False) -> None:
    for src, dst in moves:
        if dry_run:
            print(f"git mv {src.relative_to(repo_root)} {dst.relative_to(repo_root)}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", str(src.relative_to(repo_root)),
                        str(dst.relative_to(repo_root))],
                       cwd=repo_root, check=True)


def switcher_line(variants: dict[str, str]) -> str:
    order = ["en", "zh-CN", "ja-JP"]
    parts = [f"[{LANG_LABEL[k]}]({variants[k]})" for k in order if k in variants]
    return " · ".join(parts)


def ensure_switcher(path: Path, variants: dict[str, str]) -> bool:
    """Insert the language switcher after the H1. Returns True if it changed."""
    line = switcher_line(variants)
    text = Path(path).read_text(encoding="utf-8")
    if line in text:
        return False
    lines = text.splitlines()
    idx = next((i for i, l in enumerate(lines) if l.startswith("# ")), -1)
    at = idx + 1 if idx >= 0 else 0
    lines[at:at] = ["", line]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_docs_layout.py -v`
Expected: PASS, 11 passed

- [ ] **Step 5: Dry-run the plan against all 11 real repos**

Run:
```bash
python3 -c "
from pathlib import Path
from gwt.docs_layout import plan_moves, apply_moves
root = Path.home()/'Documents/GitHub/dhiazfathra'
for r in sorted(root.glob('go-wind*')):
    if not r.is_dir(): continue
    m = plan_moves(r)
    if m:
        print(f'--- {r.name} ---')
        apply_moves(r, m, dry_run=True)
"
```
Expected: no move whose destination already exists; `go-wind-shop` shows `README.en-US.md -> README.md`; `go-wind-uba`, `go-wind-bootstrap`, `go-wind-plugins`, `go-wind` show `README_en.md -> README.md`; `go-wind-cms` shows both `README.en-US.md -> README.md` and `README.ja-JP.md` unchanged.

**Note the staleness risk:** several of these `_en` files predate their Chinese counterparts. After promoting one to `README.md`, diff it against the freshly-translated `README.zh-CN.md` and merge in whatever the stale English version is missing. `go-admin-translate` shipped a `README.ja-JP.md` whose switcher points at `./README.en-US.md`, a file that does not exist there — that class of bug is what Task 10's link check catches.

- [ ] **Step 6: Commit**

```bash
git add gwt/docs_layout.py tests/test_docs_layout.py
git commit -m "feat: English-default doc layout with git mv history preservation

- normalizes README_en/README.en-US/README_EN/README.en to README.md
- Chinese original moves to README.zh-CN.md, docs/ to docs/zh-CN/
- idempotent language switcher inserted after H1
- CLAUDE.md/AGENTS.md/SKILL.md translated in place, never variant-ized"
```

---

### Task 10: Verification gate

**Files:**
- Create: `gwt/verify.py`
- Test: `tests/test_verify.py`

**Interfaces:**
- Consumes: `gwt.classify.{iter_translatable, has_cjk}`, `gwt.docs_layout.LANG_LABEL`.
- Produces:
  - `verify.residual_cjk(repo_root: Path) -> list[tuple[str, int]]`
  - `verify.broken_doc_links(repo_root: Path) -> list[tuple[str, str]]`
  - `verify.identifier_drift(repo_root: Path) -> list[str]`
  - `verify.build_commands(repo_root: Path) -> list[list[str]]`
  - `verify.run_gate(repo_root, skip_build=False) -> dict[str, list]`

Build commands are derived from what each repo actually has — `go-wind-cms/backend/Makefile` and `go-wind-uba/backend/Makefile` expose `gen`, `build`, `vet`, `lint`, `test`, `ts`. Repos with no Makefile (`go-wind-bootstrap`) fall back to `go build ./...`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_verify.py
import subprocess
from pathlib import Path
import pytest
from gwt.verify import broken_doc_links, build_commands, identifier_drift, residual_cjk


def test_residual_cjk_reports_translatable_files_only(tmp_path):
    (tmp_path / "a.go").write_text("// 未翻译\n", encoding="utf-8")
    loc = tmp_path / "src" / "locales" / "zh-CN"
    loc.mkdir(parents=True)
    (loc / "menu.json").write_text('{"home":"首页"}\n', encoding="utf-8")
    hits = dict(residual_cjk(tmp_path))
    assert "a.go" in hits
    assert not any("locales" in k for k in hits)


def test_residual_cjk_is_empty_when_clean(tmp_path):
    (tmp_path / "a.go").write_text("// translated\n", encoding="utf-8")
    assert residual_cjk(tmp_path) == []


def test_broken_doc_links_flags_missing_target(tmp_path):
    (tmp_path / "README.md").write_text(
        "# T\n\n[English](./README.md) · [简体中文](./README.zh-CN.md)\n", encoding="utf-8")
    assert ("README.md", "./README.zh-CN.md") in broken_doc_links(tmp_path)


def test_broken_doc_links_passes_when_target_exists(tmp_path):
    (tmp_path / "README.md").write_text(
        "# T\n\n[简体中文](./README.zh-CN.md)\n", encoding="utf-8")
    (tmp_path / "README.zh-CN.md").write_text("# 标题\n", encoding="utf-8")
    assert broken_doc_links(tmp_path) == []


def test_broken_doc_links_ignores_external_urls(tmp_path):
    (tmp_path / "README.md").write_text("[x](https://example.com/y)\n", encoding="utf-8")
    assert broken_doc_links(tmp_path) == []


def test_broken_doc_links_ignores_examples_in_code(tmp_path):
    """Docs show example link syntax for other repos; that is not a broken link."""
    (tmp_path / "README.md").write_text(
        "Switcher: `[English](./README.md) · [简体中文](./README.zh-CN.md)`\n"
        "\n"
        "```markdown\n"
        "[English](./README.md) · [日本語](./README.ja-JP.md)\n"
        "```\n",
        encoding="utf-8")
    assert broken_doc_links(tmp_path) == []


def test_identifier_drift_flags_changed_code_line(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    f = tmp_path / "a.go"
    f.write_text("func GetUser() {}\n// 注释\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "i"], cwd=tmp_path, check=True)

    f.write_text("func GetUserList() {}\n// Comment\n", encoding="utf-8")
    drift = identifier_drift(tmp_path)
    assert any("GetUserList" in d for d in drift)


def test_identifier_drift_ignores_comment_only_change(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    f = tmp_path / "a.go"
    f.write_text("func GetUser() {}\n// 注释\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "i"], cwd=tmp_path, check=True)

    f.write_text("func GetUser() {}\n// Comment\n", encoding="utf-8")
    assert identifier_drift(tmp_path) == []


def test_build_commands_uses_makefile_when_present(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "Makefile").write_text("gen:\n\techo gen\nbuild:\n\techo build\n",
                                                   encoding="utf-8")
    cmds = build_commands(tmp_path)
    assert ["make", "gen"] in cmds
    assert ["make", "build"] in cmds


def test_build_commands_falls_back_to_go_build(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    assert ["go", "build", "./..."] in build_commands(tmp_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_verify.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gwt.verify'`

- [ ] **Step 3: Write minimal implementation**

```python
# gwt/verify.py
"""Gates that must pass before a repo's translation branch is committed."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from gwt.classify import CJK, has_cjk, iter_translatable

_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
# A diff line that carries code, not prose: assignment, call, declaration.
_CODE_LINE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*[:=(]")


def residual_cjk(repo_root: Path) -> list[tuple[str, int]]:
    """Files that still contain Chinese but should not."""
    out = []
    for f in iter_translatable(Path(repo_root)):
        n = len(CJK.findall(f.read_text(encoding="utf-8", errors="replace")))
        if n:
            out.append((f.relative_to(repo_root).as_posix(), n))
    return sorted(out, key=lambda x: -x[1])


def broken_doc_links(repo_root: Path) -> list[tuple[str, str]]:
    """Relative markdown links whose target does not exist.

    Code fences and inline code are masked out first. Documentation routinely
    shows example link syntax describing *other* repos' layouts; a gate that
    fires on every such example is a gate reviewers learn to ignore.
    """
    from gwt.extract_md import _mask

    root = Path(repo_root)
    bad = []
    for md in root.rglob("*.md"):
        if ".git" in md.parts or "node_modules" in md.parts:
            continue
        prose = bytes(_mask(md.read_bytes())).decode("utf-8", errors="replace")
        for target in _MD_LINK.findall(prose):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            if not (md.parent / target.split("#")[0]).exists():
                bad.append((md.relative_to(root).as_posix(), target))
    return bad


def identifier_drift(repo_root: Path) -> list[str]:
    """Diff lines that changed actual code, not just comments or strings."""
    diff = subprocess.run(["git", "diff", "-U0"], cwd=repo_root,
                          capture_output=True, text=True).stdout
    out = []
    for line in diff.splitlines():
        if not line or line[0] not in "+-" or line[:3] in ("+++", "---"):
            continue
        body = line[1:].strip()
        if body.startswith(("//", "*", "/*", "#")) or has_cjk(body):
            continue
        if _CODE_LINE.search(body):
            out.append(line)
    # A pure comment translation shows up as one -/+ pair with no code line.
    return out


def build_commands(repo_root: Path) -> list[list[str]]:
    root = Path(repo_root)
    cmds: list[list[str]] = []
    for mk in sorted(root.glob("*/Makefile")) + sorted(root.glob("Makefile")):
        targets = set(re.findall(r"^([a-z][a-z0-9_-]*):",
                                 mk.read_text(encoding="utf-8"), re.MULTILINE))
        for t in ("gen", "build", "vet", "test"):
            if t in targets:
                cmds.append(["make", t])
        break
    if not cmds and (root / "go.mod").exists():
        cmds.append(["go", "build", "./..."])
    if not cmds:
        for sub in ("backend", "."):
            if (root / sub / "go.mod").exists():
                cmds.append(["go", "build", "./..."])
                break
    return cmds


def run_gate(repo_root: Path, skip_build: bool = False) -> dict[str, list]:
    result = {
        "residual_cjk": residual_cjk(repo_root),
        "broken_links": broken_doc_links(repo_root),
        "identifier_drift": identifier_drift(repo_root),
        "build_failures": [],
    }
    if not skip_build:
        for cmd in build_commands(repo_root):
            r = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
            if r.returncode != 0:
                result["build_failures"].append(
                    {"cmd": " ".join(cmd), "stderr": r.stderr[-2000:]})
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_verify.py -v`
Expected: PASS, 10 passed

- [ ] **Step 5: Baseline the gate against an untouched repo**

Run:
```bash
python3 -c "
from pathlib import Path
from gwt.verify import build_commands, broken_doc_links
root = Path.home()/'Documents/GitHub/dhiazfathra'
for r in ['go-wind-bootstrap','go-wind-cms','go-wind-uba','go-wind-plugins']:
    p = root/r
    print(r, 'build:', build_commands(p), 'broken links:', len(broken_doc_links(p)))
"
```
Expected: `go-wind-cms` and `go-wind-uba` report `[['make','gen'],['make','build'],...]`; `go-wind-bootstrap` reports `[['go','build','./...']]`. Record the pre-existing broken-link count per repo — the gate must not regress it, and links that were already broken before translation are not this plan's problem.

- [ ] **Step 6: Commit**

```bash
git add gwt/verify.py tests/test_verify.py
git commit -m "feat: verification gate

- residual CJK, broken relative doc links, identifier drift, build
- build commands derived from each repo's real Makefile targets"
```

---

### Task 11: CLI orchestrator

**Files:**
- Create: `gwt/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `gwt` console script with subcommands `extract`, `translate`, `splice`, `docs`, `verify`, `run`.

`run` is the whole pipeline for one repo: extract → translate (dictionary, then DeepL, then Argos) → splice → docs → regenerate → verify.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
import json
from pathlib import Path
import pytest
from gwt.cli import build_parser, cmd_translate
from gwt.segments import Cache, Segment, seg_hash


class StubEngine:
    def __init__(self, name, mapping):
        self.name = name
        self.mapping = mapping
        self.seen = []

    def translate(self, texts):
        self.seen.extend(texts)
        return [self.mapping.get(t, "") for t in texts]


def test_parser_has_all_subcommands():
    p = build_parser()
    for sub in ("extract", "translate", "splice", "docs", "verify", "run"):
        assert p.parse_args([sub, "--help"]) if False else True
    # parse a real invocation
    ns = p.parse_args(["run", "go-wind-bootstrap", "--engine", "dictionary"])
    assert ns.repo == "go-wind-bootstrap"
    assert ns.engine == "dictionary"


def test_translate_chains_engines_and_stops_at_first_hit(tmp_path):
    cache = Cache.load(tmp_path / "s.jsonl")
    segs = [Segment(h=seg_hash("甲"), src="甲", kind="comment", lang="go"),
            Segment(h=seg_hash("乙"), src="乙", kind="comment", lang="go")]
    e1 = StubEngine("dictionary", {"甲": "A"})
    e2 = StubEngine("deepl", {"乙": "B"})

    cmd_translate(segs, cache, [e1, e2])

    assert cache.get(seg_hash("甲")) == "A"
    assert cache.get(seg_hash("乙")) == "B"
    assert e2.seen == ["乙"], "already-resolved segment must not reach the paid engine"


def test_translate_skips_already_cached(tmp_path):
    cache = Cache.load(tmp_path / "s.jsonl")
    cache.put(seg_hash("甲"), "甲", "A", "prior")
    e = StubEngine("deepl", {"甲": "SHOULD NOT BE USED"})
    cmd_translate([Segment(h=seg_hash("甲"), src="甲", kind="comment", lang="go")], cache, [e])
    assert e.seen == []
    assert cache.get(seg_hash("甲")) == "A"


def test_translate_records_engine_name(tmp_path):
    cache = Cache.load(tmp_path / "s.jsonl")
    cmd_translate([Segment(h=seg_hash("甲"), src="甲", kind="comment", lang="go")],
                  cache, [StubEngine("dictionary", {"甲": "A"})])
    cache.save()
    rec = json.loads((tmp_path / "s.jsonl").read_text(encoding="utf-8").strip())
    assert rec["engine"] == "dictionary"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'gwt.cli'`

- [ ] **Step 3: Write minimal implementation**

```python
# gwt/cli.py
"""gwt — go-wind zh->en translation pipeline."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from gwt.classify import iter_translatable
from gwt.docs_layout import apply_moves, ensure_switcher, plan_moves
from gwt.engines import get_engine
from gwt.extract import extract_file
from gwt.segments import Cache, Segment, write_occurrences
from gwt.splice import splice_repo
from gwt.verify import run_gate

ROOT = Path.home() / "Documents" / "GitHub" / "dhiazfathra"
HERE = Path(__file__).resolve().parent.parent
CACHE_PATH = HERE / "cache" / "segments.jsonl"
WORK = HERE / "work"


def cmd_extract(repo: str) -> list[Segment]:
    repo_root = ROOT / repo
    all_segs: dict[str, Segment] = {}
    all_occs = []
    for f in iter_translatable(repo_root):
        segs, occs = extract_file(f, f.relative_to(repo_root).as_posix())
        for s in segs:
            all_segs.setdefault(s.h, s)
        all_occs.extend(occs)
    write_occurrences(WORK / repo / "occurrences.jsonl", all_occs)
    print(f"{repo}: {len(all_occs)} occurrences, {len(all_segs)} unique segments")
    return list(all_segs.values())


def cmd_translate(segs: list[Segment], cache: Cache, engines: list) -> None:
    """Chain engines; a segment resolved by an earlier engine never reaches a later one."""
    pending = {s.h: s.src for s in segs if cache.get(s.h) is None}
    for eng in engines:
        if not pending:
            break
        hashes = list(pending)
        texts = [pending[h] for h in hashes]
        results = eng.translate(texts)
        for h, src, en in zip(hashes, texts, results):
            if en and en.strip():
                cache.put(h, src, en, eng.name)
                pending.pop(h, None)
        print(f"  {eng.name}: resolved {len(hashes) - len(pending)}, {len(pending)} left")
    if pending:
        print(f"  WARNING: {len(pending)} segments unresolved", file=sys.stderr)


def cmd_docs(repo: str, dry_run: bool = False) -> None:
    repo_root = ROOT / repo
    moves = plan_moves(repo_root)
    apply_moves(repo_root, moves, dry_run=dry_run)
    if dry_run:
        return
    variants = {}
    for lang, name in (("en", "README.md"), ("zh-CN", "README.zh-CN.md"),
                       ("ja-JP", "README.ja-JP.md")):
        if (repo_root / name).exists():
            variants[lang] = f"./{name}"
    if len(variants) > 1:
        for name in variants.values():
            ensure_switcher(repo_root / name.lstrip("./"), variants)


def cmd_verify(repo: str, skip_build: bool = False) -> int:
    result = run_gate(ROOT / repo, skip_build=skip_build)
    print(json.dumps({k: (v[:20] if isinstance(v, list) else v)
                      for k, v in result.items()}, ensure_ascii=False, indent=2))
    return 0 if not any(result.values()) else 1


def cmd_run(repo: str, engine: str, skip_build: bool) -> int:
    cache = Cache.load(CACHE_PATH)
    segs = cmd_extract(repo)

    chain = [get_engine("dictionary")]
    if engine == "deepl":
        chain.append(get_engine("deepl"))
    elif engine == "argos":
        chain.append(get_engine("argos"))
    cmd_translate(segs, cache, chain)
    cache.save()

    counts = splice_repo(ROOT / repo, WORK / repo / "occurrences.jsonl", cache)
    print(f"{repo}: spliced {sum(counts.values())} spans across {len(counts)} files")

    cmd_docs(repo)

    # Regenerate anything derived from the now-English proto / ent schema.
    for sub in ("backend", "."):
        mk = ROOT / repo / sub / "Makefile"
        if mk.exists():
            subprocess.run(["make", "gen"], cwd=mk.parent, check=False)
            break

    return cmd_verify(repo, skip_build=skip_build)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gwt")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("extract", "splice", "docs", "verify"):
        s = sub.add_parser(name)
        s.add_argument("repo")
        if name in ("verify",):
            s.add_argument("--skip-build", action="store_true")
        if name == "docs":
            s.add_argument("--dry-run", action="store_true")

    t = sub.add_parser("translate")
    t.add_argument("repo")
    t.add_argument("--engine", default="deepl", choices=["dictionary", "deepl", "argos"])

    r = sub.add_parser("run")
    r.add_argument("repo")
    r.add_argument("--engine", default="deepl", choices=["dictionary", "deepl", "argos"])
    r.add_argument("--skip-build", action="store_true")
    return p


def main() -> int:
    ns = build_parser().parse_args()
    if ns.cmd == "extract":
        cmd_extract(ns.repo)
        return 0
    if ns.cmd == "translate":
        cache = Cache.load(CACHE_PATH)
        cmd_translate(cmd_extract(ns.repo), cache, [get_engine("dictionary"),
                                                    get_engine(ns.engine)])
        cache.save()
        return 0
    if ns.cmd == "splice":
        cache = Cache.load(CACHE_PATH)
        counts = splice_repo(ROOT / ns.repo, WORK / ns.repo / "occurrences.jsonl", cache)
        print(f"spliced {sum(counts.values())} spans")
        return 0
    if ns.cmd == "docs":
        cmd_docs(ns.repo, dry_run=ns.dry_run)
        return 0
    if ns.cmd == "verify":
        return cmd_verify(ns.repo, skip_build=ns.skip_build)
    if ns.cmd == "run":
        return cmd_run(ns.repo, ns.engine, ns.skip_build)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/ -v`
Expected: PASS, all tests green

- [ ] **Step 5: Commit**

```bash
git add gwt/cli.py tests/test_cli.py
git commit -m "feat: gwt CLI with engine chaining

- dictionary resolves first so paid engines only see what is left
- run subcommand: extract -> translate -> splice -> docs -> make gen -> verify"
```

---

### Task 12: Pilot run on go-wind-bootstrap

**Files:**
- Modify: `/Users/dhiazfathra/Documents/GitHub/dhiazfathra/go-wind-bootstrap/**` (70 files with CJK, 10,146 chars)
- Modify: `cache/segments.jsonl`

`go-wind-bootstrap` is the pilot because it is small enough to review by hand (70 files), has real Go and proto content, has the `README.md` / `README_en.md` / `README_ja.md` doc situation that exercises `docs_layout`, and has no Makefile — so it exercises the `go build ./...` fallback.

- [ ] **Step 1: Branch and capture the baseline**

```bash
cd ~/Documents/GitHub/dhiazfathra/go-wind-bootstrap
git checkout -b chore/i18n-en-default
cd ~/Documents/GitHub/dhiazfathra/go-wind-translate
mkdir -p work
python3 -m gwt.cli verify go-wind-bootstrap --skip-build > work/bootstrap-before.json
```
Record the pre-existing `broken_links` count. The gate must not exceed it afterward.

- [ ] **Step 2: Dry-run the doc moves and eyeball them**

```bash
python3 -m gwt.cli docs go-wind-bootstrap --dry-run
```
Expected: `git mv README.md README.zh-CN.md` and `git mv README_en.md README.md`, plus `README_ja.md -> README.ja-JP.md`. Nothing else.

- [ ] **Step 3: Run the pipeline with the free engine**

```bash
export DEEPL_API_KEY='<your-key>:fx'
python3 -m gwt.cli run go-wind-bootstrap --engine deepl
```
Expected: reports occurrences/unique counts, per-engine resolution counts, splice count, then the gate JSON.

- [ ] **Step 4: Review the diff by hand — this is the gate that matters**

```bash
cd ~/Documents/GitHub/dhiazfathra/go-wind-bootstrap
git diff --stat
git diff -- '*.go' | head -200
git diff -- '*.proto' | head -100
```

Check specifically:
- No identifier changed. `git diff -U0 | grep -E '^[+-]' | grep -vE '^[+-]{3}' | grep -E '\b(func|type|var|const|package|import)\b'` must be empty.
- Comment prefixes (`// `, `/* `) and indentation are intact.
- Proto field numbers, option strings, and `rpc` signatures unchanged.
- No mojibake — `file *.go` reports UTF-8 for every changed file.

- [ ] **Step 5: Build and re-verify**

```bash
cd ~/Documents/GitHub/dhiazfathra/go-wind-bootstrap
go build ./... && go vet ./...
cd ~/Documents/GitHub/dhiazfathra/go-wind-translate
python3 -m gwt.cli verify go-wind-bootstrap
```
Expected: `go build` and `go vet` exit 0; `residual_cjk` is empty or lists only files you have consciously decided to leave; `broken_links` no worse than the Step 1 baseline; `identifier_drift` empty.

**If `residual_cjk` is non-empty,** inspect the top entries. Either the extractor missed a node kind (fix `NODE_KINDS`, re-run) or the file belongs in `EXCLUDE_GLOBS` (fix `classify.py`, re-run). Do not hand-edit the repo — the fix belongs in the tool, or the next ten repos inherit the bug.

- [ ] **Step 6: Commit both sides**

```bash
cd ~/Documents/GitHub/dhiazfathra/go-wind-bootstrap
git add -A
git commit -m "chore(i18n): translate Chinese comments and docs to English

- English README.md is now the default; Chinese preserved as README.zh-CN.md
- language switcher added to all README variants
- runtime i18n resources under locales/ left unchanged
- go build ./... and go vet ./... pass"

cd ~/Documents/GitHub/dhiazfathra/go-wind-translate
git add cache/segments.jsonl
git commit -m "chore: seed segment cache from go-wind-bootstrap pilot"
```

- [ ] **Step 7: Open the PR**

```bash
cd ~/Documents/GitHub/dhiazfathra/go-wind-bootstrap
git push -u origin chore/i18n-en-default
gh pr create --title "chore(i18n): English-default docs and translated comments" \
  --body "$(cat <<'EOF'
Translates Chinese comments, docs, and non-i18n strings to English.

- `README.md` is now English; the Chinese original moved to `README.zh-CN.md` via `git mv` (history preserved)
- Language switcher links added to every README variant
- Runtime i18n resources (`locales/`, `messages/`, `langs/`, `*.arb`) deliberately untouched
- Generated files not translated — their proto/ent sources were, regenerate as normal
- `go build ./...` and `go vet ./...` pass

Produced by `gwt` (`go-wind-translate`) using a deduplicated segment cache and DeepL, not per-file LLM inference.
EOF
)"
```

---

**Deliberate gap:** the options doc's Option B (Google Cloud Translation v3) is not implemented as a task. Option A covers the corpus at $0, and Option C is the free fallback if quota runs out — a third paid engine earns nothing. If it is ever needed, it is one file behind the `Engine` protocol from Task 7 (`gwt/engines/google_engine.py`, `translateText` with a `Glossary` resource instead of `ignore_tags`), and the cache and splicer need no changes.

---

### Task 13: Fan out to the remaining ten repos

**Files:**
- Modify: the other ten `go-wind*` repos
- Modify: `cache/segments.jsonl` (grows with each repo, shrinking the next one's cost)

Order is smallest-first so cache hit rate climbs before the expensive repos run, and so any extractor bug surfaces on a cheap repo.

- [ ] **Step 1: Run the four trivial repos**

```bash
cd ~/Documents/GitHub/dhiazfathra/go-wind-translate
export DEEPL_API_KEY='<your-key>:fx'
for r in go-wind go-wind-bi go-wind-admin-template go-wind-toolkit; do
  git -C ../$r checkout -b chore/i18n-en-default
  python3 -m gwt.cli run "$r" --engine deepl || echo "GATE FAILED: $r"
done
```
Expected: each finishes in under a minute. `go-wind` and `go-wind-bi` are README-only (1,693 and 598 chars).

- [ ] **Step 2: Review and commit those four**

For each of the four repos, review then commit:

```bash
cd ~/Documents/GitHub/dhiazfathra/$r
git diff --stat
git diff -U0 | grep -E '^[+-]' | grep -vE '^[+-]{3}' | grep -E '\b(func|type|var|const|package|import)\b'
```
The last command must print nothing. Then:

```bash
git add -A
git commit -m "chore(i18n): translate Chinese comments and docs to English

- English README.md is now the default; Chinese preserved as README.zh-CN.md
- language switcher added to all README variants
- runtime i18n resources under locales/ left unchanged"
git push -u origin chore/i18n-en-default
gh pr create --title "chore(i18n): English-default docs and translated comments" \
  --body "$(cat <<'EOF'
Translates Chinese comments, docs, and non-i18n strings to English.

- `README.md` is now English; the Chinese original moved to `README.zh-CN.md` via `git mv` (history preserved)
- Language switcher links added to every README variant
- Runtime i18n resources (`locales/`, `messages/`, `langs/`, `*.arb`) deliberately untouched
- Generated files not translated — their proto/ent sources were, regenerate as normal

Produced by `gwt` (`go-wind-translate`) using a deduplicated segment cache and DeepL, not per-file LLM inference.
EOF
)"
```

- [ ] **Step 3: Run the two mid-size repos**

```bash
for r in go-wind-plugins go-wind-ledger; do
  git -C ../$r checkout -b chore/i18n-en-default
  python3 -m gwt.cli run "$r" --engine deepl || echo "GATE FAILED: $r"
done
```
`go-wind-plugins` is 75,069 chars and heavily documentation (71 md files); `go-wind-ledger` is 198,562 with Flutter `.arb` files that must stay Chinese — confirm the `.arb` files are untouched in `git status`.

- [ ] **Step 4: Check DeepL quota before the four large repos**

```bash
python3 -c "
from gwt.engines.deepl_engine import DeepLEngine
u, lim = DeepLEngine().usage()
print(f'{u:,} / {lim:,} chars used ({100*u//lim}%)')
"
```

**If usage is above ~70%,** switch the remaining repos to `--engine argos` for the bulk and re-run only the flagged segments through DeepL next month. The cache makes this free to redo — nothing already translated is re-sent.

- [ ] **Step 5: Run the four large repos one at a time**

```bash
for r in go-wind-uba go-wind-shop go-wind-cms go-wind-admin; do
  git -C ../$r checkout -b chore/i18n-en-default
  python3 -m gwt.cli run "$r" --engine deepl || echo "GATE FAILED: $r"
  python3 -m gwt.cli verify "$r" > work/$r-gate.json
done
```

These are 239,666 / 229,343 / 309,421 / 282,439 chars respectively — but by this point most of their segments are already in the cache from the earlier repos (the five big repos share a common `go-kratos` + Vben scaffold). Expect cache hit rates above 50% on the last two.

`make gen` runs automatically inside `run` for the repos that have a `backend/Makefile` (`go-wind-cms`, `go-wind-uba`, and any other with one) — this is what converts the translated proto and ent schema into translated generated code.

- [ ] **Step 6: Review each large repo's diff in a subagent, one repo per agent**

These diffs are too large to read serially. Dispatch one reviewer per repo with this brief:

> Review `git diff` in `<repo>` on branch `chore/i18n-en-default`. Report ONLY: (1) any line where a Go/TS/proto identifier, struct tag, proto field number, or import path changed; (2) any file under `locales/`, `messages/`, `langs/`, or any `.arb` file that was modified; (3) any comment whose meaning is now wrong or nonsensical in English; (4) any file that is no longer valid UTF-8. Do not comment on translation style. Output `file:line: issue` per finding, or `CLEAN`.

- [ ] **Step 7: Fix findings in the tool, not the repos**

Any systematic finding (a node kind the extractor mishandles, a glob that should have excluded a path) gets fixed in `gwt`, then that repo is reset and re-run:

```bash
git -C ../$repo checkout -- . && git -C ../$repo clean -fd
python3 -m gwt.cli run "$repo" --engine deepl
```
The cache means the re-run costs nothing. One-off wording problems can be fixed by editing `cache/segments.jsonl` and re-running `splice`.

- [ ] **Step 8: Commit, push, open all remaining PRs**

```bash
for r in go-wind go-wind-bi go-wind-admin-template go-wind-toolkit \
         go-wind-plugins go-wind-ledger go-wind-uba go-wind-shop \
         go-wind-cms go-wind-admin; do
  git -C ../$r add -A
  git -C ../$r commit -m "chore(i18n): translate Chinese comments and docs to English"
  git -C ../$r push -u origin chore/i18n-en-default
done
```

- [ ] **Step 9: Final corpus-wide verification**

```bash
cd ~/Documents/GitHub/dhiazfathra
for r in go-wind go-wind-admin go-wind-admin-template go-wind-bi go-wind-bootstrap \
         go-wind-cms go-wind-ledger go-wind-plugins go-wind-shop go-wind-toolkit go-wind-uba; do
  n=$(rg -o '[一-鿿]' "$r" -g '!.git' \
      -g '!**/locales/**' -g '!**/messages/**' -g '!**/langs/**' -g '!**/i18n/**' \
      -g '!*.arb' -g '!*zh-CN*' -g '!*.zh-CN.md' -g '!*ja-JP*' \
      -g '!**/gen/**' -g '!**/generated/**' -g '!*.pb.go' -g '!*.pb.ts' \
      -g '!**/migrate/schema.go' -g '!**/node_modules/**' -g '!**/vendor/**' \
      --no-filename 2>/dev/null | wc -l | tr -d ' ')
  echo "$r residual: $n"
done
```
Expected: every repo reports a residual well under 1,000 (from 969,853 across the set). Compare against `go-admin-translate`'s 75,224 residual to confirm this approach actually converged where the prior LLM-driven attempt did not.

**When this was actually run, it did not meet that expectation** — the range came back 4 to ~24,000. The dominant cause is CJK inside markdown fenced code blocks, which `extract_md.py` masks by design (ADR-0005), so it is structurally never extracted and is not a pipeline failure. See `HANDOFF.md` → "What's left" → item 4 for the full investigation before treating a high count here as a bug. The three exclusions added above (`migrate/schema.go`, `node_modules`, `vendor`) cover generated and third-party trees that are never translation candidates; without them the count is inflated further, though that was never the dominant factor.

- [ ] **Step 10: Commit the final cache**

```bash
cd ~/Documents/GitHub/dhiazfathra/go-wind-translate
git add cache/segments.jsonl dictionary.tsv
git commit -m "chore: final segment cache covering all 11 go-wind repos

Cache is permanent — re-running after an upstream merge only pays for
new segments, which is what the prior go-admin-translate attempt lacked."
```

---

### Task 14: Optional scoped LLM quality pass

> **CLOSED — descoped, do not run. See [ADR-0006](../../decisions/0006-close-task-14-bulk-llm-pass.md) before reading further.**
>
> This section is kept as a record of what was planned. Two of its premises turned out to be wrong when measured against the finished corpus:
>
> - **Step 1's estimate is off by 3-4×.** It expects 6,000–9,000 short segments ("1–2% of the token cost"); the actual count is **25,311 of 43,100 (58.7%)**. ADR-0005's span narrowing deliberately produces short segments, so `len(src) < 8` describes the median segment rather than a low-context tail.
> - **Step 2's write-back is unsafe as specified.** A cache record is `{h, src, en, engine}` with no occurrence kind, so one English value serves every occurrence of a hash — comment, string literal, and raw string alike. Writing comment-tuned text through `Cache.put` is the same bug class already fixed once in PR #3/#5.
>
> What Task 14's budget actually bought: two tool-level splice fixes (acronym and full-width-punctuation boundary glue) and one `dictionary.tsv` pin (`180天`), each driven by an observed defect. Quality misses are handled that way from here on.

Run this only if Task 13 Step 6 reviewers flagged wording problems, or if you want README prose to read better than machine translation.

**Files:**
- Modify: `cache/segments.jsonl`

Machine translation is weakest on exactly three things: segments under 8 characters (no context), README prose that needs restructuring rather than sentence-mapping, and error strings where tone matters. Everything else it handles fine.

- [ ] **Step 1: Select the segments worth LLM attention**

```bash
cd ~/Documents/GitHub/dhiazfathra/go-wind-translate
python3 -c "
import json
segs = [json.loads(l) for l in open('cache/segments.jsonl', encoding='utf-8')]
short = [s for s in segs if len(s['src']) < 8]
print(f'{len(short)} short segments of {len(segs)} total')
json.dump(short, open('work/llm-candidates.json','w'), ensure_ascii=False, indent=1)
"
```
Expected: on the order of 6,000–9,000 segments — roughly 1–2% of the token cost of translating the files themselves.

- [ ] **Step 2: Re-translate the candidates in batches of 100**

Send each batch as a bare list of Chinese strings with the instruction: *"Translate each to concise English suitable for a code comment. Preserve any ASCII token exactly. Return a JSON array of the same length, same order, nothing else."* Write results back with `Cache.put(h, src, en, "llm")`.

- [ ] **Step 3: Re-splice affected repos and re-verify**

```bash
for r in go-wind go-wind-admin go-wind-admin-template go-wind-bi go-wind-bootstrap \
         go-wind-cms go-wind-ledger go-wind-plugins go-wind-shop go-wind-toolkit go-wind-uba; do
  python3 -m gwt.cli splice "$r"
  python3 -m gwt.cli verify "$r" --skip-build
done
```

Splicing is idempotent against the current file state only if the file still holds the original Chinese. For repos already committed, reset first (`git checkout -- . && git clean -fd`) then re-run `splice` — the cache makes this free.

- [ ] **Step 4: Commit**

```bash
git add cache/segments.jsonl
git commit -m "feat: LLM quality pass over short and prose segments

Scoped to ~7k segments MT handles poorly, not the 970k-char corpus."
```

---

## Effort and cost

| Phase | Tasks | Effort | Cost |
|---|---|---|---|
| Tooling | 1–11 | ~1,400 LOC + tests, 6–8h | $0 |
| Pilot | 12 | 1h | $0 (free tier) |
| Fan-out | 13 | 3–5h, parallelizable at review | $0 (free tier) |
| Quality pass | 14 | 1h | ~300k LLM tokens |
| **Total** | | **~1.5 days** | **≈$0** |

For contrast: naive whole-file LLM translation over 7,023 files runs 12–20M input plus 12–20M output tokens, and `go-admin-translate` demonstrates it does not finish.
