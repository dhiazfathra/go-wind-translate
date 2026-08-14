"""gwt — go-wind zh->en translation pipeline."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from gwt.classify import iter_translatable
from gwt.docs_layout import apply_moves, ensure_switcher, plan_moves
from gwt.engines import get_engine
from gwt.extract import extract_file
from gwt.segments import Cache, Segment, write_occurrences
from gwt.splice import splice_repo
from gwt.verify import run_gate

ROOT = Path.home() / "Documents" / "GitHub" / "dhiazfathra"
HERE = Path(__file__).resolve().parent.parent
CACHE_PATH = HERE / "cache" / "segments.jsonl"
WORK = HERE / "work"


def _safe_repo_root(repo: str) -> Path:
    """Reject repo args that could escape the sibling-repo directory."""
    if "/" in repo or "\\" in repo or repo in ("..", "."):
        raise ValueError(f"invalid repo name: {repo!r}")
    return ROOT / repo


def cmd_extract(repo: str) -> list[Segment]:
    repo_root = _safe_repo_root(repo)
    all_segs: dict[str, Segment] = {}
    all_occs = []
    for f in iter_translatable(repo_root):
        segs, occs = extract_file(f, f.relative_to(repo_root).as_posix())
        for s in segs:
            all_segs.setdefault(s.h, s)
        all_occs.extend(occs)
    write_occurrences(WORK / repo / "occurrences.jsonl", all_occs)
    print(f"{repo}: {len(all_occs)} occurrences, {len(all_segs)} unique segments")
    return list(all_segs.values())


def cmd_translate(segs: list[Segment], cache: Cache, engines: list) -> None:
    """Chain engines; a segment resolved by an earlier engine never reaches a later one."""
    pending = {s.h: s.src for s in segs if cache.get(s.h) is None}
    for eng in engines:
        if not pending:
            break
        hashes = list(pending)
        texts = [pending[h] for h in hashes]
        results = eng.translate(texts)
        if len(results) != len(texts):
            raise RuntimeError(
                f"engine {eng.name} returned {len(results)} results for {len(texts)} inputs")
        for h, src, en in zip(hashes, texts, results):
            if en and en.strip():
                cache.put(h, src, en, eng.name)
                pending.pop(h, None)
        print(f"  {eng.name}: resolved {len(hashes) - len(pending)}, {len(pending)} left")
    if pending:
        print(f"  WARNING: {len(pending)} segments unresolved", file=sys.stderr)


def cmd_switchers(repo: str) -> None:
    """Insert/update the language switcher line in every README variant.

    Kept separate from the moves so cmd_run can defer it until after
    splice: the README.md left behind for a default (Chinese) doc is the
    same file cmd_extract already recorded byte offsets against, and
    ensure_switcher inserting a line would shift every offset after it,
    breaking splice's hash-matched byte spans.
    """
    repo_root = _safe_repo_root(repo)
    variants = {}
    for lang, name in (("en", "README.md"), ("zh-CN", "README.zh-CN.md"),
                       ("ja-JP", "README.ja-JP.md")):
        if (repo_root / name).exists():
            variants[lang] = f"./{name}"
    if len(variants) > 1:
        for name in variants.values():
            ensure_switcher(repo_root / name.lstrip("./"), variants)


def cmd_docs(repo: str, dry_run: bool = False) -> None:
    repo_root = _safe_repo_root(repo)
    moves = plan_moves(repo_root)
    apply_moves(repo_root, moves, dry_run=dry_run)
    if dry_run:
        return
    cmd_switchers(repo)


def cmd_verify(repo: str, skip_build: bool = False, baseline_path: str | Path | None = None,
              baseline: dict | None = None) -> int:
    """`baseline`/`baseline_path` (a previously captured `gwt verify` JSON
    result, e.g. work/<repo>-before.json per Task 12) suppress pre-existing
    defects: only items NEW relative to the baseline are reported."""
    if baseline_path is not None:
        baseline = json.loads(Path(baseline_path).read_text(encoding="utf-8"))
    result = run_gate(_safe_repo_root(repo), skip_build=skip_build)
    if baseline:
        # A baseline loaded from JSON has tuples turned into lists; normalize
        # both sides the same way before comparing so pre-existing entries
        # (e.g. an already-broken doc link) are actually recognized and
        # excluded, rather than always appearing "new".
        def _norm(x):
            return list(x) if isinstance(x, (list, tuple)) else x

        result = {k: [item for item in v if _norm(item) not in
                      [_norm(b) for b in baseline.get(k, [])]]
                  if isinstance(v, list) else v
                  for k, v in result.items()}
    print(json.dumps({k: (v[:20] if isinstance(v, list) else v)
                      for k, v in result.items()}, ensure_ascii=False, indent=2))
    return 0 if not any(result.values()) else 1


def cmd_run(repo: str, engine: str, skip_build: bool) -> int:
    cache = Cache.load(CACHE_PATH)
    segs = cmd_extract(repo)

    # Docs layout moves BEFORE translate/splice: plan_moves' has_cjk check
    # needs to see the still-untranslated README, and this must happen
    # before any Chinese content is overwritten with English. The archival
    # copy left at the original path (see docs_layout.apply_moves) keeps the
    # occurrence file paths recorded by cmd_extract valid.
    repo_root = _safe_repo_root(repo)
    apply_moves(repo_root, plan_moves(repo_root))

    chain = [get_engine("dictionary")]
    if engine == "deepl":
        chain.append(get_engine("deepl"))
    elif engine == "argos":
        chain.append(get_engine("argos"))
    cmd_translate(segs, cache, chain)
    cache.save()

    counts = splice_repo(repo_root, WORK / repo / "occurrences.jsonl", cache)
    print(f"{repo}: spliced {sum(counts.values())} spans across {len(counts)} files")

    # Switcher insertion mutates README bytes — must happen after splice,
    # not before: it would otherwise shift the byte offsets cmd_extract
    # recorded for the archived-and-recreated README (see cmd_switchers).
    cmd_switchers(repo)

    # Regenerate anything derived from the now-English proto / ent schema.
    for sub in ("backend", "."):
        mk = _safe_repo_root(repo) / sub / "Makefile"
        if mk.exists():
            subprocess.run(["make", "gen"], cwd=mk.parent, check=False)
            break

    return cmd_verify(repo, skip_build=skip_build)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gwt")
    sub = p.add_subparsers(dest="cmd", required=True)

    for name in ("extract", "splice", "docs", "verify"):
        s = sub.add_parser(name)
        s.add_argument("repo")
        if name in ("verify",):
            s.add_argument("--skip-build", action="store_true")
            s.add_argument("--baseline", default=None,
                          help="path to a prior `gwt verify` JSON result; only NEW findings fail")
        if name == "docs":
            s.add_argument("--dry-run", action="store_true")

    t = sub.add_parser("translate")
    t.add_argument("repo")
    t.add_argument("--engine", default="deepl", choices=["dictionary", "deepl", "argos"])

    r = sub.add_parser("run")
    r.add_argument("repo")
    r.add_argument("--engine", default="deepl", choices=["dictionary", "deepl", "argos"])
    r.add_argument("--skip-build", action="store_true")
    return p


def main() -> int:
    ns = build_parser().parse_args()
    if ns.cmd == "extract":
        cmd_extract(ns.repo)
        return 0
    if ns.cmd == "translate":
        cache = Cache.load(CACHE_PATH)
        cmd_translate(cmd_extract(ns.repo), cache, [get_engine("dictionary"),
                                                    get_engine(ns.engine)])
        cache.save()
        return 0
    if ns.cmd == "splice":
        cache = Cache.load(CACHE_PATH)
        counts = splice_repo(_safe_repo_root(ns.repo), WORK / ns.repo / "occurrences.jsonl", cache)
        print(f"spliced {sum(counts.values())} spans")
        return 0
    if ns.cmd == "docs":
        cmd_docs(ns.repo, dry_run=ns.dry_run)
        return 0
    if ns.cmd == "verify":
        return cmd_verify(ns.repo, skip_build=ns.skip_build, baseline_path=ns.baseline)
    if ns.cmd == "run":
        return cmd_run(ns.repo, ns.engine, ns.skip_build)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
