from gwt.mask import protect, unprotect


def test_protects_camel_and_pascal_case():
    assert protect("获取 getUserList 数据") == "获取 <x>getUserList</x> 数据"
    assert protect("调用 UserRepo 方法") == "调用 <x>UserRepo</x> 方法"


def test_protects_snake_case_and_calls():
    assert protect("设置 max_retry 次数") == "设置 <x>max_retry</x> 次数"
    assert protect("执行 doWork() 后") == "执行 <x>doWork</x>() 后"


def test_protects_urls_and_backticks():
    assert protect("见 https://a.b/c 页面") == "见 <x>https://a.b/c</x> 页面"
    assert protect("用 `ent.Client` 查询") == "用 <x>`ent.Client`</x> 查询"


def test_protects_glossary_terms_even_when_lowercase():
    # 'kratos' and 'ent' are lowercase and would otherwise look like prose
    assert protect("基于 kratos 框架") == "基于 <x>kratos</x> 框架"
    assert protect("使用 ent 生成") == "使用 <x>ent</x> 生成"


def test_leaves_ordinary_english_words_alone():
    assert protect("这是 a simple test 的说明") == "这是 a simple test 的说明"


def test_protects_format_verbs():
    assert protect("创建用户失败: %w") == "创建用户失败: <x>%w</x>"
    assert protect("已处理 {count} 条") == "已处理 <x>{count}</x> 条"


def test_roundtrip_is_lossless():
    for s in ["获取 getUserList 数据", "见 https://a.b/c 页面", "创建用户失败: %w"]:
        assert unprotect(protect(s)) == s


def test_unprotect_strips_only_our_tag():
    assert unprotect("<x>Foo</x> 和 <b>bold</b>") == "Foo 和 <b>bold</b>"


def test_protects_camelcase_adjacent_to_cjk():
    # Critical: Python \b treats CJK as \w, creating false word boundary.
    # Must use explicit lookaround to mask identifiers directly adjacent to Chinese.
    assert protect("GetUserList获取用户列表") == "<x>GetUserList</x>获取用户列表"
    assert protect("执行doWork()后返回") == "执行<x>doWork</x>()后返回"


def test_protects_snake_case_adjacent_to_cjk():
    assert protect("设置max_retry次数") == "设置<x>max_retry</x>次数"


def test_protects_dotted_identifier_adjacent_to_cjk():
    assert protect("调用user.Repo.Get方法") == "调用<x>user.Repo.Get</x>方法"
