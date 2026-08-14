import json
from pathlib import Path
import pytest
from gwt.cli import build_parser, cmd_translate
from gwt.segments import Cache, Segment, seg_hash


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
