import importlib

import app.models as models
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.chat import ChatSession


def test_common_code_models_expose_category_and_lookup_indexes() -> None:
    assert hasattr(models, "CommonCodeGroup"), "CommonCodeGroup 모델이 등록되어야 합니다."
    assert hasattr(models, "CommonCode"), "CommonCode 모델이 등록되어야 합니다."

    group_model = models.CommonCodeGroup
    code_model = models.CommonCode

    assert group_model._meta.db_table == "common_code_groups"
    assert group_model._meta.fields_map["category"].max_length == 50
    assert group_model._meta.fields_map["group_code"].unique is True
    assert ("category", "is_active", "group_code") in group_model._meta.indexes

    assert code_model._meta.db_table == "common_codes"
    assert (("group", "detail_code"),) == code_model._meta.unique_together
    assert ("group", "is_active", "sort_order") in code_model._meta.indexes


def test_common_code_models_are_registered_with_tortoise() -> None:
    assert "app.models.common_codes" in TORTOISE_APP_MODELS


def test_chat_session_uses_nullable_like_feedback_instead_of_score() -> None:
    fields = ChatSession._meta.fields_map

    assert "score" not in fields
    assert fields["is_like"].null is True
    assert fields["reason_code"].null is True
    assert fields["reason_code"].max_length == 20


async def test_migration_discards_legacy_chat_score() -> None:
    migration = importlib.import_module(
        "app.core.db.migrations.models.23_20260903212549_add_common_codes_chat_feedback"
    )

    upgrade_sql = await migration.upgrade(None)
    downgrade_sql = await migration.downgrade(None)

    assert "DROP CHECK `chk_chat_session_score`" in upgrade_sql
    assert "DROP COLUMN `score`" in upgrade_sql
    assert "ADD `score` INT" in downgrade_sql
