import json

from gwt.repair import Correction, apply_corrections, load_corrections, repair_cache

ROLE = Correction("角色", "Character", "Role")


def test_rewrites_when_zh_term_present():
    assert apply_corrections("角色代码分隔符", "Character code separator", [ROLE]) == "Role code separator"


def test_leaves_en_alone_when_zh_term_absent():
    # A genuine "character" (as in a char) must survive.
    assert apply_corrections("字符编码", "Character encoding", [ROLE]) == "Character encoding"


def test_does_not_split_words():
    assert apply_corrections("角色", "Characters", [ROLE]) == "Characters"
    assert apply_corrections("角色", "Characters", [ROLE, Correction("角色", "Characters", "Roles")]) == "Roles"


def test_repairs_only_matching_records(tmp_path):
    cache = tmp_path / "segments.jsonl"
    cache.write_text(
        json.dumps({"h": "a", "src": "角色名称", "en": "Character Name", "engine": "deepl"}, ensure_ascii=False)
        + "\n"
        + json.dumps({"h": "b", "src": "字符集", "en": "Character set", "engine": "deepl"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    count, changed = repair_cache(cache, [ROLE])
    assert count == 1
    assert changed[0]["after"] == "Role Name"
    rows = [json.loads(x) for x in cache.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["engine"] == "phase2-repair"
    assert rows[1]["en"] == "Character set"


def test_shipped_corrections_table_parses():
    from pathlib import Path

    rows = load_corrections(Path(__file__).parent.parent / "corrections.tsv")
    assert len(rows) > 50
    assert Correction("角色", "Character", "Role") in rows


def test_single_word_pairs_are_not_propagated_by_text_search():
    # "Execute" -> "Enforcement" rewrote a Go call site to root.Enforcement().
    from gwt.propagate import _safe_literal

    assert not _safe_literal("Execute")
    assert not _safe_literal("Equipment")
    assert _safe_literal("Git Warehouse")


def test_ambiguous_before_values_are_not_propagated():
    # 错误的请求 / 不可接受的请求 both came back as "Invalid Request"; text search
    # cannot tell which occurrence is which.
    from gwt.propagate import propagate

    changed = [
        {"before": "Invalid Request Here", "after": "Not Acceptable"},
        {"before": "Invalid Request Here", "after": "Misdirected Request"},
    ]
    import subprocess, tempfile
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True)
        f = __import__("pathlib").Path(d) / "a.go"
        f.write_text("// Invalid Request Here\n")
        subprocess.run(["git", "-C", d, "add", "a.go"], check=True)
        files, reps, skipped = propagate(__import__("pathlib").Path(d), changed)
        assert reps == 0
        assert len(skipped) == 2
        assert f.read_text() == "// Invalid Request Here\n"


def test_collapses_a_word_the_substitution_duplicated():
    # 站内信消息 came back as "Inbox Messages"; rewriting 站内信 to "Internal Message"
    # would otherwise leave "Internal Message Messages".
    got = apply_corrections("站内信消息列表", "Inbox Message Message List", [Correction("站内信", "Inbox Message", "Internal Message")])
    assert got == "Internal Message List"


def test_collapses_a_gloss_the_substitution_made_redundant():
    got = apply_corrections("会话（Session）", "Conversation (Session)", [Correction("会话", "Conversation", "Session")])
    assert got == "Session"
