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
    elif before and before[-1] in _FULLWIDTH_PUNCT and _WORD_START.match(en):
        en = " " + en
    if _LEADING_ACRONYM.match(after) and _WORD_END.search(en):
        en = en + " "
    elif after and after[0] in _FULLWIDTH_PUNCT and _WORD_END.search(en):
        en = en + " "
    return en
