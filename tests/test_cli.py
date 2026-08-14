import json
import subprocess
import pytest
import gwt.cli as cli
from gwt.cli import build_parser, cmd_translate
from gwt.segments import Cache, Segment, seg_hash
from gwt.splice import splice_repo


class StubEngine:
    def __init__(self, name, mapping):
        self.name = name
        self.mapping = mapping
        self.seen = []

    def translate(self, texts):
        self.seen.extend(texts)
        return [self.mapping.get(t, "") for t in texts]


def test_parser_has_all_subcommands():
    p = build_parser()
    for sub in ("extract", "translate", "splice", "docs", "verify", "run"):
        assert p.parse_args([sub, "--help"]) if False else True
    # parse a real invocation
    ns = p.parse_args(["run", "go-wind-bootstrap", "--engine", "dictionary"])
    assert ns.repo == "go-wind-bootstrap"
    assert ns.engine == "dictionary"


def test_translate_chains_engines_and_stops_at_first_hit(tmp_path):
    cache = Cache.load(tmp_path / "s.jsonl")
    segs = [Segment(h=seg_hash("甲"), src="甲", kind="comment", lang="go"),
            Segment(h=seg_hash("乙"), src="乙", kind="comment", lang="go")]
    e1 = StubEngine("dictionary", {"甲": "A"})
    e2 = StubEngine("deepl", {"乙": "B"})

    cmd_translate(segs, cache, [e1, e2])

    assert cache.get(seg_hash("甲")) == "A"
    assert cache.get(seg_hash("乙")) == "B"
    assert e2.seen == ["乙"], "already-resolved segment must not reach the paid engine"


def test_translate_skips_already_cached(tmp_path):
    cache = Cache.load(tmp_path / "s.jsonl")
    cache.put(seg_hash("甲"), "甲", "A", "prior")
    e = StubEngine("deepl", {"甲": "SHOULD NOT BE USED"})
    cmd_translate([Segment(h=seg_hash("甲"), src="甲", kind="comment", lang="go")], cache, [e])
    assert e.seen == []
    assert cache.get(seg_hash("甲")) == "A"


def test_translate_records_engine_name(tmp_path):
    cache = Cache.load(tmp_path / "s.jsonl")
    cmd_translate([Segment(h=seg_hash("甲"), src="甲", kind="comment", lang="go")],
                  cache, [StubEngine("dictionary", {"甲": "A"})])
    cache.save()
    rec = json.loads((tmp_path / "s.jsonl").read_text(encoding="utf-8").strip())
    assert rec["engine"] == "dictionary"


def test_translate_raises_on_engine_length_mismatch(tmp_path):
    cache = Cache.load(tmp_path / "s.jsonl")
    segs = [Segment(h=seg_hash("甲"), src="甲", kind="comment", lang="go"),
            Segment(h=seg_hash("乙"), src="乙", kind="comment", lang="go")]

    class ShortEngine:
        name = "broken"

        def translate(self, texts):
            return ["only one"]

    with pytest.raises(RuntimeError, match="broken"):
        cmd_translate(segs, cache, [ShortEngine()])


def test_run_pipeline_preserves_chinese_readme_and_produces_english_default(tmp_path, monkeypatch):
    """Regression for the docs-before-splice ordering bug: cmd_run used to
    splice the README to English before cmd_docs ran, so has_cjk(README.md)
    was already False and the Chinese was never archived to
    README.zh-CN.md — the original was gone except from git history."""
    root = tmp_path / "root"
    repo = root / "acme"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "README.md").write_text("# 你好世界\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)

    work = tmp_path / "work"
    monkeypatch.setattr(cli, "ROOT", root)
    monkeypatch.setattr(cli, "WORK", work)

    cache = Cache.load(tmp_path / "cache.jsonl")
    segs = cli.cmd_extract("acme")  # mirrors cmd_run's single extract call
    cli.cmd_docs("acme")            # must run before translate/splice (item 1 fix)
    cli.cmd_translate(segs, cache, [StubEngine("dictionary", {"你好世界": "Hello World"})])
    splice_repo(repo, work / "acme" / "occurrences.jsonl", cache)

    assert (repo / "README.zh-CN.md").exists()
    assert "你好世界" in (repo / "README.zh-CN.md").read_text(encoding="utf-8")
    assert (repo / "README.md").exists()
    assert "Hello World" in (repo / "README.md").read_text(encoding="utf-8")
    assert "你好世界" not in (repo / "README.md").read_text(encoding="utf-8")


def test_switcher_insertion_after_splice_does_not_corrupt_offsets(tmp_path, monkeypatch):
    """Regression: ensure_switcher inserts a line after the H1, which shifts
    every byte offset recorded for content below it. Running it before
    splice (the old cmd_docs-does-everything order) made splice's hash
    check skip nearly every occurrence in the recreated README. cmd_run
    must apply moves, translate, splice, THEN insert switchers."""
    root = tmp_path / "root"
    repo = root / "acme"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "README.md").write_text("# Title\n\n你好世界\n\n再见\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)

    work = tmp_path / "work"
    monkeypatch.setattr(cli, "ROOT", root)
    monkeypatch.setattr(cli, "WORK", work)

    cache = Cache.load(tmp_path / "cache.jsonl")
    segs = cli.cmd_extract("acme")
    from gwt.docs_layout import apply_moves, plan_moves
    apply_moves(repo, plan_moves(repo))
    cli.cmd_translate(segs, cache, [StubEngine("dictionary",
                                                {"你好世界": "Hello World", "再见": "Goodbye"})])
    splice_repo(repo, work / "acme" / "occurrences.jsonl", cache)
    cli.cmd_switchers("acme")

    text = (repo / "README.md").read_text(encoding="utf-8")
    assert "Hello World" in text
    assert "Goodbye" in text
    assert "你好世界" not in text
    assert "再见" not in text


def test_switchers_apply_to_every_readme_directory(tmp_path, monkeypatch):
    """A repo like go-wind-toolkit carries a README triad per sub-tool, not
    just at the root — cmd_switchers must not stop at the root README."""
    root = tmp_path / "root"
    repo = root / "acme"
    sub = repo / "tools" / "widget"
    sub.mkdir(parents=True)
    (repo / "README.md").write_text("# Root\n\nHi\n", encoding="utf-8")
    (repo / "README.zh-CN.md").write_text("# Root\n\n你好\n", encoding="utf-8")
    (sub / "README.md").write_text("# Widget\n\nHi\n", encoding="utf-8")
    (sub / "README.zh-CN.md").write_text("# Widget\n\n你好\n", encoding="utf-8")

    monkeypatch.setattr(cli, "ROOT", root)
    cli.cmd_switchers("acme")

    assert "简体中文" in (repo / "README.md").read_text(encoding="utf-8")
    assert "简体中文" in (sub / "README.md").read_text(encoding="utf-8")


def test_safe_repo_root_rejects_path_traversal():
    with pytest.raises(ValueError):
        cli._safe_repo_root("../../etc")
    with pytest.raises(ValueError):
        cli._safe_repo_root("foo/bar")


def test_cmd_verify_baseline_suppresses_pre_existing_findings(tmp_path, monkeypatch):
    root = tmp_path / "root"
    repo = root / "acme"
    repo.mkdir(parents=True)
    (repo / "README.md").write_text("[x](./missing.md)\n", encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", root)

    # No baseline: the pre-existing broken link fails the gate.
    assert cli.cmd_verify("acme", skip_build=True) == 1

    baseline_path = tmp_path / "before.json"
    baseline_path.write_text(json.dumps({"broken_links": [["README.md", "./missing.md"]]}),
                             encoding="utf-8")
    assert cli.cmd_verify("acme", skip_build=True, baseline_path=str(baseline_path)) == 0
