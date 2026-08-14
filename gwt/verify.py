"""Gates that must pass before a repo's translation branch is committed."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from gwt.classify import CJK, has_cjk, iter_translatable

_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
# A diff line that carries code, not prose: assignment, call, declaration.
_CODE_LINE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*[:=(]")

# Masking patterns for markdown: code blocks and inline code only.
# Note: we do NOT mask link targets, because we need to detect links to check if they're broken.
_MD_MASK_PATTERNS = [
    re.compile(r"^---\n.*?\n---\n", re.DOTALL),          # YAML frontmatter
    re.compile(r"```.*?```", re.DOTALL),                  # fenced code
    re.compile(r"~~~.*?~~~", re.DOTALL),                  # fenced code (tilde)
    re.compile(r"`[^`\n]+`"),                             # inline code
    re.compile(r"<[^>\n]+>"),                             # raw HTML tags
]


def _mask_md(raw: bytes) -> bytearray:
    """Mask code blocks and inline code, preserving length for byte offsets."""
    text = raw.decode("utf-8", errors="replace")
    keep = bytearray(raw)
    for pat in _MD_MASK_PATTERNS:
        for m in pat.finditer(text):
            s = len(text[:m.start()].encode("utf-8"))
            e = s + len(m.group(0).encode("utf-8"))
            for i in range(s, min(e, len(keep))):
                keep[i] = 0x0A
    return keep


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
    root = Path(repo_root)
    bad = []
    for md in root.rglob("*.md"):
        if ".git" in md.parts or "node_modules" in md.parts:
            continue
        prose = bytes(_mask_md(md.read_bytes())).decode("utf-8", errors="replace")
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
