import app.models as models
from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.email_verifications import EmailVerification
from app.models.enums import EmailVerificationPurpose


def test_email_verification_model_contract() -> None:
    fields = EmailVerification._meta.fields_map

    assert EmailVerification._meta.db_table == "email_verifications"
    assert fields["email"].max_length == 255
    assert fields["purpose"].enum_type is EmailVerificationPurpose
    assert fields["code_digest"].max_length == 64
    assert fields["attempt_count"].default == 0
    assert {index.name for index in EmailVerification._meta.indexes} == {
        "idx_email_verification_lookup",
        "idx_email_verification_expiry",
        "idx_email_verification_state",
    }


def test_email_verification_model_is_registered_with_tortoise() -> None:
    assert hasattr(models, "EmailVerification")
    assert "app.models.email_verifications" in TORTOISE_APP_MODELS
