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
            "app.models.medications",
            "app.models.interactions",
            "app.models.supplement_nutrients",
        ),
        "models",
    )
    return recovery, chat


def load_alarm_job_models():
    try:
        alarms = import_module("app.models.alarms")
        background_jobs = import_module("app.models.background_jobs")
    except ModuleNotFoundError as exc:
        pytest.fail(f"alarm/background-job model module is missing: {exc.name}")

    Tortoise.init_models(
        (
            "app.models.users",
            "app.models.admins",
            "app.models.care",
            "app.models.ocr",
            "app.models.recovery",
            "app.models.chat",
            "app.models.medications",
            "app.models.alarms",
            "app.models.background_jobs",
        ),
        "models",
    )
    return alarms, background_jobs


def load_medication_models():
    try:
        medications = import_module("app.models.medications")
    except ModuleNotFoundError as exc:
        pytest.fail(f"medication model module is missing: {exc.name}")
    return medications


def test_user_matches_merged_account_schema() -> None:
    enums, user_model, _ = load_account_models()

    assert user_model._meta.db_table == "user"
    assert user_model._meta.db_fields == {
        "id",
        "email",
        "hashed_password",
        "status",
        "name",
        "phone",
        "birth_date",
        "gender",
        "created_at",
        "updated_at",
    }
    assert user_model._meta.fields_map["email"].unique is True
    assert user_model._meta.fields_map["status"].default == enums.AccountStatus.PENDING
    assert user_model._meta.fields_map["birth_date"].null is True
    assert user_model._meta.fields_map["gender"].null is True
    assert user_model._meta.fields_map["gender"].enum_type is enums.Gender


def test_user_settings_are_one_to_one_and_have_default_times() -> None:
    enums, _, _ = load_account_models()
    users = import_module("app.models.users")

    assert users.UserSettings._meta.db_table == "user_settings"
    assert users.UserSettings._meta.fields_map["user"].unique is True
    assert users.UserSettings._meta.fields_map["is_notify_medication"].default is True
    assert users.UserSettings._meta.fields_map["is_notify_schedule"].default is True
    assert users.UserSettings._meta.fields_map["is_notify_guide"].default is True
    assert users.UserSettings._meta.fields_map["is_terms_agreed"].default is False
    assert users.UserSettings._meta.fields_map["morning_medication_time"].default.hour == 8
    assert enums.MealSlot.BEDTIME.value == "BEDTIME"


def test_user_notification_v4_metadata() -> None:
    enums = import_module("app.models.enums")
    users = import_module("app.models.users")

    assert {item.value for item in enums.NotifySettingKey} == {
        "IS_NOTIFY_MEDICATION",
        "IS_NOTIFY_SCHEDULE",
        "IS_NOTIFY_GUIDE",
    }
    assert users.UserSettings._meta.fields_map["terms_agreed_at"].null is True
    assert users.UserSettings._meta.fields_map["notify_consented_at"].null is True
    history = users.UserNotifyHistory
    assert history._meta.db_table == "user_notify_histories"
    assert history._meta.fields_map["user"].on_delete == fields.CASCADE
    assert history._meta.fields_map["user"].null is False
    assert history._meta.fields_map["setting_key"].enum_type is enums.NotifySettingKey
    assert history._meta.fields_map["new_value"].null is False
    assert history._meta.fields_map["created_at"].auto_now_add is True
    assert history._meta.indexes == (("user", "setting_key", "created_at"), ("created_at",))


def test_admin_has_nullable_creator_self_reference() -> None:
    enums, _, admin_model = load_account_models()

    assert admin_model._meta.db_table == "admin"
    assert admin_model._meta.fields_map["role"].default == enums.AdminRole.STAFF
    creator = admin_model._meta.fields_map["created_by_admin"]
    assert creator.null is True
    assert creator.model_name == "models.Admin"


def test_care_models_preserve_ownership_and_confirmation_fields() -> None:
    care, _ = load_care_ocr_models()

    assert care.CareEpisode._meta.db_table == "care_episodes"
    assert care.CareEpisode._meta.fields_map["user"].model_name == "models.User"
    assert {
        "diagnosis",
        "surgery",
        "discharge_date",
        "medication_days",
        "source_ocr_job_id",
        "confirmation_hash",
        "confirmed_at",
        "medication_start_date",
        "medication_start_slot",
    } <= care.CareEpisode._meta.db_fields
    assert care.CareAdvice._meta.unique_together == (("care_episode", "display_order"),)
    assert "source_extracted_field" not in care.CareAdvice._meta.fields_map
    assert "source_extracted_field" not in care.FollowUpVisit._meta.fields_map


def test_care_v4_metadata() -> None:
    care, _ = load_care_ocr_models()
    enums = import_module("app.models.enums")

    assert {item.value for item in enums.CareAdviceCategory} == {
        "ACTIVITY",
        "HYGIENE",
        "DIET",
        "LIFESTYLE",
        "RESTRICTION",
        "RED_FLAG",
        "OTHER",
    }
    assert care.CareAdvice._meta.fields_map["category"].null is False
    assert care.CareAdvice._meta.fields_map["category"].enum_type is enums.CareAdviceCategory
    assert ("care_episode", "category") in care.CareAdvice._meta.indexes
    assert care.FollowUpVisit._meta.fields_map["visit_date"].null is False
    assert care.FollowUpVisit._meta.fields_map["visit_time"].null is True
    assert "source_ocr_job" not in care.FollowUpVisit._meta.fields_map
    assert "source_ocr_job_id" not in care.FollowUpVisit._meta.db_fields
    assert care.FollowUpVisit._meta.fields_map["user"].model_name == "models.User"
    assert care.FollowUpVisit._meta.fields_map["user"].on_delete == fields.CASCADE
    assert care.FollowUpVisit._meta.fields_map["user"].null is False
    assert care.FollowUpVisit._meta.fields_map["hospital"].max_length == 255
    assert care.FollowUpVisit._meta.fields_map["hospital"].null is True
    assert "department" not in care.FollowUpVisit._meta.fields_map
    assert {"care_episode", "care_episode_id", "doctor_name", "place", "purpose"}.isdisjoint(
        care.FollowUpVisit._meta.fields_map
    )
    assert ("user",) in care.FollowUpVisit._meta.indexes
    assert ("visit_date", "visit_time", "id") in care.FollowUpVisit._meta.indexes
    assert "visit_at" not in care.FollowUpVisit._meta.fields_map


def test_ocr_job_uses_temporary_structured_result_contract() -> None:
    _, ocr = load_care_ocr_models()

    assert ocr.OcrJob._meta.db_table == "ocr_jobs"
    assert ocr.OcrJob._meta.fields_map["user"].model_name == "models.User"
    assert ocr.OcrJob._meta.fields_map["user"].null is False
    assert ocr.OcrJob._meta.fields_map["care_episode"].model_name == "models.CareEpisode"
    assert ocr.OcrJob._meta.fields_map["care_episode"].null is True
    assert ocr.OcrJob._meta.fields_map["care_episode"].on_delete == fields.SET_NULL
    assert ocr.OcrJob._meta.unique_together == (
        ("user", "idempotency_key"),
        ("id", "care_episode"),
    )
    assert ocr.OcrJob._meta.fields_map["input_manifest"].null is False
    assert ocr.OcrJob._meta.fields_map["structured_result"].null is True
    assert {"ocr_model", "structuring_model", "ready_at", "expires_at"} <= ocr.OcrJob._meta.db_fields
    assert not hasattr(ocr, "OcrExtractedField")


def test_recovery_models_preserve_citations_and_patient_sources() -> None:
    recovery, _ = load_recovery_chat_models()

    guide_fields = recovery.RecoveryGuide._meta.fields_map
    assert guide_fields["care_episode"].model_name == "models.CareEpisode"
    for field_name in (
        "guide_content",
        "model_name",
        "prompt_version",
        "schema_version",
        "safety_reason_codes",
        "completed_at",
    ):
        assert guide_fields[field_name].null is False
    assert "safety_reason_code" not in guide_fields

    assert recovery.RecoveryGuideSource._meta.unique_together == (("recovery_guide", "citation_order"),)
    assert "extracted_field" not in recovery.RecoveryGuideSource._meta.fields_map
    assert recovery.RecoveryGuideSource._meta.fields_map["medication"].on_delete == fields.RESTRICT
    assert recovery.RecoveryGuideSource._meta.fields_map["care_advice"].null is True
    assert recovery.RecoveryGuideSource._meta.fields_map["follow_up_visit"].null is True
    assert recovery.RecoveryGuideSource._meta.fields_map["source_page_number"].null is True
    assert len(recovery.RecoveryGuideSource._meta.fields_map["source_page_number"].validators) == 1
    assert recovery.RecoveryGuideSource._meta.fields_map["source_license"].max_length == 255


def test_chat_models_preserve_sequence_reply_and_source_constraints() -> None:
    _, chat = load_recovery_chat_models()

    assert chat.ChatMessage._meta.unique_together == (("chat_session", "sequence_no"),)
    assert chat.ChatMessage._meta.fields_map["reply_to_message"].model_name == "models.ChatMessage"
    assert chat.ChatMessage._meta.fields_map["guide"].on_delete == fields.SET_NULL
    assert chat.ChatMessageSource._meta.unique_together == (("chat_message", "citation_order"),)
    assert "extracted_field" not in chat.ChatMessageSource._meta.fields_map
    assert chat.ChatMessageSource._meta.fields_map["medication"].on_delete == fields.RESTRICT
    assert chat.ChatMessageSource._meta.fields_map["care_advice"].null is True
    assert chat.ChatMessageSource._meta.fields_map["source_page_number"].null is True
    assert len(chat.ChatMessageSource._meta.fields_map["source_page_number"].validators) == 1
    assert chat.ChatMessageSource._meta.fields_map["source_license"].max_length == 255


def test_chat_and_source_retention_v4_metadata() -> None:
    recovery, chat = load_recovery_chat_models()

    score = chat.ChatSession._meta.fields_map["score"]
    assert isinstance(score, fields.IntField)
    assert score.null is True
    assert score.description == "채팅 별점"
    assert {validator.__class__.__name__ for validator in score.validators} == {
        "MinValueValidator",
        "MaxValueValidator",
    }
    assert score.validators[0].min_value == 1
    assert score.validators[1].max_value == 5
    assert chat.ChatSession._meta.fields_map["user"].null is False
    assert chat.ChatSession._meta.fields_map["user"].model_name == "models.User"
    assert chat.ChatSession._meta.fields_map["user"].on_delete == fields.CASCADE
    assert chat.ChatSession._meta.fields_map["care_episode"].null is True
    assert chat.ChatSession._meta.fields_map["care_episode"].model_name == "models.CareEpisode"
    assert chat.ChatSession._meta.fields_map["care_episode"].on_delete == fields.CASCADE
    for model in (chat.ChatMessageSource, recovery.RecoveryGuideSource):
        for name in ("medication", "care_advice", "follow_up_visit"):
            assert model._meta.fields_map[name].on_delete == fields.RESTRICT


def test_alarm_models_preserve_subscription_and_optional_source_relations() -> None:
    alarms, _ = load_alarm_job_models()

    assert alarms.PushSubscription._meta.fields_map["endpoint"].unique is True
    assert alarms.Alarm._meta.fields_map["user"].model_name == "models.User"
    assert alarms.Alarm._meta.fields_map["source_guide"].on_delete == fields.SET_NULL
    follow_up_visit = alarms.Alarm._meta.fields_map["follow_up_visit"]
    assert follow_up_visit.model_name == "models.FollowUpVisit"
    assert follow_up_visit.null is True
    assert follow_up_visit.on_delete == fields.CASCADE
    assert alarms.Alarm._meta.fields_map["meal_slot"].null is True
    assert alarms.Alarm._meta.unique_together == (("user", "alarm_type", "meal_slot"),)
    push_subscription = alarms.AlarmEvent._meta.fields_map["push_subscription"]
    assert push_subscription.null is True
    assert push_subscription.on_delete == fields.SET_NULL


def test_background_job_keeps_polymorphic_reference_and_self_parent() -> None:
    _, background_jobs = load_alarm_job_models()

    model = background_jobs.BackgroundJob
    assert {"reference_table", "reference_id"} <= model._meta.db_fields
    assert model._meta.fields_map["parent_job"].model_name == "models.BackgroundJob"
    assert model._meta.fields_map["parent_job"].on_delete == fields.SET_NULL
    assert model._meta.fields_map["idempotency_key"].unique is True
    assert len(model._meta.fields_map["retry_count"].validators) == 1


def test_medication_slot_model_replaces_legacy_time_model() -> None:
    medications = load_medication_models()

    assert medications.Medication._meta.fields_map["source_ocr_job"].on_delete == fields.SET_NULL
    assert "source_extracted_field" not in medications.Medication._meta.fields_map
    assert not hasattr(medications, "MedicationTime")
    assert medications.MedicationSlot._meta.db_table == "medication_slots"
    assert medications.MedicationSlot._meta.unique_together == (("medication", "slot"),)


def test_medication_v4_metadata() -> None:
    medications = load_medication_models()

    medication_fields = medications.Medication._meta.fields_map
    for name in ("efficacy", "administration", "precautions"):
        assert medication_fields[name].null is True
        assert medication_fields[name].max_length == 500
    assert medication_fields["note"].null is True
    assert medication_fields["note"].max_length == 500
    assert any(getattr(validator, "min_value", None) == 1 for validator in medication_fields["days"].validators)
    assert any(getattr(validator, "max_value", None) == 365 for validator in medication_fields["days"].validators)


def test_all_19_domain_tables_are_registered() -> None:
    from app.core.db.databases import TORTOISE_APP_MODELS

    expected_tables = {
        "user",
        "user_settings",
        "user_notify_histories",
        "admin",
        "care_episodes",
        "ocr_jobs",
        "recovery_guides",
        "recovery_guide_sources",
        "chat_sessions",
        "chat_messages",
        "chat_message_sources",
        "push_subscriptions",
        "alarms",
        "alarm_events",
        "background_jobs",
        "medications",
        "medication_slots",
        "care_advices",
        "follow_up_visits",
    }

    Tortoise.init_models(TORTOISE_APP_MODELS, "models")
    registered_tables = {model._meta.db_table for model in Tortoise.apps["models"].values()}

    assert expected_tables <= registered_tables
    assert "accounts" not in registered_tables
    assert "users" not in registered_tables
    assert "ocr_extracted_fields" not in registered_tables
    assert "medication_times" not in registered_tables
    assert "user_consents" not in registered_tables
