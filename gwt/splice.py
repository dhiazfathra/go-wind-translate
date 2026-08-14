"""Write translations back by byte span, deepest offset first."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from gwt.segments import Cache, Occurrence, read_occurrences, seg_hash


def splice_file(path: Path, occs: list[Occurrence], cache: Cache) -> int:
    raw = bytearray(Path(path).read_bytes())
    n = 0
    for o in sorted(occs, key=lambda o: o.start, reverse=True):
        en = cache.get(o.h)
        if en is None:
            continue
        # Guard against a stale occurrences.jsonl (e.g. a standalone `gwt
        # splice` run against a file that has since changed): only write if
        # the span still holds the source text this occurrence was recorded
        # for. Skip rather than corrupt — residual_cjk will still flag it.
        try:
            current = raw[o.start:o.end].decode("utf-8")
        except (UnicodeDecodeError, IndexError):
            continue
        if seg_hash(current) != o.h:
            continue
        if o.kind == "string":
            # MT output occasionally wraps a word in literal ASCII quotes
            # for emphasis (DeepL does this on negation words like "非").
            # Spliced verbatim into a double-quoted string literal, that
            # quote terminates the literal early and breaks the build —
            # escape it the same way the host language would.
            en = en.replace("\\", "\\\\").replace('"', '\\"')
        elif o.kind == "raw_string":
            # A raw string literal (Go: backtick-delimited) treats backslash
            # and double-quote as plain bytes, not escapes — applying the
            # interpreted-string escaping here would corrupt content like a
            # Windows path (C:\tmp) or an embedded quote. The one thing a raw
            # string genuinely cannot represent is a literal backtick (it
            # would terminate the literal); if MT output contains one, skip
            # this occurrence rather than emit a broken source file.
            if "`" in en:
                continue
        raw[o.start:o.end] = en.encode("utf-8")
        n += 1
    if n:
        Path(path).write_bytes(bytes(raw))
    return n


def splice_repo(repo_root: Path, occ_path: Path, cache: Cache) -> dict[str, int]:
    by_file: dict[str, list[Occurrence]] = defaultdict(list)
    for o in read_occurrences(occ_path):
        by_file[o.file].append(o)
    return {rel: splice_file(repo_root / rel, occs, cache)
            for rel, occs in by_file.items()}
