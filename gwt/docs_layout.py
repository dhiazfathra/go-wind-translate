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

# A README *filename*, not the bare word: "[README](./README.md)" is one
# link to one file and must count once, not twice (link text + href).
_README_FILENAME = re.compile(r"README[\w.-]*\.md", re.IGNORECASE)


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


_SWITCHER_LINK = re.compile(r"^\[[^\]]+\]\([^)]+\)$")


def _looks_like_label(segment: str) -> bool:
    """A switcher segment is a markdown link, or a short bare language name
    (e.g. "中文", "**English**") — never a sentence. Distinguishes a real
    switcher from ordinary prose that happens to contain a README link and
    a pipe elsewhere on the line (e.g. "See [README](./README.md) for
    setup | more details.")."""
    core = segment.strip("*").strip()
    if _SWITCHER_LINK.match(core):
        return True
    return bool(core) and len(core) <= 16 and " " not in core


def _is_stale_switcher(text: str) -> bool:
    """A hand-written language-switcher line from before the doc move.

    Some repos already had their own language-switcher line pointing at
    the pre-move filenames (README_en.md, README_JA.md, ...) — separator
    style varies by repo (' · ', ' | ', ...), so detection doesn't depend
    on one: any line naming two or more README variants is a switcher,
    since prose has no reason to link the same doc under two names.

    A 2-language switcher's *current*-language side needs no link (it's
    already this file), so it may name a README file only once — e.g.
    "[English](./README.en-US.md) | **中文**". Trust a single mention only
    when every separator-delimited segment on the line looks like a
    language label, not prose.
    """
    files = {m.upper() for m in _README_FILENAME.findall(text)}
    if len(files) >= 2:
        return True
    if not files:
        return False
    sep = " · " if " · " in text else (" | " if " | " in text else None)
    if sep is None:
        return False
    return all(_looks_like_label(seg) for seg in text.split(sep))


def ensure_switcher(path: Path, variants: dict[str, str]) -> bool:
    """Insert the language switcher after the H1. Returns True if it changed."""
    line = switcher_line(variants)
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    stale = [i for i, ln in enumerate(lines) if _is_stale_switcher(ln) and ln != line]
    if line in text and not stale:
        return False
    for i in reversed(stale):
        del lines[i]
    idx = next((i for i, ln in enumerate(lines) if ln.startswith("# ")), -1)
    at = idx + 1 if idx >= 0 else 0
    if line not in lines:
        lines[at:at] = ["", line]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True
