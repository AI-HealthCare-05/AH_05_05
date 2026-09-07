from tortoise import fields, models
from tortoise.indexes import Index
from tortoise.validators import MaxValueValidator, MinValueValidator

from app.models.enums import EmailVerificationPurpose


class EmailVerification(models.Model):
    id = fields.BigIntField(primary_key=True)
    email = fields.CharField(max_length=255)
    purpose = fields.CharEnumField(EmailVerificationPurpose, max_length=30)
    code_digest = fields.CharField(max_length=64)
    expires_at = fields.DatetimeField()
    attempt_count = fields.IntField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    verified_at = fields.DatetimeField(null=True)
    consumed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "email_verifications"
        indexes = (
            Index(fields=("email", "purpose", "created_at"), name="idx_email_verification_lookup"),
            Index(fields=("expires_at",), name="idx_email_verification_expiry"),
            Index(fields=("verified_at", "consumed_at"), name="idx_email_verification_state"),
        )
