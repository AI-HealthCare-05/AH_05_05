from importlib import import_module

import pytest
from tortoise import Tortoise, fields


def load_account_models():
    try:
        enums = import_module("app.models.enums")
        users = import_module("app.models.users")
        admins = import_module("app.models.admins")
    except ModuleNotFoundError as exc:
        pytest.fail(f"account model module is missing: {exc.name}")
    return enums, users.User, admins.Admin


def load_care_ocr_models():
    try:
        care = import_module("app.models.care")
        ocr = import_module("app.models.ocr")
    except ModuleNotFoundError as exc:
        pytest.fail(f"care/OCR model module is missing: {exc.name}")

    Tortoise.init_models(
        (
            "app.models.users",
            "app.models.admins",
            "app.models.care",
            "app.models.ocr",
        ),
        "models",
    )
    return care, ocr


def load_recovery_chat_models():
    try:
        recovery = import_module("app.models.recovery")
        chat = import_module("app.models.chat")
    except ModuleNotFoundError as exc:
        pytest.fail(f"recovery/chat model module is missing: {exc.name}")

    Tortoise.init_models(
        (
            "app.models.users",
            "app.models.admins",
            "app.models.care",
            "app.models.ocr",
            "app.models.recovery",
            "app.models.chat",
        ),
        "models",
    )
    return recovery, chat


def test_user_matches_merged_account_schema() -> None:
    enums, user_model, _ = load_account_models()

    assert user_model._meta.db_table == "user"
    assert user_model._meta.fields == {
        "id",
        "email",
        "hashed_password",
        "status",
        "name",
        "phone",
        "is_alarm",
        "created_at",
        "updated_at",
    }
    assert user_model._meta.fields_map["email"].unique is True
    assert user_model._meta.fields_map["status"].default == enums.AccountStatus.PENDING


def test_admin_has_nullable_creator_self_reference() -> None:
    enums, _, admin_model = load_account_models()

    assert admin_model._meta.db_table == "admin"
    assert admin_model._meta.fields_map["role"].default == enums.AdminRole.STAFF
    creator = admin_model._meta.fields_map["created_by_admin"]
    assert creator.null is True
    assert creator.model_name == "models.Admin"


def test_care_models_preserve_ownership_and_source_deletion_policies() -> None:
    care, _ = load_care_ocr_models()

    assert care.CareEpisode._meta.db_table == "care_episodes"
    assert care.CareEpisode._meta.fields_map["user"].model_name == "models.User"
    assert care.CareAdvice._meta.unique_together == (("care_episode", "display_order"),)
    assert care.CareAdvice._meta.fields_map["source_extracted_field"].on_delete == fields.SET_NULL
    assert care.FollowUpVisit._meta.fields_map["source_extracted_field"].on_delete == fields.SET_NULL


def test_ocr_models_preserve_job_and_extracted_field_constraints() -> None:
    _, ocr = load_care_ocr_models()

    assert ocr.OcrJob._meta.db_table == "ocr_jobs"
    assert ocr.OcrJob._meta.fields_map["care_episode"].model_name == "models.CareEpisode"
    assert ocr.OcrJob._meta.fields_map["idempotency_key"].unique is True
    assert ocr.OcrExtractedField._meta.unique_together == (
        ("ocr_job", "entity_key", "field_type"),
    )
    assert len(ocr.OcrExtractedField._meta.fields_map["confidence"].validators) == 2


def test_recovery_models_preserve_citations_and_patient_sources() -> None:
    recovery, _ = load_recovery_chat_models()

    assert recovery.RecoveryGuide._meta.fields_map["care_episode"].model_name == "models.CareEpisode"
    assert recovery.RecoveryGuideSource._meta.unique_together == (("recovery_guide", "citation_order"),)
    extracted_field = recovery.RecoveryGuideSource._meta.fields_map["extracted_field"]
    assert extracted_field.null is True
    assert extracted_field.on_delete == fields.SET_NULL


def test_chat_models_preserve_sequence_reply_and_source_constraints() -> None:
    _, chat = load_recovery_chat_models()

    assert chat.ChatMessage._meta.unique_together == (("chat_session", "sequence_no"),)
    assert chat.ChatMessage._meta.fields_map["reply_to_message"].model_name == "models.ChatMessage"
    assert chat.ChatMessage._meta.fields_map["guide"].on_delete == fields.SET_NULL
    assert chat.ChatMessageSource._meta.unique_together == (("chat_message", "citation_order"),)
    assert chat.ChatMessageSource._meta.fields_map["extracted_field"].on_delete == fields.SET_NULL
