from importlib import import_module

import pytest


def load_account_models():
    try:
        enums = import_module("app.models.enums")
        users = import_module("app.models.users")
        admins = import_module("app.models.admins")
    except ModuleNotFoundError as exc:
        pytest.fail(f"account model module is missing: {exc.name}")
    return enums, users.User, admins.Admin


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

