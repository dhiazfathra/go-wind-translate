"""Gates that must pass before a repo's translation branch is committed."""
from __future__ import annotations

import re
import subprocess
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


_ANCHOR_ONLY = re.compile(r"\]\(#([^)]+)\)")


def broken_anchors(repo_root: Path) -> list[tuple[str, str]]:
    """In-page `](#fragment)` links that no heading in the same file resolves.

    Complements `broken_doc_links`, which skips `#`-prefixed targets entirely.
    That exemption is why translating a heading could silently orphan every
    anchor pointing at it (ADR-0007) without the gate noticing.

    Scoped to same-file anchors: cross-file `other.md#frag` needs the other
    file's headings, and its *file* half is already checked above. Fenced and
    inline code are masked first, for the same reason as `broken_doc_links` —
    docs illustrate link syntax, and a gate that fires on illustrations is one
    reviewers learn to ignore.
    """
    from gwt.quality import _headings, heading_slug

    root = Path(repo_root)
    bad = []
    for md in root.rglob("*.md"):
        if ".git" in md.parts or "node_modules" in md.parts:
            continue
        raw = md.read_bytes()
        prose = bytes(_mask_md(raw)).decode("utf-8", errors="replace")
        slugs = {heading_slug(h) for h in _headings(raw.decode("utf-8", errors="replace"))}
        for frag in _ANCHOR_ONLY.findall(prose):
            if frag.lower() not in slugs:
                bad.append((md.relative_to(root).as_posix(), frag))
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


_MULTILINE_OPAQUE = [
    (re.compile(r'`[^`]*`', re.DOTALL), '`', '`'),        # Go raw string literal
    (re.compile(r'/\*.*?\*/', re.DOTALL), '/*', '*/'),    # block comment (Go, proto)
]


def _multiline_opaque(text: str) -> tuple[set[int], dict[int, tuple[str, bool]]]:
    """Interior line numbers and boundary-line roles for a raw string or
    block comment spanning more than one line.

    A multi-line Go raw string is common for embedded templates — email
    bodies, LLM prompts, Lua/SQL scripts. Each of its interior lines is
    just translated prose/script content, but `_pair_verdict` sees isolated
    diff lines with no way to know they're inside one literal: a line like
    "Verification code:{code}" or a Lua "-- comment" trips `_CODE_LINE` on
    its own — those are skipped outright by the caller.

    The opening/closing delimiter lines are different: real code can share
    that line (var tmpl = `Hello), and a rename there is genuine drift.
    They're reported as boundary roles instead of being blanket-skipped, so
    the caller can mask only the literal-content side of the line before
    running it through `_pair_verdict` — the code-bearing side still gets
    compared.
    """
    interior: set[int] = set()
    boundary: dict[int, tuple[str, bool]] = {}
    for pat, open_delim, close_delim in _MULTILINE_OPAQUE:
        for m in pat.finditer(text):
            start = text.count("\n", 0, m.start()) + 1
            end = text.count("\n", 0, m.end()) + 1
            if end > start:
                interior.update(range(start + 1, end))
                boundary[start] = (open_delim, True)
                boundary[end] = (close_delim, False)
    return interior, boundary


def _mask_multiline_boundary(body: str, delim: str, is_open: bool) -> str:
    """Blank the literal-content side of a multi-line-literal boundary line.

    An opening line keeps everything up to and including the delimiter
    (code, then the delimiter); a closing line keeps everything from the
    delimiter onward (the delimiter, then any trailing code). Either way,
    the content that lives inside the literal — the side with no delimiter
    on it — is discarded before comparison.
    """
    idx = body.find(delim) if is_open else body.rfind(delim)
    if idx == -1:
        return body
    return body[:idx + len(delim)] if is_open else body[idx:]


_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def identifier_drift(repo_root: Path) -> list[str]:
    """Diff lines that changed actual code, not just string/comment content.

    Scoped to `.go`/`.proto`, matching the manual check this automates
    (Task 12's `grep -E '\\b(func|type|var|const|package|import)\\b'` was
    only ever run against `*.go`/`*.proto`). Every other language this repo
    set carries breaks the line-diff heuristic a different way: markdown
    prose trips it on a bare `word:`, YAML/shell/PowerShell on translated
    scalar values and single-quoted strings, Vue/HTML on inner text between
    tags (not inside any string literal `_blank_literals` can mask) sharing
    a line with an unrelated `attr="..."`. None of those carry the actual
    identifier/signature risk this gate exists to catch.
    """
    root = Path(repo_root)
    diff = subprocess.run(
        ["git", "diff", "-U0", "--", "*.go", "*.proto"],
        cwd=root, capture_output=True, text=True).stdout

    out: list[str] = []
    opaque: set[int] = set()
    boundary: dict[int, tuple[str, bool]] = {}
    new_lineno = 0
    # A "-" run followed by a "+" run within one hunk pairs positionally
    # (git diff -U0's convention for a same-size replacement); track the
    # pending "-" run so each "+" line consumes the next one in order.
    pending_removed: list[str] = []

    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            path = root / line[6:]
            text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
            opaque, boundary = _multiline_opaque(text)
            pending_removed.clear()
            continue
        m = _HUNK_HEADER.match(line)
        if m:
            pending_removed.clear()  # stale "-" run from the previous hunk
            new_lineno = int(m.group(1))
            continue
        if not line or line[:3] in ("---", "+++"):
            continue
        if line[0] == "-":
            pending_removed.append(line)
        elif line[0] == "+":
            old = pending_removed.pop(0) if pending_removed else None
            if new_lineno in opaque:
                new_lineno += 1
                continue
            role = boundary.get(new_lineno)
            new_for_verdict, old_for_verdict = line, old
            if role:
                delim, is_open = role
                new_for_verdict = "+" + _mask_multiline_boundary(line[1:], delim, is_open)
                if old is not None:
                    old_for_verdict = "-" + _mask_multiline_boundary(old[1:], delim, is_open)
            verdict = _pair_verdict(old_for_verdict, new_for_verdict)
            if verdict:
                out.append(line)
            new_lineno += 1
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
        "broken_anchors": broken_anchors(repo_root),
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
