import subprocess
from gwt.verify import broken_doc_links, build_commands, identifier_drift, residual_cjk


def test_residual_cjk_reports_translatable_files_only(tmp_path):
    (tmp_path / "a.go").write_text("// 未翻译\n", encoding="utf-8")
    loc = tmp_path / "src" / "locales" / "zh-CN"
    loc.mkdir(parents=True)
    (loc / "menu.json").write_text('{"home":"首页"}\n', encoding="utf-8")
    hits = dict(residual_cjk(tmp_path))
    assert "a.go" in hits
    assert not any("locales" in k for k in hits)


def test_residual_cjk_is_empty_when_clean(tmp_path):
    (tmp_path / "a.go").write_text("// translated\n", encoding="utf-8")
    assert residual_cjk(tmp_path) == []


def test_broken_doc_links_flags_missing_target(tmp_path):
    (tmp_path / "README.md").write_text(
        "# T\n\n[English](./README.md) · [简体中文](./README.zh-CN.md)\n", encoding="utf-8")
    assert ("README.md", "./README.zh-CN.md") in broken_doc_links(tmp_path)


def test_broken_doc_links_passes_when_target_exists(tmp_path):
    (tmp_path / "README.md").write_text(
        "# T\n\n[简体中文](./README.zh-CN.md)\n", encoding="utf-8")
    (tmp_path / "README.zh-CN.md").write_text("# 标题\n", encoding="utf-8")
    assert broken_doc_links(tmp_path) == []


def test_broken_doc_links_ignores_external_urls(tmp_path):
    (tmp_path / "README.md").write_text("[x](https://example.com/y)\n", encoding="utf-8")
    assert broken_doc_links(tmp_path) == []


def test_broken_doc_links_ignores_examples_in_code(tmp_path):
    """Docs show example link syntax for other repos; that is not a broken link."""
    (tmp_path / "README.md").write_text(
        "Switcher: `[English](./README.md) · [简体中文](./README.zh-CN.md)`\n"
        "\n"
        "```markdown\n"
        "[English](./README.md) · [日本語](./README.ja-JP.md)\n"
        "```\n",
        encoding="utf-8")
    assert broken_doc_links(tmp_path) == []


def test_identifier_drift_flags_changed_code_line(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    f = tmp_path / "a.go"
    f.write_text("func GetUser() {}\n// 注释\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "i"], cwd=tmp_path, check=True)

    f.write_text("func GetUserList() {}\n// Comment\n", encoding="utf-8")
    drift = identifier_drift(tmp_path)
    assert any("GetUserList" in d for d in drift)


def test_identifier_drift_ignores_markdown_prose(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    f = tmp_path / "README.md"
    f.write_text("依赖方向：`cmd -> server`\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "i"], cwd=tmp_path, check=True)

    f.write_text("Dependency Direction:`cmd -> server`\n", encoding="utf-8")
    assert identifier_drift(tmp_path) == []


def test_identifier_drift_ignores_comment_only_change(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    f = tmp_path / "a.go"
    f.write_text("func GetUser() {}\n// 注释\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "i"], cwd=tmp_path, check=True)

    f.write_text("func GetUser() {}\n// Comment\n", encoding="utf-8")
    assert identifier_drift(tmp_path) == []


def test_build_commands_uses_makefile_when_present(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend" / "Makefile").write_text("gen:\n\techo gen\nbuild:\n\techo build\n",
                                                   encoding="utf-8")
    cmds = build_commands(tmp_path)
    assert ["make", "gen"] in cmds
    assert ["make", "build"] in cmds


def test_build_commands_falls_back_to_go_build(tmp_path):
    (tmp_path / "go.mod").write_text("module x\n", encoding="utf-8")
    assert ["go", "build", "./..."] in build_commands(tmp_path)
