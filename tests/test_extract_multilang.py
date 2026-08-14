from pathlib import Path
import pytest
from gwt.extract import extract_file

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name,expect_present,expect_absent", [
    ("sample.proto", ["用户服务", "创建用户", "用户名"], ["UserService", "CreateUser"]),
    ("sample.vue", ["用户列表", "加载用户数据", "用户管理"], ["setup", "const"]),
])
def test_extracts_and_never_captures_identifiers(name, expect_present, expect_absent):
    segs, occs = extract_file(FIX / name, name)
    texts = " ".join(s.src for s in segs)
    for want in expect_present:
        assert want in texts, f"{name}: missing {want}"
    for reject in expect_absent:
        assert reject not in texts, f"{name}: leaked identifier {reject}"


@pytest.mark.parametrize("name", ["sample.proto", "sample.vue"])
def test_offsets_slice_back(name):
    raw = (FIX / name).read_bytes()
    segs, occs = extract_file(FIX / name, name)
    by_hash = {s.h: s.src for s in segs}
    for o in occs:
        assert raw[o.start:o.end].decode("utf-8") == by_hash[o.h]
