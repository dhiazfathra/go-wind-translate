import pytest

from gwt.quality import fix_spacing, pad_comment_boundary


@pytest.mark.parametrize("text, expected", [
    ("UserIDInvalid", "UserID Invalid"),
    ("URIToo long", "URI Too long"),
    ("HTTPThis version is not supported", "HTTP This version is not supported"),
    ("QueryAPIList of Resources", "QueryAPI List of Resources"),
    ("tokenDoes not exist", "tokenDoes not exist"),  # no known acronym: left alone
])
def test_fix_spacing_inserts_space_after_glued_acronym(text, expected):
    assert fix_spacing(text) == expected


@pytest.mark.parametrize("text", [
    "UserID",
    "the UserID field",
    "OrderID must be unique",
    "isValidRequest",
    "HTTP request failed",
])
def test_fix_spacing_leaves_normal_text_untouched(text):
    assert fix_spacing(text) == text


def test_pad_comment_boundary_pads_after_leading_acronym():
    # Source "用户ID无效" has no space around ID (Chinese doesn't need one);
    # extraction narrows to "无效" only, leaving "ID" as untouched literal
    # text directly before the span.
    raw = "// UserID无效\n".encode("utf-8")
    start = raw.index("无效".encode())
    end = start + len("无效".encode())
    assert pad_comment_boundary(raw, start, end, "Invalid") == " Invalid"


def test_pad_comment_boundary_pads_before_trailing_acronym():
    raw = "// 太长URI\n".encode("utf-8")
    # The CJK span is "太长", occupying bytes [3:9) after "// ".
    start = 3
    end = start + len("太长".encode())
    assert pad_comment_boundary(raw, start, end, "Too long") == "Too long "


def test_pad_comment_boundary_pads_both_sides_for_multi_segment_glue():
    # "查询API列表" -> "Query" + "API" (literal) + "List": both translated
    # segments need their own side padded so the shared "API" boundary ends
    # up with exactly one space on each side, regardless of splice order.
    raw = "// 查询API列表\n".encode("utf-8")
    query_start = 3
    query_end = query_start + len("查询".encode())
    list_start = raw.index("列表".encode())
    list_end = list_start + len("列表".encode())

    assert pad_comment_boundary(raw, query_start, query_end, "Query") == "Query "
    assert pad_comment_boundary(raw, list_start, list_end, "List") == " List"


def test_pad_comment_boundary_leaves_ordinary_comment_text_untouched():
    raw = "// already fine\n".encode("utf-8")
    start = raw.index(b"fine")
    end = start + len(b"fine")
    assert pad_comment_boundary(raw, start, end, "fine") == "fine"


def test_pad_comment_boundary_pads_both_sides_inside_fullwidth_brackets():
    # "（配置项）" glues both the opening "（" and closing "）" directly onto
    # the span, same root cause as the acronym case: extraction narrows to
    # the CJK-letter run only, so the brackets outside it are never touched.
    raw = "// （配置项）get value\n".encode("utf-8")
    start = raw.index("（".encode()) + len("（".encode())
    end = raw.index("）".encode())
    assert pad_comment_boundary(raw, start, end, "Config item") == " Config item "


def test_pad_comment_boundary_pads_before_trailing_fullwidth_punct():
    raw = "// 说明。get value\n".encode("utf-8")
    start = 3
    end = start + len("说明".encode())
    assert pad_comment_boundary(raw, start, end, "Note") == "Note "


def test_pad_comment_boundary_pads_lowercase_word_on_leading_side():
    # A fullwidth punct mark can't be a code identifier, so leading-side
    # padding applies regardless of capitalization (symmetric with the
    # trailing-side fullwidth-punct check).
    raw = "// （配置项）get value\n".encode("utf-8")
    start = raw.index("（".encode()) + len("（".encode())
    end = raw.index("）".encode())
    assert pad_comment_boundary(raw, start, end, "config item") == " config item "
