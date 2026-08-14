from gwt.segments import Cache, Occurrence, seg_hash
from gwt.splice import splice_file


def _cache(tmp_path, pairs):
    c = Cache.load(tmp_path / "s.jsonl")
    for zh, en in pairs:
        c.put(seg_hash(zh), zh, en, "test")
    return c


def test_replaces_single_span(tmp_path):
    f = tmp_path / "a.go"
    f.write_text("// 创建用户\n", encoding="utf-8")
    raw = f.read_bytes()
    start = raw.index("创建用户".encode())
    occ = [Occurrence(file="a.go", start=start,
                      end=start + len("创建用户".encode()), h=seg_hash("创建用户"))]
    n = splice_file(f, occ, _cache(tmp_path, [("创建用户", "Create user")]))
    assert n == 1
    assert f.read_text(encoding="utf-8") == "// Create user\n"


def test_multiple_spans_keep_offsets_valid(tmp_path):
    f = tmp_path / "b.go"
    f.write_text("// 甲\nx := \"乙\"\n// 丙\n", encoding="utf-8")
    raw = f.read_bytes()
    occs = []
    for zh in ("甲", "乙", "丙"):
        s = raw.index(zh.encode())
        occs.append(Occurrence(file="b.go", start=s, end=s + len(zh.encode()), h=seg_hash(zh)))
    cache = _cache(tmp_path, [("甲", "A"), ("乙", "B"), ("丙", "C")])
    assert splice_file(f, occs, cache) == 3
    assert f.read_text(encoding="utf-8") == "// A\nx := \"B\"\n// C\n"


def test_replacement_longer_than_source_still_lands(tmp_path):
    """English is usually longer than Chinese - the classic offset-drift bug."""
    f = tmp_path / "c.go"
    f.write_text("// 甲\n// 乙\n", encoding="utf-8")
    raw = f.read_bytes()
    occs = []
    for zh in ("甲", "乙"):
        s = raw.index(zh.encode())
        occs.append(Occurrence(file="c.go", start=s, end=s + len(zh.encode()), h=seg_hash(zh)))
    cache = _cache(tmp_path, [("甲", "a very long replacement string"), ("乙", "another long one")])
    splice_file(f, occs, cache)
    assert f.read_text(encoding="utf-8") == "// a very long replacement string\n// another long one\n"


def test_uncached_span_is_left_untouched(tmp_path):
    f = tmp_path / "d.go"
    f.write_text("// 未翻译\n", encoding="utf-8")
    raw = f.read_bytes()
    s = raw.index("未翻译".encode())
    occ = [Occurrence(file="d.go", start=s, end=s + len("未翻译".encode()), h=seg_hash("未翻译"))]
    assert splice_file(f, occ, _cache(tmp_path, [])) == 0
    assert f.read_text(encoding="utf-8") == "// 未翻译\n"


def test_result_is_valid_utf8(tmp_path):
    f = tmp_path / "e.go"
    f.write_text("// 甲乙丙\n", encoding="utf-8")
    raw = f.read_bytes()
    s = raw.index("甲乙丙".encode())
    occ = [Occurrence(file="e.go", start=s, end=s + len("甲乙丙".encode()), h=seg_hash("甲乙丙"))]
    splice_file(f, occ, _cache(tmp_path, [("甲乙丙", "ABC")]))
    f.read_text(encoding="utf-8")  # raises if invalid
