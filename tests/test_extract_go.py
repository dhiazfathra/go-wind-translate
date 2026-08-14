from pathlib import Path

from gwt.extract import extract_file

FIX = Path(__file__).parent / "fixtures" / "sample.go"


def _texts(segs):
    return [s.src for s in segs]


def test_extracts_doc_and_line_comments():
    segs, occs = extract_file(FIX, "sample.go")
    texts = _texts(segs)
    assert "用户仓储实现" in texts
    assert "提供用户的增删改查能力" in texts
    assert "默认用户名" in texts


def test_identifier_prefix_is_not_part_of_segment():
    """`// UserRepo 用户仓储实现` must yield only the Chinese half."""
    segs, _ = extract_file(FIX, "sample.go")
    assert "用户仓储实现" in _texts(segs)
    assert not any("UserRepo" in s.src for s in segs)
    assert not any(s.src.startswith("//") for s in segs)


def test_extracts_string_literals_with_cjk():
    segs, _ = extract_file(FIX, "sample.go")
    texts = _texts(segs)
    assert any("创建用户失败" in t for t in texts)
    assert "张三" in texts


def test_ignores_ascii_only_comments():
    segs, _ = extract_file(FIX, "sample.go")
    assert not any(s.src.strip() == "TODO" for s in segs)
    assert all(any("一" <= c <= "鿿" for c in s.src) for s in segs)


def test_offsets_slice_back_to_source_text():
    raw = FIX.read_bytes()
    segs, occs = extract_file(FIX, "sample.go")
    by_hash = {s.h: s.src for s in segs}
    for o in occs:
        assert raw[o.start:o.end].decode("utf-8") == by_hash[o.h]


def test_occurrences_do_not_overlap():
    _, occs = extract_file(FIX, "sample.go")
    spans = sorted((o.start, o.end) for o in occs)
    for (_, e1), (s2, _) in zip(spans, spans[1:]):
        assert e1 <= s2
