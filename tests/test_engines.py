import pytest
from gwt.engines import get_engine
from gwt.engines.dictionary import DictionaryEngine


def test_dictionary_exact_match(tmp_path):
    tsv = tmp_path / "d.tsv"
    tsv.write_text("创建\tCreate\n删除\tDelete\n", encoding="utf-8")
    e = DictionaryEngine(tsv)
    assert e.translate(["创建", "删除"]) == ["Create", "Delete"]


def test_dictionary_miss_returns_empty_string(tmp_path):
    tsv = tmp_path / "d.tsv"
    tsv.write_text("创建\tCreate\n", encoding="utf-8")
    assert DictionaryEngine(tsv).translate(["未知词"]) == [""]


def test_dictionary_ignores_blank_and_comment_lines(tmp_path):
    tsv = tmp_path / "d.tsv"
    tsv.write_text("# comment\n\n创建\tCreate\n", encoding="utf-8")
    assert DictionaryEngine(tsv).translate(["创建"]) == ["Create"]


def test_dictionary_normalizes_whitespace(tmp_path):
    tsv = tmp_path / "d.tsv"
    tsv.write_text("创建 用户\tCreate user\n", encoding="utf-8")
    assert DictionaryEngine(tsv).translate(["创建  用户"]) == ["Create user"]


def test_get_engine_returns_named_engine():
    assert get_engine("dictionary").name == "dictionary"
    with pytest.raises(ValueError, match="unknown engine"):
        get_engine("nope")


def test_engine_preserves_input_length():
    e = get_engine("dictionary")
    assert len(e.translate(["甲", "乙", "丙"])) == 3


def test_dictionary_pins_180tian_mistranslation():
    # DeepL returned "180Tian" for this segment -- an untranslated
    # transliteration of the day-count suffix, not a boundary artifact.
    # Pinned in dictionary.tsv so it never reaches the MT engine.
    e = get_engine("dictionary")
    assert e.translate(["180天"]) == ["180 days"]
