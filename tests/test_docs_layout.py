import subprocess
import pytest
from gwt.docs_layout import apply_moves, ensure_switcher, plan_moves, switcher_line


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


def test_apply_moves_with_existing_en_variant_does_not_collide(repo):
    # Archiving README.md -> README.zh-CN.md recreates README.md so it can
    # later be translated in place — but here README_en.md is also being
    # promoted onto README.md. The promote move must win; recreating the
    # archived copy at README.md first must not collide with it.
    _commit(repo, "README.md", "README_en.md")
    moves = plan_moves(repo)
    apply_moves(repo, moves)
    assert (repo / "README.zh-CN.md").read_text(encoding="utf-8") == "# 中文\n"
    assert (repo / "README.md").read_text(encoding="utf-8") == "# README_en.md\n"


def test_ja_variants_normalize_to_ja_jp(repo):
    _commit(repo, "README.md", "README_ja.md")
    moves = dict((a.name, b.name) for a, b in plan_moves(repo))
    assert moves["README_ja.md"] == "README.ja-JP.md"


def test_docs_dir_chinese_files_move_under_zh_cn(repo):
    _commit(repo, "docs/architecture.md")
    (repo / "docs/architecture.md").write_text("# 架构设计\n", encoding="utf-8")
    moves = {str(a.relative_to(repo)): str(b.relative_to(repo)) for a, b in plan_moves(repo)}
    assert moves["docs/architecture.md"] == "docs/zh-CN/architecture.md"


def test_docs_move_rewrites_relative_links_in_the_archived_copy(repo):
    # docs/architecture.md -> docs/zh-CN/architecture.md drops one
    # directory level deeper; its existing "../backend/x.md" link now
    # needs an extra "../" to still resolve. The recreated original at
    # docs/architecture.md stays at the same depth and must NOT change.
    _commit(repo, "docs/architecture.md")
    (repo / "docs/architecture.md").write_text(
        "# 架构设计\n\n[部署](../backend/docs/deploy.md)\n[外部](https://example.com)\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "content"], cwd=repo, check=True)

    apply_moves(repo, plan_moves(repo))

    archived = (repo / "docs/zh-CN/architecture.md").read_text(encoding="utf-8")
    assert "(../../backend/docs/deploy.md)" in archived
    assert "(https://example.com)" in archived

    recreated = (repo / "docs/architecture.md").read_text(encoding="utf-8")
    assert "(../backend/docs/deploy.md)" in recreated


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


def test_switcher_replaces_stale_pre_move_line(tmp_path):
    # The repo already had its own switcher pointing at the pre-move
    # filenames (README_en.md); after the doc move renames those files
    # away, that line's links 404. ensure_switcher must replace it, not
    # leave it dangling alongside the new correct one.
    p = tmp_path / "README.md"
    p.write_text(
        "# Title\n\n中文 · [English](./README_en.md) · [日本語](./README_ja.md)\n\nBody\n",
        encoding="utf-8",
    )
    variants = {"en": "./README.md", "zh-CN": "./README.zh-CN.md", "ja-JP": "./README.ja-JP.md"}
    assert ensure_switcher(p, variants) is True
    text = p.read_text(encoding="utf-8")
    assert "README_en.md" not in text
    assert "README_ja.md" not in text
    assert switcher_line(variants) in text


def test_switcher_replaces_stale_pipe_separated_line(tmp_path):
    # Some repos use " | " instead of " · " for their own hand-written
    # switcher — detection must not depend on the separator character.
    p = tmp_path / "README.md"
    p.write_text(
        "# Title\n\n[中文](README.md) | **[English](README_EN.md)** | [Japanese](README_JA.md)\n\nBody\n",
        encoding="utf-8",
    )
    variants = {"en": "./README.md", "zh-CN": "./README.zh-CN.md", "ja-JP": "./README.ja-JP.md"}
    assert ensure_switcher(p, variants) is True
    text = p.read_text(encoding="utf-8")
    assert "README_EN.md" not in text
    assert "README_JA.md" not in text
    assert switcher_line(variants) in text


def test_switcher_replaces_stale_single_mention_line_near_h1(tmp_path):
    # A 2-language switcher's current-language side needs no link (it's
    # already this file) -- "README" appears only once on the line.
    p = tmp_path / "README.zh-CN.md"
    p.write_text(
        "# Title\n\n[English](./README.en-US.md) | **中文**\n\nBody\n",
        encoding="utf-8",
    )
    variants = {"en": "./README.md", "zh-CN": "./README.zh-CN.md"}
    assert ensure_switcher(p, variants) is True
    text = p.read_text(encoding="utf-8")
    assert "README.en-US.md" not in text
    assert switcher_line(variants) in text


def test_switcher_leaves_unrelated_readme_mention_further_down(tmp_path):
    # A single README mention away from the H1, with no switcher shape,
    # is ordinary prose -- must survive untouched.
    p = tmp_path / "README.md"
    p.write_text(
        "# Title\n\nIntro paragraph.\n\n"
        "## Docs\n\nSee [the README](./README.md) for setup | more details.\n",
        encoding="utf-8",
    )
    variants = {"en": "./README.md", "zh-CN": "./README.zh-CN.md"}
    ensure_switcher(p, variants)
    text = p.read_text(encoding="utf-8")
    assert "See [the README](./README.md) for setup | more details." in text


def test_switcher_goes_after_h1(tmp_path):
    p = tmp_path / "README.md"
    p.write_text("# Title\n\nBody\n", encoding="utf-8")
    ensure_switcher(p, {"en": "./README.md", "zh-CN": "./README.zh-CN.md"})
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "# Title"
    assert "简体中文" in lines[2]
