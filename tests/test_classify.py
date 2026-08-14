import pytest
from gwt.classify import is_translatable, LANG_BY_SUFFIX


@pytest.mark.parametrize("path", [
    "go-wind-cms/backend/app/core/service/internal/data/user.go",
    "go-wind-cms/backend/api/admin/service/v1/user.proto",
    "go-wind-admin/frontend/admin/react/src/views/login.tsx",
    "go-wind-uba/docs/architecture.md",
    "go-wind-cms/backend/app/core/service/internal/data/ent/schema/user.go",
])
def test_translatable_sources(path):
    assert is_translatable(path) is True


@pytest.mark.parametrize("path", [
    # deliberate Chinese: runtime i18n
    "go-wind-admin/frontend/admin/react/src/locales/zh-CN/_modules/menu.json",
    "go-wind-cms/frontend/app/react/messages/zh-CN/common.json",
    "go-wind-uba/frontend/admin/packages/locales/src/langs/zh-CN/common.json",
    "go-wind-ledger/frontend/app/flutter_app/lib/l10n/app_zh.arb",
    "go-wind-cms/frontend/app/react/src/app/[locale]/login/page.tsx",
    "go-wind-cms/README.ja-JP.md",
    "go-wind-shop/README.zh-CN.md",
    # pre-move underscore variants (docs_layout hasn't renamed these yet
    # when extraction runs first in cmd_run's pipeline)
    "go-wind-bootstrap/README_ja.md",
    "go-wind-bootstrap/README_en.md",
    # generated: regenerate, do not translate
    "go-wind-cms/backend/api/gen/go/admin/service/v1/user.pb.go",
    "go-wind-admin/frontend/admin/react/src/api/generated/admin/service/v1/index.ts",
    "go-wind-cms/backend/app/core/service/internal/data/ent/user.go",
    "go-wind-admin/backend/app/admin/service/internal/data/ent/migrate/schema.go",
    # not a source file
    "go-wind-cms/node_modules/foo/index.js",
    "go-wind-cms/.git/config",
])
def test_excluded(path):
    assert is_translatable(path) is False


def test_ent_schema_beats_ent_exclusion():
    # ent/schema/ is hand-written source; ent/ elsewhere is generated
    assert is_translatable("x/backend/internal/data/ent/schema/post.go") is True
    assert is_translatable("x/backend/internal/data/ent/post.go") is False


def test_lang_lookup():
    assert LANG_BY_SUFFIX[".go"] == "go"
    assert LANG_BY_SUFFIX[".vue"] == "vue"
    assert LANG_BY_SUFFIX[".md"] == "markdown"
