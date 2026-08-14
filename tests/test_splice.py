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


def test_string_kind_leaves_glued_acronym_cache_value_unchanged(tmp_path):
    # The cache is keyed by source hash and shared across every occurrence
    # of that segment. If the SAME segment is also spliced into a comment
    # elsewhere, the comment-only fix_spacing()/pad_comment_boundary() pass
    # must never touch the cached value itself -- only the copy going into
    # a "string"/"raw_string" span, where "APIClient" is a real identifier
    # and must survive intact.
    f = tmp_path / "a.go"
    f.write_text('x := "接口客户端"\n', encoding="utf-8")
    raw = f.read_bytes()
    zh = "接口客户端"
    start = raw.index(zh.encode())
    occ = [Occurrence(file="a.go", start=start, end=start + len(zh.encode()),
                      h=seg_hash(zh), kind="string")]
    n = splice_file(f, occ, _cache(tmp_path, [(zh, "APIClient")]))
    assert n == 1
    assert f.read_text(encoding="utf-8") == 'x := "APIClient"\n'


def test_raw_string_kind_leaves_glued_acronym_cache_value_unchanged(tmp_path):
    f = tmp_path / "a.go"
    f.write_text('var name = `接口客户端`\n', encoding="utf-8")
    raw = f.read_bytes()
    zh = "接口客户端"
    start = raw.index(zh.encode())
    occ = [Occurrence(file="a.go", start=start, end=start + len(zh.encode()),
                      h=seg_hash(zh), kind="raw_string")]
    n = splice_file(f, occ, _cache(tmp_path, [(zh, "APIClient")]))
    assert n == 1
    assert f.read_text(encoding="utf-8") == 'var name = `APIClient`\n'


def test_string_kind_escapes_embedded_quotes(tmp_path):
    # DeepL sometimes wraps a negation word in literal quotes for emphasis
    # (observed: 非 -> "not"). Spliced raw into a Go string literal, that
    # quote terminates it early and breaks the build.
    f = tmp_path / "a.go"
    f.write_text('t.Fatalf("Ctx.Err() 应为非 nil")\n', encoding="utf-8")
    raw = f.read_bytes()
    zh = "应为非 nil"
    start = raw.index(zh.encode())
    occ = [Occurrence(file="a.go", start=start, end=start + len(zh.encode()),
                      h=seg_hash(zh), kind="string")]
    en = 'Should be "not" nil'
    n = splice_file(f, occ, _cache(tmp_path, [(zh, en)]))
    assert n == 1
    result = f.read_text(encoding="utf-8")
    assert result == 't.Fatalf("Ctx.Err() Should be \\"not\\" nil")\n'


def test_raw_string_kind_leaves_backslash_and_quotes_unescaped(tmp_path):
    # A Go raw string (backtick-delimited) treats backslash and double-quote
    # as literal bytes, not escapes. Applying interpreted-string escaping
    # here would corrupt content like a Windows path or an embedded quote.
    f = tmp_path / "a.go"
    f.write_text('var tmpl = `原始路径`\n', encoding="utf-8")
    raw = f.read_bytes()
    zh = "原始路径"
    start = raw.index(zh.encode())
    occ = [Occurrence(file="a.go", start=start, end=start + len(zh.encode()),
                      h=seg_hash(zh), kind="raw_string")]
    en = r'C:\tmp "quoted"'
    n = splice_file(f, occ, _cache(tmp_path, [(zh, en)]))
    assert n == 1
    assert f.read_text(encoding="utf-8") == 'var tmpl = `C:\\tmp "quoted"`\n'


def test_raw_string_kind_skips_translation_containing_backtick(tmp_path):
    # A raw string literal cannot represent a literal backtick -- it would
    # terminate the literal early and break the build. Skip rather than
    # emit invalid source.
    f = tmp_path / "a.go"
    f.write_text('var tmpl = `原始`\n', encoding="utf-8")
    raw = f.read_bytes()
    zh = "原始"
    start = raw.index(zh.encode())
    occ = [Occurrence(file="a.go", start=start, end=start + len(zh.encode()),
                      h=seg_hash(zh), kind="raw_string")]
    en = "has a ` backtick"
    n = splice_file(f, occ, _cache(tmp_path, [(zh, en)]))
    assert n == 0
    assert f.read_text(encoding="utf-8") == 'var tmpl = `原始`\n'


def test_comment_kind_pads_glued_acronym_boundary(tmp_path):
    # Chinese needs no space between a Latin identifier fragment and
    # surrounding prose ("UserID无效"); splicing "Invalid" straight into
    # that CJK-only span reproduces the same zero-width join in English
    # ("UserIDInvalid"), which isn't readable. Comment-kind splicing pads it.
    f = tmp_path / "a.go"
    f.write_text("// UserID无效\n", encoding="utf-8")
    raw = f.read_bytes()
    zh = "无效"
    start = raw.index(zh.encode())
    occ = [Occurrence(file="a.go", start=start, end=start + len(zh.encode()),
                      h=seg_hash(zh), kind="comment")]
    n = splice_file(f, occ, _cache(tmp_path, [(zh, "Invalid")]))
    assert n == 1
    assert f.read_text(encoding="utf-8") == "// UserID Invalid\n"


def test_comment_kind_pads_glued_fullwidth_bracket_boundary(tmp_path):
    # "（配置项）" glues both full-width brackets directly onto the
    # translated span for the same reason as the acronym case: extraction
    # narrows to the CJK-letter run only, so the brackets outside it are
    # never touched by translation.
    f = tmp_path / "a.go"
    f.write_text("// （配置项）get value\n", encoding="utf-8")
    raw = f.read_bytes()
    zh = "配置项"
    start = raw.index(zh.encode())
    occ = [Occurrence(file="a.go", start=start, end=start + len(zh.encode()),
                      h=seg_hash(zh), kind="comment")]
    n = splice_file(f, occ, _cache(tmp_path, [(zh, "Config item")]))
    assert n == 1
    assert f.read_text(encoding="utf-8") == "// （ Config item ）get value\n"


def test_comment_kind_leaves_quotes_unescaped(tmp_path):
    f = tmp_path / "a.go"
    f.write_text("// 创建用户\n", encoding="utf-8")
    raw = f.read_bytes()
    zh = "创建用户"
    start = raw.index(zh.encode())
    occ = [Occurrence(file="a.go", start=start, end=start + len(zh.encode()),
                      h=seg_hash(zh), kind="comment")]
    n = splice_file(f, occ, _cache(tmp_path, [(zh, 'Create "user"')]))
    assert n == 1
    assert f.read_text(encoding="utf-8") == '// Create "user"\n'


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
