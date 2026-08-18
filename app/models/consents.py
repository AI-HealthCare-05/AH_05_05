from tortoise import fields, models

from app.models.enums import ConsentType


class UserConsent(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="consents",
        on_delete=fields.CASCADE,
    )
    consent_type = fields.CharEnumField(ConsentType)
    agreed = fields.BooleanField()
    agreed_at = fields.DatetimeField(auto_now_add=True)
    policy_version = fields.CharField(max_length=50)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "user_consents"
        indexes = (("user", "consent_type", "agreed_at"), ("user", "consent_type"))

