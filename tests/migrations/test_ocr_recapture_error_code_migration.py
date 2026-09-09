from importlib import import_module

from aerich.utils import compress_dict, decompress_dict, get_models_describe
from tortoise import Tortoise

from app.core.db.databases import TORTOISE_APP_MODELS

MIGRATION = import_module("app.core.db.migrations.models.40_20260909143654_allow_ocr_recapture_error_code")


def test_migration_snapshot_matches_current_models() -> None:
    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    expected = decompress_dict(compress_dict(get_models_describe("models")))

    assert decompress_dict(MIGRATION.MODELS_STATE) == expected


async def test_upgrade_replaces_ocr_error_code_check_with_recapture_allowed() -> None:
    sql = await MIGRATION.upgrade(None)

    drop = sql.index("DROP CHECK `chk_ocr_error_code`")
    add = sql.index("ADD CONSTRAINT `chk_ocr_error_code`")
    check = sql[add : sql.index(";", add)]

    assert drop < add
    assert "'RECAPTURE_REQUIRED'" in check
    assert "'OCR_PROVIDER_ERROR'" in check
    assert "'OCR_PROVIDER_TIMEOUT'" in check
    assert "'EXTRACTION_FAILED'" in check
    assert "'VALIDATION_FAILED'" in check
    assert "'WORKER_INTERRUPTED'" in check
    assert "'USER_CANCELLED'" in check
    assert "'REVIEW_EXPIRED'" in check
    assert "`status` IN ('QUEUED', 'PROCESSING', 'READY_FOR_REVIEW', 'COMPLETE')" in check


async def test_downgrade_restores_the_previous_ocr_error_code_check() -> None:
    sql = await MIGRATION.downgrade(None)

    drop = sql.index("DROP CHECK `chk_ocr_error_code`")
    add = sql.index("ADD CONSTRAINT `chk_ocr_error_code`")
    check = sql[add : sql.index(";", add)]

    assert drop < add
    assert "'RECAPTURE_REQUIRED'" not in check
    assert "'OCR_PROVIDER_ERROR'" in check
    assert "'USER_CANCELLED'" in check
