"""Gates that must pass before a repo's translation branch is committed."""
from __future__ import annotations

import re
import subprocess
from itertools import zip_longest
from pathlib import Path

from gwt.classify import CJK, has_cjk, iter_translatable

_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
# A diff line that carries code, not prose: assignment, call, declaration.
_CODE_LINE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\s*[:=(]")

# String/comment literal bodies to blank out before checking for code drift,
# so a translated string's *content* can never trip _CODE_LINE — only an
# actual change to the surrounding code skeleton should.
_DQ_STRING = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"')
_SQ_STRING = re.compile(r"'[^'\\]*(?:\\.[^'\\]*)*'")
_BACKTICK_STRING = re.compile(r'`[^`]*`')
_LINE_COMMENT = re.compile(r'(//|#).*$')
_BLOCK_COMMENT = re.compile(r'/\*.*?\*/')


def _blank_literals(body: str) -> str:
    """Replace string/comment literal contents with a fixed placeholder.

    Only the *code skeleton* survives (e.g. `msg := "..."` -> `msg := ""`),
    so two lines that differ only in what a string/comment says compare
    equal — content length isn't preserved, unlike gwt.splice's byte-offset
    masking, since this is diff-line text, not a byte span to write back.
    Single-quoted strings (shell, PowerShell) get the same treatment as
    double-quoted ones — otherwise a translated `'...'` argument (e.g. a
    PowerShell `-match` pattern) reads as a code skeleton change.
    """
    body = _BLOCK_COMMENT.sub('/**/', body)
    body = _DQ_STRING.sub('""', body)
    body = _SQ_STRING.sub("''", body)
    body = _BACKTICK_STRING.sub('``', body)
    body = _LINE_COMMENT.sub(lambda m: m.group(1), body)
    return body

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


def _pair_verdict(old: str | None, new: str | None) -> str | None:
    """Return the `new` line if it represents real code drift, else None.

    Compares the `-`/`+` lines with string and comment literal *contents*
    blanked out: a translated string literal keeps the same code skeleton
    (e.g. `msg := "..."` before and after), so it is not drift. Only a
    skeleton change — a change outside any literal — counts.
    """
    for line in (old, new):
        if line is not None and line[1:].strip().startswith(("//", "*", "/*", "#")):
            return None  # comment-only change, never drift
    if new is None:
        return None
    new_body = new[1:].strip()
    if has_cjk(new_body):
        return None
    new_skel = _blank_literals(new_body)
    if old is not None and _blank_literals(old[1:].strip()) == new_skel:
        return None
    return new if _CODE_LINE.search(new_skel) else None


def identifier_drift(repo_root: Path) -> list[str]:
    """Diff lines that changed actual code, not just string/comment content.

    Scoped to code files only: markdown prose routinely has a word followed
    by `:` or `(` (e.g. "Direction:`cmd -> ...`"), which trips `_CODE_LINE`
    despite carrying no identifiers at all.
    """
    diff = subprocess.run(
        ["git", "diff", "-U0", "--", ".", ":(exclude)*.md", ":(exclude)*.mdx"],
        cwd=repo_root, capture_output=True, text=True).stdout
    lines = [ln for ln in diff.splitlines()
              if ln and ln[0] in "+-" and ln[:3] not in ("+++", "---")]
    out = []
    i = 0
    while i < len(lines):
        if lines[i][0] == "-":
            removed = []
            while i < len(lines) and lines[i][0] == "-":
                removed.append(lines[i])
                i += 1
            added = []
            while i < len(lines) and lines[i][0] == "+":
                added.append(lines[i])
                i += 1
            # git diff -U0 pairs a single-line change as one removed line
            # immediately followed by one added line; pair positionally.
            for old, new in zip_longest(removed, added):
                verdict = _pair_verdict(old, new)
                if verdict:
                    out.append(verdict)
        else:
            verdict = _pair_verdict(None, lines[i])
            if verdict:
                out.append(verdict)
            i += 1
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
