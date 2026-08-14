"""Markdown extraction: prose only, code and URLs masked out."""
from __future__ import annotations

import re

from gwt.segments import Occurrence, Segment, seg_hash
from gwt.classify import has_cjk

# Regions whose bytes must never reach a translator. Order matters:
# fences first, so an inline-code regex cannot chew into a fenced block.
_SKIP = [
    re.compile(r"^---\n.*?\n---\n", re.DOTALL),          # YAML frontmatter
    re.compile(r"```.*?```", re.DOTALL),                  # fenced code
    re.compile(r"~~~.*?~~~", re.DOTALL),                  # fenced code (tilde)
    re.compile(r"`[^`\n]+`"),                             # inline code
    re.compile(r"<[^>\n]+>"),                             # raw HTML tags
    re.compile(r"\]\([^)\n]*\)"),                         # link/image targets
    re.compile(r"https?://\S+"),                          # bare URLs
]

# CJK run for markdown: like _CJK_RUN in extract.py but doesn't allow newlines
# in the middle of runs, to keep heading and prose separate.
_CJK_RUN_MD = re.compile(
    r"[一-鿿　-〿＀-￯]"
    r"(?:[一-鿿　-〿＀-￯ ,.:;()'\"-]*"
    r"[一-鿿　-〿＀-￯])?"
)


def _mask(raw: bytes) -> bytearray:
    """Return a copy with skip-regions blanked to newlines, preserving length."""
    text = raw.decode("utf-8", errors="replace")
    keep = bytearray(raw)
    for pat in _SKIP:
        for m in pat.finditer(text):
            s = len(text[: m.start()].encode("utf-8"))
            e = s + len(m.group(0).encode("utf-8"))
            # Replace with newline bytes (0x0A) to break the CJK regex pattern
            for i in range(s, min(e, len(keep))):
                keep[i] = 0x0A
    return keep


def _cjk_spans_md(raw: bytes, node_start: int, node_end: int):
    """Yield (start, end, text) byte spans of CJK runs, no newlines in middle."""
    chunk = raw[node_start:node_end].decode("utf-8", errors="replace")
    for m in _CJK_RUN_MD.finditer(chunk):
        text = m.group(0).strip()
        if not text or not has_cjk(text):
            continue
        # Recompute byte offsets: char index -> byte offset within the chunk.
        pre = chunk[: m.start()].encode("utf-8")
        body = m.group(0)
        lead = len(body) - len(body.lstrip())
        lead_b = len(body[:lead].encode("utf-8"))
        start = node_start + len(pre) + lead_b
        yield start, start + len(text.encode("utf-8")), text


def extract_markdown(raw: bytes, rel: str):
    masked = bytes(_mask(raw))
    segs: dict[str, Segment] = {}
    occs: list[Occurrence] = []
    # Extract spans from masked bytes (to avoid masked regions), but text from original raw bytes
    for s, e, _ in _cjk_spans_md(masked, 0, len(masked)):
        text = raw[s:e].decode("utf-8")
        text = text.strip()
        if not text or not has_cjk(text):
            continue
        h = seg_hash(text)
        segs.setdefault(h, Segment(h=h, src=text, kind="md_prose", lang="markdown"))
        occs.append(Occurrence(file=rel, start=s, end=e, h=h))
    return list(segs.values()), occs
