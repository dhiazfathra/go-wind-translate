"""Push repaired cache values into an already-translated target repo.

A normal re-run would re-splice from `work/<repo>/occurrences.jsonl`, but those
byte spans were recorded against the *Chinese* tree. On a branch that is already
translated there is no Chinese left to match, so the spans are gone.

What survives is the spliced English itself. Every repaired cache record gives an
exact before/after pair for text this pipeline wrote, so replacing `before` with
`after` literally is the same edit the splicer would have made — no offsets, no
re-parse. Short strings are skipped rather than risked: they collide with prose
the pipeline never wrote.
"""

from __future__ import annotations

import re
from pathlib import Path

MIN_LITERAL = 6  # shorter `before` values collide with unrelated English

SKIP_DIRS = {
    ".git", "node_modules", "gen", "generated", "locales", "messages", "langs",
    "i18n", "dist", "build", "vendor", ".venv", "__pycache__",
}
SKIP_FILE = re.compile(r"(\.pb\.(go|ts)$|zh-CN|migrate/schema\.go$|wire_gen\.go$)")
TEXT_SUFFIXES = {
    ".go", ".proto", ".ts", ".tsx", ".js", ".jsx", ".vue", ".md", ".scss", ".css",
    ".sql", ".yaml", ".yml", ".sh", ".ps1", ".cs", ".dart", ".json",
}


def target_files(repo: Path):
    for p in repo.rglob("*"):
        if not p.is_file() or p.suffix not in TEXT_SUFFIXES:
            continue
        if SKIP_DIRS & set(p.relative_to(repo).parts):
            continue
        if SKIP_FILE.search(str(p.relative_to(repo))):
            continue
        yield p


def propagate(repo: Path, changed: list[dict]) -> tuple[int, int, list[dict]]:
    """Apply before→after pairs across the repo.

    Returns (files_touched, replacements, skipped_pairs).
    """
    pairs = [(c["before"], c["after"]) for c in changed if len(c["before"]) >= MIN_LITERAL]
    skipped = [c for c in changed if len(c["before"]) < MIN_LITERAL]
    files_touched = replacements = 0
    for path in target_files(repo):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        original = text
        for before, after in pairs:
            if before in text:
                replacements += text.count(before)
                text = text.replace(before, after)
        if text != original:
            path.write_text(text, encoding="utf-8")
            files_touched += 1
    return files_touched, replacements, skipped
