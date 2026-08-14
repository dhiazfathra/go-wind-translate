"""AST-accurate extraction of Chinese-bearing segments."""
from __future__ import annotations

import re
from pathlib import Path

from gwt.classify import LANG_BY_SUFFIX, has_cjk
from gwt.segments import Occurrence, Segment, seg_hash

# tree-sitter node type -> our segment kind, per language.
#
# c_sharp is intentionally absent: tree-sitter-language-pack>=0.9 reports
# get_parser("c_sharp") as MISS in this environment (LookupError). Files
# routed to "c_sharp" fall through to the line-based fallback below.
NODE_KINDS: dict[str, dict[str, str]] = {
    "go": {
        "comment": "comment",
        "interpreted_string_literal": "string",
        "raw_string_literal": "raw_string",
    },
    "typescript": {
        "comment": "comment",
        "string_fragment": "string",
        "template_string": "string",
    },
    "tsx": {
        "comment": "comment",
        "string_fragment": "string",
        "template_string": "string",
    },
    "proto": {"comment": "comment", "string": "string"},
    "dart": {"comment": "comment", "documentation_comment": "comment"},
}

# A run of CJK plus the punctuation/spacing that belongs to it. Latin runs on
# either side (identifiers, format verbs, URLs) fall outside the match.
_CJK_RUN = re.compile(
    r"[一-鿿　-〿＀-￯]"
    r"(?:[一-鿿　-〿＀-￯\s,.:;()'\"-]*"
    r"[一-鿿　-〿＀-￯])?"
)

_LINE_COMMENT = re.compile(r"(?://|#|--)\s?(.*)$")


def _parser(lang: str):
    from tree_sitter_language_pack import get_parser
    return get_parser(lang)


def _cjk_spans(raw: bytes, node_start: int, node_end: int):
    """Yield (start, end, text) byte spans of CJK runs inside a node."""
    chunk = raw[node_start:node_end].decode("utf-8", errors="replace")
    for m in _CJK_RUN.finditer(chunk):
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


def _extract_treesitter(raw: bytes, rel: str, lang: str):
    kinds = NODE_KINDS[lang]
    tree = _parser(lang).parse(raw)
    segs: dict[str, Segment] = {}
    occs: list[Occurrence] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        kind = kinds.get(node.type)
        if kind is not None:
            for s, e, text in _cjk_spans(raw, node.start_byte, node.end_byte):
                h = seg_hash(text)
                segs.setdefault(h, Segment(h=h, src=text, kind=kind, lang=lang))
                occs.append(Occurrence(file=rel, start=s, end=e, h=h, kind=kind))
        else:
            stack.extend(node.children)
    return list(segs.values()), occs


def _extract_lines(raw: bytes, rel: str, lang: str):
    """Fallback for languages with no grammar: comment lines and any CJK run."""
    segs: dict[str, Segment] = {}
    occs: list[Occurrence] = []
    offset = 0
    for line in raw.split(b"\n"):
        text = line.decode("utf-8", errors="replace")
        if has_cjk(text):
            kind = "comment" if _LINE_COMMENT.search(text) else "string"
            for s, e, t in _cjk_spans(raw, offset, offset + len(line)):
                h = seg_hash(t)
                segs.setdefault(h, Segment(h=h, src=t, kind=kind, lang=lang))
                occs.append(Occurrence(file=rel, start=s, end=e, h=h, kind=kind))
        offset += len(line) + 1
    return list(segs.values()), occs


def extract_file(path: Path, rel: str) -> tuple[list[Segment], list[Occurrence]]:
    lang = LANG_BY_SUFFIX.get(Path(rel).suffix, "")
    raw = Path(path).read_bytes()
    if lang == "markdown":
        from gwt.extract_md import extract_markdown
        return extract_markdown(raw, rel)
    if lang == "vue":
        try:
            return _extract_treesitter(raw, rel, "vue")
        except Exception:
            # No vue grammar: script-block comments and template text both
            # reduce to "lines containing CJK", which the fallback handles.
            return _extract_lines(raw, rel, "vue")
    if lang in NODE_KINDS:
        try:
            return _extract_treesitter(raw, rel, lang)
        except Exception:
            pass  # grammar unavailable at runtime -> degrade, never crash a repo run
    return _extract_lines(raw, rel, lang)
