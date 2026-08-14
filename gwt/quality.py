"""Deterministic cleanup for recurring MT spacing artifacts.

DeepL occasionally emits an acronym glued directly to the next English word
with no space — e.g. "UserIDInvalid", "URIToo long", "HTTPThis version is
not supported". Observed across every repo's `*.proto` enum comments in the
Task 13 fan-out (documented in HANDOFF.md's Task 14 notes).

Scope is deliberately narrow: only a *known* acronym immediately followed by
a capitalized real word (2+ lowercase letters) counts. A generic
lower-then-upper glue detector would also fire on a legitimate camelCase
identifier mentioned in a comment (e.g. "the isValidRequest function") and
wrongly split it into three words — this only touches the acronym case,
which is unambiguous: acronyms are already all-caps by convention, so an
acronym directly followed by a new capitalized word is never a real single
token.
"""
from __future__ import annotations

import re

# Acronyms observed gluing to the next word in translated proto/Go comments.
# Ordered longest-first so e.g. "HTTPS" matches before "HTTP" would.
_ACRONYMS = sorted(
    ["HTTPS", "HTTP", "JSON", "UUID", "JWT", "URI", "URL", "API", "SQL",
     "XML", "TTL", "ID", "IP"],
    key=len, reverse=True,
)

_GLUE = re.compile(
    r"(" + "|".join(_ACRONYMS) + r")([A-Z][a-z]{1,})"
)


def fix_spacing(text: str) -> str:
    """Insert a space between an acronym and a word glued directly to it."""
    return _GLUE.sub(r"\1 \2", text)


_ACRONYM_ALT = "|".join(_ACRONYMS)
_TRAILING_ACRONYM = re.compile(r"(?:" + _ACRONYM_ALT + r")$")
_LEADING_ACRONYM = re.compile(r"^(?:" + _ACRONYM_ALT + r")")
_WORD_START = re.compile(r"^[A-Z][a-z]")
_WORD_END = re.compile(r"[a-z]$")

# Full-width Chinese punctuation left glued to a translated span for the same
# reason as the acronym case above: extraction narrows to the CJK-letter run
# only, so punctuation immediately outside it is never part of the segment
# and is never touched by translation. Left as-is, it reads as e.g.
# "the request、then respond" or "get value（configured elsewhere）" — a
# half-width English word directly touching a full-width mark. Pad with a
# space rather than converting the mark itself: the mark may still be
# bracketing untranslated Chinese on its far side, so swapping it for an
# ASCII equivalent isn't always correct, but a boundary space always reads
# better than none.
_FULLWIDTH_PUNCT = "，。、；：（）！？"

# Bytes of lookaround around a splice span, enough for the longest acronym
# ("HTTPS", 5 chars) plus slack.
_LOOKAROUND = 10


def pad_comment_boundary(raw: bytes, start: int, end: int, en: str) -> str:
    """Insert a space where a translated comment segment would otherwise
    glue directly onto adjacent literal source text.

    Chinese needs no space between an identifier-like Latin run and the
    surrounding prose (`用户ID无效`, "UserID" + "invalid" with nothing
    between) — extraction narrows to the CJK-only spans either side of
    `ID` and leaves it untouched, so splicing the English translations
    back in place reproduces that same zero-width join, which English
    can't read (`UserIDInvalid`). Comments only: this must never touch a
    real code identifier, and a `//`/`#` comment's surrounding literal text
    is never itself code.
    """
    before = raw[max(0, start - _LOOKAROUND):start].decode("utf-8", errors="ignore")
    after = raw[end:end + _LOOKAROUND].decode("utf-8", errors="ignore")
    if _TRAILING_ACRONYM.search(before) and _WORD_START.match(en):
        en = " " + en
    elif before and before[-1] in _FULLWIDTH_PUNCT and en:
        en = " " + en
    if _LEADING_ACRONYM.match(after) and _WORD_END.search(en):
        en = en + " "
    elif after and after[0] in _FULLWIDTH_PUNCT and _WORD_END.search(en):
        en = en + " "
    return en


# --- In-page anchor repair -------------------------------------------------
#
# A markdown link *target* is masked and never translated (ADR-0005), which is
# right: blindly translating a URL or a fragment breaks it. But a heading's
# *text* is translated, and a heading is what a `#fragment` resolves against.
# So translating `## 架构概览` silently invalidates every `](#架构概览)` in the
# document. `verify.broken_doc_links` skips `#`-prefixed targets by design, so
# nothing caught this: 9 broken anchors in go-wind-admin, 23 in go-wind-cms.
#
# The repair needs the whole heading line, before and after, because a slug can
# mix a Latin run with the translated CJK one (`## API 两层架构` ->
# `#api-两层架构`), so it cannot be derived from the segment alone. See ADR-0007.

_ATX_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(?:```|~~~)")
_ANCHOR_LINK = re.compile(r"(\]\([^)]*?#)([^)]+)(\))")


def heading_slug(line: str) -> str:
    """GitHub's heading-to-fragment slug for an ATX heading line.

    Lowercase, punctuation dropped, whitespace collapsed to hyphens. CJK is
    kept verbatim — GitHub does not transliterate it, which is exactly why a
    Chinese heading yields a Chinese fragment.
    """
    m = _ATX_HEADING.match(line)
    text = m.group(1) if m else line
    text = text.strip().lower()
    text = re.sub(r"[^\w\s一-鿿-]", "", text)
    return re.sub(r"\s+", "-", text).strip("-")


def _headings(text: str) -> list[str]:
    """ATX heading lines, skipping fenced blocks (a `#` in a shell fence is a
    comment, and counting it would shift the positional pairing below)."""
    out, fenced = [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if not fenced and _ATX_HEADING.match(line):
            out.append(line)
    return out


def repair_anchors(before: bytes, after: bytes) -> bytes:
    """Rewrite in-page anchors in `after` whose heading was translated.

    Headings are paired positionally: splicing replaces bytes in place and
    never adds or removes a line, so the Nth heading before is the Nth heading
    after. A differing count means these aren't the same document — return
    `after` untouched rather than mis-pair and corrupt working links.

    Only anchors whose target matches a heading slug that actually changed are
    rewritten. An anchor pointing at something that was never a heading here
    (e.g. a section of another document) is left alone rather than guessed at.
    """
    old_text = before.decode("utf-8", errors="replace")
    new_text = after.decode("utf-8", errors="replace")
    old_heads, new_heads = _headings(old_text), _headings(new_text)
    if len(old_heads) != len(new_heads):
        return after
    renamed = {}
    for o, n in zip(old_heads, new_heads):
        os_, ns = heading_slug(o), heading_slug(n)
        if os_ and ns and os_ != ns:
            renamed[os_] = ns
    if not renamed:
        return after

    def sub(m):
        target = m.group(2)
        return m.group(1) + renamed.get(target.lower(), target) + m.group(3)

    return _ANCHOR_LINK.sub(sub, new_text).encode("utf-8")
