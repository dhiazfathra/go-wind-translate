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
    "*README*.ja*", "*README*_ja*", "*README*_JA*",
    "*README*.zh*", "*README*_zh*", "*README*_ZH*",
    "*README.en*", "*README_en*", "*README_EN*",
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
