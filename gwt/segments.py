"""Segment identity, occurrence records, and the permanent translation cache."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

_WS = re.compile(r"\s+")


def seg_hash(src: str) -> str:
    """Stable identity for a translatable segment.

    Normalizes Unicode (NFC) and collapses whitespace so that the same prose
    indented differently in two files hashes to one cache entry.
    """
    norm = _WS.sub(" ", unicodedata.normalize("NFC", src)).strip()
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Segment:
    h: str
    src: str
    kind: str
    lang: str


@dataclass(frozen=True)
class Occurrence:
    file: str
    start: int   # byte offset, inclusive
    end: int     # byte offset, exclusive
    h: str
    kind: str = "comment"  # "string" spans need quote-escaping at splice time


class Cache:
    """JSONL store of hash -> English, rewritten in sorted order on save
    for deterministic diffs. Committed to git."""

    def __init__(self, path: Path, entries: dict[str, dict]) -> None:
        self.path = path
        self._entries = entries

    @classmethod
    def load(cls, path: Path | str) -> "Cache":
        path = Path(path)
        entries: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                entries[rec["h"]] = rec
        return cls(path, entries)

    def get(self, h: str) -> str | None:
        rec = self._entries.get(h)
        return rec["en"] if rec else None

    def get_src(self, h: str) -> str | None:
        """The original (pre-translation) source text cached for this hash."""
        rec = self._entries.get(h)
        return rec["src"] if rec else None

    def put(self, h: str, src: str, en: str, engine: str) -> None:
        self._entries[h] = {"h": h, "src": src, "en": en, "engine": engine}

    def missing(self, hashes) -> list[str]:
        seen, out = set(), []
        for h in hashes:
            if h in self._entries or h in seen:
                continue
            seen.add(h)
            out.append(h)
        return out

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(self._entries[h], ensure_ascii=False)
                 for h in sorted(self._entries)]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def __len__(self) -> int:
        return len(self._entries)


def write_occurrences(path: Path | str, occs) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for o in occs:
            fh.write(json.dumps(asdict(o), ensure_ascii=False) + "\n")


def read_occurrences(path: Path | str) -> list[Occurrence]:
    return [Occurrence(**json.loads(line))
            for line in Path(path).read_text(encoding="utf-8").splitlines()
            if line.strip()]
