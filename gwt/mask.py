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
# Uses explicit lookaround (?<![A-Za-z0-9_])...(?![A-Za-z0-9_]) instead of \b
# because \b treats CJK ideographs as \w, leaving identifiers adjacent to Chinese unmasked.
_PATTERNS = [
    re.compile(r"`[^`\n]+`"),                                   # backticked code
    re.compile(r"https?://\S+"),                                # URLs
    re.compile(r"%[-+ #0]?[0-9.*]*[a-zA-Z]"),                   # printf verbs
    re.compile(r"\{[A-Za-z0-9_.]+\}"),                          # {placeholders}
    re.compile(r"\$\{[A-Za-z0-9_.]+\}"),                        # ${placeholders}
    re.compile(r"(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*(?=\()"),              # call sites
    re.compile(r"(?<![A-Za-z0-9_])[a-z]+(?:[A-Z][a-zA-Z0-9]*)+(?![A-Za-z0-9_])"),            # camelCase
    re.compile(r"(?<![A-Za-z0-9_])[A-Z][a-z0-9]+(?:[A-Z][a-zA-Z0-9]*)+(?![A-Za-z0-9_])"),    # PascalCase
    re.compile(r"(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+(?![A-Za-z0-9_])"),      # snake_case
    re.compile(r"(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]+)+(?![A-Za-z0-9_])"),  # dotted
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
    """Strip <x>…</x> wrapper tags added by protect().

    Note: this is safe only because DeepL's tag_handling=xml requires well-formed
    XML, so a literal unescaped <x> in the original source would fail XML parsing
    before unprotect is called. If that assumption changes, escape < and > in
    literal content first.
    """
    return _TAGGED.sub("", text)
