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
import subprocess
from pathlib import Path

from gwt.repair import _GLOSSED

MIN_LITERAL = 6  # shorter `before` values collide with unrelated English


def _safe_literal(before: str) -> bool:
    """A pair is only safe to apply by text search if it is a multi-word phrase.

    A single word matches identifiers as readily as prose: propagating
    "Execute" -> "Enforcement" rewrote a Go call site to `root.Enforcement()`.
    Prose the splicer wrote is almost always more than one word; single-word
    pairs are reported instead, for a human to place.
    """
    return len(before) >= MIN_LITERAL and " " in before.strip()

SKIP_DIRS = {
    ".git", "node_modules", "gen", "generated", "locales", "messages", "langs",
    "i18n", "dist", "build", "vendor", ".venv", "__pycache__",
}
# The review document quotes the bad translations as evidence; repairing it in
# place would erase the record of what was wrong.
SKIP_FILE = re.compile(
    r"(\.pb\.(go|ts)$|zh-CN|migrate/schema\.go$|wire_gen\.go$|ZH_EN_TRANSLATION_REVIEW\.md$)"
)
TEXT_SUFFIXES = {
    ".go", ".proto", ".ts", ".tsx", ".js", ".jsx", ".vue", ".md", ".scss", ".css",
    ".sql", ".yaml", ".yml", ".sh", ".ps1", ".cs", ".dart", ".json",
}


def target_files(repo: Path):
    """Tracked files only.

    Walking the tree also finds untracked tooling state (`.tokensave/config.json`
    was the one that caught this), which the splicer never wrote and which no
    diff would show. `git ls-files` is the authoritative list of what this
    pipeline is allowed to have produced.
    """
    listing = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout
    for rel in filter(None, listing.split("\0")):
        p = repo / rel
        if not p.is_file() or p.suffix not in TEXT_SUFFIXES:
            continue
        if SKIP_DIRS & set(Path(rel).parts):
            continue
        if SKIP_FILE.search(rel):
            continue
        yield p


def propagate(repo: Path, changed: list[dict]) -> tuple[int, int, list[dict]]:
    """Apply before→after pairs across the repo.

    Returns (files_touched, replacements, skipped_pairs).
    """
    # One English string can be the repair target of several different segments:
    # 错误的请求, 不可接受的请求 and 错误请求 all came back as "Invalid Request", and
    # text search cannot tell which occurrence is which. Ambiguous pairs are
    # reported, never guessed at.
    targets: dict[str, set[str]] = {}
    for c in changed:
        targets.setdefault(c["before"], set()).add(c["after"])
    def usable(c: dict) -> bool:
        return (
            _safe_literal(c["before"])
            and len(targets[c["before"]]) == 1
            and not c.get("ambiguous")
        )

    pairs = [(c["before"], c["after"]) for c in changed if usable(c)]
    skipped = [c for c in changed if not usable(c)]
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
            # A span can end mid-phrase (会话（ spliced as "Conversation ("), so
            # correcting the term can leave the gloss restating it.
            text = _GLOSSED.sub(r"\1", text)
            path.write_text(text, encoding="utf-8")
            files_touched += 1
    return files_touched, replacements, skipped
