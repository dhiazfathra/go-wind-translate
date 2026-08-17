"""Phase 2 term repair.

Phase 1 translated with DeepL/Argos over narrowed CJK spans. Narrowing strips the
surrounding identifiers, which is what keeps identifiers safe — but it also strips
the domain context an engine needs, so 角色 came back as "Character" and 桶 as
"Barrel". Those are wrong terms, not awkward phrasing, and they are systematic.

This module rewrites cached English for a closed set of (zh_term, wrong_en,
correct_en) triples, gated on the Chinese source actually containing the term. It
does not re-translate and does not call an engine: the source of truth for what is
wrong is the eleven-repo review pass recorded in corrections.tsv.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Correction:
    zh: str
    wrong: str
    right: str


def load_corrections(path: Path) -> list[Correction]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            raise ValueError(f"malformed corrections row: {line!r}")
        out.append(Correction(*(p.strip() for p in parts)))
    return out


def _pattern(wrong: str) -> re.Pattern[str]:
    # \b is wrong at a non-word edge (e.g. a trailing "("), so anchor on the term itself.
    return re.compile(rf"(?<![A-Za-z]){re.escape(wrong)}(?![A-Za-z])")


def apply_corrections(src: str, en: str, corrections: list[Correction]) -> str:
    """Rewrite `en` for every correction whose zh term appears in `src`.

    A zh term written as `=词` requires the whole segment to be exactly that term.
    Some words are only mistranslated in isolation — 执行 is "Enforcement" as a
    Code-of-Conduct heading and "Execute" everywhere else — so a substring gate
    would corrupt more than it fixes.

    A term written as `词!例外` additionally requires that `例外` is absent, for
    compounds where the longer form flips the right answer.
    """
    for c in corrections:
        required, *forbidden = c.zh.split("!")
        if required.startswith("="):
            if src.strip() != required[1:]:
                continue
        elif required not in src:
            continue
        # A longer compound can flip the right answer: 仓库 is "repository", but
        # 数据仓库 really is a data warehouse.
        if any(f in src for f in forbidden):
            continue
        en = _pattern(c.wrong).sub(c.right, en)
    return en


def repair_cache(cache_path: Path, corrections: list[Correction]) -> tuple[int, list[dict]]:
    """Rewrite cache records in place. Returns (changed_count, changed_records)."""
    records = [json.loads(line) for line in cache_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    changed = []
    for rec in records:
        fixed = apply_corrections(rec["src"], rec["en"], corrections)
        if fixed != rec["en"]:
            changed.append({"h": rec["h"], "src": rec["src"], "before": rec["en"], "after": fixed})
            rec["en"] = fixed
            rec["engine"] = "phase2-repair"
    if changed:
        cache_path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
        )
    return len(changed), changed
