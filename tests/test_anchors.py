"""In-page anchor repair after a heading is translated.

ADR-0007: a link *target* is masked and never translated, but a heading's
text is. That combination silently breaks every `](#chinese-slug)` pointing
at a heading the pipeline just rewrote -- and `broken_doc_links` skips
`#`-prefixed targets by design, so nothing caught it.
"""
from gwt.quality import heading_slug, repair_anchors


def test_heading_slug_matches_github_convention():
    assert heading_slug("## Architecture Overview") == "architecture-overview"
    assert heading_slug("# API 两层架构") == "api-两层架构"
    assert heading_slug("### Two-Tier: A Detailed Explanation!") == \
        "two-tier-a-detailed-explanation"


def test_repairs_anchor_whose_heading_was_translated():
    before = "# 架构概览\n\n- [Overview](#架构概览)\n".encode("utf-8")
    after = "# Architecture Overview\n\n- [Overview](#架构概览)\n".encode("utf-8")
    out = repair_anchors(before, after).decode("utf-8")
    assert out == "# Architecture Overview\n\n- [Overview](#architecture-overview)\n"


def test_repairs_partially_translated_heading():
    # "## API 两层架构" -> "## API Two-Tier Architecture": the slug mixes a
    # Latin run with the CJK one, so the anchor can't be derived from the
    # translated segment alone -- it needs the whole heading line.
    before = "## API 两层架构\n\n[x](#api-两层架构)\n".encode("utf-8")
    after = "## API Two-Tier Architecture\n\n[x](#api-两层架构)\n".encode("utf-8")
    out = repair_anchors(before, after).decode("utf-8")
    assert "[x](#api-two-tier-architecture)" in out


def test_repairs_cross_file_anchor_target():
    before = "# 目录结构\n\n[x](./README.md#目录结构)\n".encode("utf-8")
    after = "# Directory Structure\n\n[x](./README.md#目录结构)\n".encode("utf-8")
    out = repair_anchors(before, after).decode("utf-8")
    assert "[x](./README.md#directory-structure)" in out


def test_leaves_anchor_with_no_matching_heading_alone():
    # An anchor pointing at something that was never a heading in this file
    # (e.g. a heading in another document) must not be rewritten by guesswork.
    before = "# 架构概览\n\n[x](#别的东西)\n".encode("utf-8")
    after = "# Architecture Overview\n\n[x](#别的东西)\n".encode("utf-8")
    out = repair_anchors(before, after).decode("utf-8")
    assert "[x](#别的东西)" in out


def test_leaves_untranslated_heading_anchor_untouched():
    before = "# 架构概览\n\n[x](#架构概览)\n".encode("utf-8")
    out = repair_anchors(before, before)
    assert out == before


def test_no_headings_is_a_noop():
    raw = "just prose, [x](#nothing)\n".encode("utf-8")
    assert repair_anchors(raw, raw) == raw


def test_heading_count_mismatch_is_a_noop_not_a_corruption():
    # Pairing is positional, so a differing heading count means the two
    # versions aren't the same document. Bail rather than mis-pair.
    before = "# 一\n# 二\n[x](#一)\n".encode("utf-8")
    after = "# One\n[x](#一)\n".encode("utf-8")
    assert repair_anchors(before, after) == after


def test_ignores_heading_inside_fenced_block():
    # A "#" line inside a fence is a shell comment, not a heading. Counting
    # it would shift the positional pairing and rewrite the wrong anchor.
    before = ("# 架构概览\n\n```bash\n# 注释\n```\n\n[x](#架构概览)\n").encode("utf-8")
    after = ("# Architecture Overview\n\n```bash\n# 注释\n```\n\n"
             "[x](#架构概览)\n").encode("utf-8")
    out = repair_anchors(before, after).decode("utf-8")
    assert "[x](#architecture-overview)" in out
