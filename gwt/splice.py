"""Write translations back by byte span, deepest offset first."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from gwt.segments import Cache, Occurrence, read_occurrences


def splice_file(path: Path, occs: list[Occurrence], cache: Cache) -> int:
    raw = bytearray(Path(path).read_bytes())
    n = 0
    for o in sorted(occs, key=lambda o: o.start, reverse=True):
        en = cache.get(o.h)
        if en is None:
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
