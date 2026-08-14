"""English-default doc layout with Chinese preserved as a selectable variant."""
from __future__ import annotations

import re
import shutil
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
    # Sources that something else in this batch will move onto — an `en`
    # variant being promoted to README.md, say. Recreating the archived
    # file at that same path would collide with the later promote move.
    incoming_dsts = {d for _, d in moves}
    for src, dst in moves:
        if dry_run:
            print(f"git mv {src.relative_to(repo_root)} {dst.relative_to(repo_root)}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "mv", str(src.relative_to(repo_root)),
                        str(dst.relative_to(repo_root))],
                       cwd=repo_root, check=True)
        # Archival move (default doc -> a zh-CN-named backup): recreate the
        # original at its old path so extraction/translation can still turn
        # it into the English default. The zh-CN copy is left untouched from
        # here on, which is what preserves the original Chinese. Skipped
        # when another move in this batch (e.g. an `en` variant) is about
        # to be promoted onto that same path instead.
        is_archival = "zh-CN" in dst.relative_to(repo_root).parts or "zh-CN" in dst.name
        if is_archival and src not in incoming_dsts:
            shutil.copy2(dst, src)
            subprocess.run(["git", "add", str(src.relative_to(repo_root))],
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
    idx = next((i for i, ln in enumerate(lines) if ln.startswith("# ")), -1)
    at = idx + 1 if idx >= 0 else 0
    lines[at:at] = ["", line]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True
