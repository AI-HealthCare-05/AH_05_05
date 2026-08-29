from tortoise import Tortoise, fields

from app.models.admin_settings import AdminSetting


def test_admin_settings_model_matches_smtp_schema() -> None:
    Tortoise.init_models(("app.models.admins", "app.models.admin_settings"), "models")
    assert AdminSetting._meta.db_table == "admin_settings"
    assert AdminSetting._meta.db_fields == {
        "id",
        "setting_key",
        "smtp_host",
        "smtp_port",
        "smtp_user",
        "smtp_password_enc",
        "smtp_from_email",
        "created_at",
        "updated_at",
        "updated_by_admin_id",
    }
    assert AdminSetting._meta.fields_map["setting_key"].unique is True
    assert AdminSetting._meta.fields_map["smtp_password_enc"].max_length == 500
    updater = AdminSetting._meta.fields_map["updated_by_admin"]
    assert updater.model_name == "models.Admin"
    assert updater.source_field == "updated_by_admin_id"
    assert updater.on_delete == fields.RESTRICT
    assert updater.null is False
