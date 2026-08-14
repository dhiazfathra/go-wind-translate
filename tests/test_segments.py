from gwt.segments import Cache, Occurrence, Segment, seg_hash, read_occurrences, write_occurrences


def test_hash_is_whitespace_and_unicode_stable():
    assert seg_hash("创建用户") == seg_hash("  创建用户  ")
    assert seg_hash("创建 用户") == seg_hash("创建  用户")
    assert seg_hash("创建用户") != seg_hash("删除用户")


def test_cache_roundtrip(tmp_path):
    p = tmp_path / "segments.jsonl"
    c = Cache.load(p)
    assert c.get(seg_hash("创建用户")) is None
    c.put(seg_hash("创建用户"), "创建用户", "Create user", "deepl")
    c.save()

    c2 = Cache.load(p)
    assert c2.get(seg_hash("创建用户")) == "Create user"


def test_cache_missing_filters_known(tmp_path):
    c = Cache.load(tmp_path / "s.jsonl")
    a, b = seg_hash("甲"), seg_hash("乙")
    c.put(a, "甲", "A", "dict")
    assert c.missing([a, b]) == [b]


def test_cache_put_is_idempotent_and_append_safe(tmp_path):
    p = tmp_path / "s.jsonl"
    c = Cache.load(p)
    h = seg_hash("重复")
    c.put(h, "重复", "Duplicate", "dict")
    c.put(h, "重复", "Duplicate", "dict")
    c.save()
    assert p.read_text(encoding="utf-8").strip().count("\n") == 0  # exactly one line


def test_occurrences_roundtrip(tmp_path):
    p = tmp_path / "occ.jsonl"
    occs = [Occurrence(file="a.go", start=10, end=20, h="abc"),
            Occurrence(file="a.go", start=30, end=40, h="def")]
    write_occurrences(p, occs)
    assert read_occurrences(p) == occs


def test_segment_dataclass_fields():
    s = Segment(h="x", src="中", kind="line_comment", lang="go")
    assert (s.h, s.src, s.kind, s.lang) == ("x", "中", "line_comment", "go")
