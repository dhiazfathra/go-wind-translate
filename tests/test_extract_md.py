from pathlib import Path
from gwt.extract import extract_file

FIX = Path(__file__).parent / "fixtures" / "sample.md"


def _texts(segs):
    return [s.src for s in segs]


def test_translates_headings_and_prose():
    segs, _ = extract_file(FIX, "sample.md")
    texts = _texts(segs)
    assert "用户服务文档" in texts
    assert any("普通段落" in t for t in texts)


def test_skips_fenced_code_blocks():
    segs, _ = extract_file(FIX, "sample.md")
    joined = " ".join(_texts(segs))
    assert "这段注释在代码块内" not in joined
    assert "你好" not in joined


def test_skips_inline_code_and_urls():
    segs, _ = extract_file(FIX, "sample.md")
    assert not any("CreateUser" in t for t in _texts(segs))
    assert not any("example.com" in t for t in _texts(segs))


def test_translates_link_label_but_not_target():
    segs, _ = extract_file(FIX, "sample.md")
    assert "文档" in _texts(segs)


def test_offsets_slice_back():
    raw = FIX.read_bytes()
    segs, occs = extract_file(FIX, "sample.md")
    by_hash = {s.h: s.src for s in segs}
    for o in occs:
        assert raw[o.start:o.end].decode("utf-8") == by_hash[o.h]
