import subprocess
import pytest
from gwt.docs_layout import ensure_switcher, plan_moves, switcher_line


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _commit(repo, *names):
    for n in names:
        p = repo / n
        p.parent.mkdir(parents=True, exist_ok=True)
        # Create Chinese content for README.md (the default is Chinese)
        if n == "README.md":
            p.write_text("# 中文\n", encoding="utf-8")
        else:
            p.write_text(f"# {n}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=repo, check=True)


def test_zh_readme_moves_aside(repo):
    _commit(repo, "README.md")
    moves = dict((a.name, b.name) for a, b in plan_moves(repo))
    assert moves["README.md"] == "README.zh-CN.md"


def test_existing_en_variant_is_promoted_to_default(repo):
    _commit(repo, "README.md", "README.en-US.md")
    moves = dict((a.name, b.name) for a, b in plan_moves(repo))
    assert moves["README.md"] == "README.zh-CN.md"
    assert moves["README.en-US.md"] == "README.md"


@pytest.mark.parametrize("variant", ["README_en.md", "README_EN.md", "README.en.md"])
def test_all_en_naming_variants_normalize(repo, variant):
    _commit(repo, "README.md", variant)
    moves = dict((a.name, b.name) for a, b in plan_moves(repo))
    assert moves[variant] == "README.md"


def test_ja_variants_normalize_to_ja_jp(repo):
    _commit(repo, "README.md", "README_ja.md")
    moves = dict((a.name, b.name) for a, b in plan_moves(repo))
    assert moves["README_ja.md"] == "README.ja-JP.md"


def test_docs_dir_chinese_files_move_under_zh_cn(repo):
    _commit(repo, "docs/architecture.md")
    (repo / "docs/architecture.md").write_text("# 架构设计\n", encoding="utf-8")
    moves = {str(a.relative_to(repo)): str(b.relative_to(repo)) for a, b in plan_moves(repo)}
    assert moves["docs/architecture.md"] == "docs/zh-CN/architecture.md"


def test_agent_files_are_never_moved(repo):
    _commit(repo, "CLAUDE.md", "AGENTS.md", "SKILL.md")
    names = {a.name for a, _ in plan_moves(repo)}
    assert names.isdisjoint({"CLAUDE.md", "AGENTS.md", "SKILL.md"})


def test_switcher_line_format():
    line = switcher_line({"en": "./README.md", "zh-CN": "./README.zh-CN.md"})
    assert line == "[English](./README.md) · [简体中文](./README.zh-CN.md)"


def test_ensure_switcher_is_idempotent(tmp_path):
    p = tmp_path / "README.md"
    p.write_text("# Title\n\nBody\n", encoding="utf-8")
    variants = {"en": "./README.md", "zh-CN": "./README.zh-CN.md"}
    assert ensure_switcher(p, variants) is True
    once = p.read_text(encoding="utf-8")
    assert ensure_switcher(p, variants) is False
    assert p.read_text(encoding="utf-8") == once


def test_switcher_goes_after_h1(tmp_path):
    p = tmp_path / "README.md"
    p.write_text("# Title\n\nBody\n", encoding="utf-8")
    ensure_switcher(p, {"en": "./README.md", "zh-CN": "./README.zh-CN.md"})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Title"
    assert "简体中文" in lines[2]
