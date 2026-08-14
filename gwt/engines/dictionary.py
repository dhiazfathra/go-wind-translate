"""Zero-network exact-match pre-pass over high-frequency boilerplate."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

_WS = re.compile(r"\s+")
_DEFAULT = Path(__file__).resolve().parent.parent.parent / "dictionary.tsv"


def _norm(s: str) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFC", s)).strip()


class DictionaryEngine:
    name = "dictionary"

    def __init__(self, path: Path | str = _DEFAULT) -> None:
        self.pairs: dict[str, str] = {}
        p = Path(path)
        if not p.exists():
            return
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.startswith("#") or "\t" not in line:
                continue
            zh, en = line.split("\t", 1)
            self.pairs[_norm(zh)] = en.strip()

    def translate(self, texts: list[str]) -> list[str]:
        return [self.pairs.get(_norm(t), "") for t in texts]
