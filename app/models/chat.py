from decimal import Decimal

from tortoise import fields, models
from tortoise.validators import MaxValueValidator, MinValueValidator

from app.models.enums import (
    ChatConflictStatus,
    ChatMessageRole,
    ChatMessageStatus,
    ChatRouteType,
    ChatSafetyStatus,
    ChatSessionStatus,
    ChatSourceType,
    ChatVerificationStatus,
)


class ChatSession(models.Model):
    id = fields.BigIntField(primary_key=True)
    care_episode = fields.ForeignKeyField(
        "models.CareEpisode",
        related_name="chat_sessions",
        on_delete=fields.CASCADE,
    )
    status = fields.CharEnumField(ChatSessionStatus, default=ChatSessionStatus.ACTIVE)
    last_message_at = fields.DatetimeField(null=True)
    deleted_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "chat_sessions"
        indexes = (("care_episode", "status"), ("last_message_at",))


class ChatMessage(models.Model):
    id = fields.BigIntField(primary_key=True)
    chat_session = fields.ForeignKeyField(
        "models.ChatSession",
        related_name="messages",
        on_delete=fields.CASCADE,
    )
    reply_to_message = fields.ForeignKeyField(
        "models.ChatMessage",
        related_name="replies",
        null=True,
        on_delete=fields.SET_NULL,
    )
    guide = fields.ForeignKeyField(
        "models.RecoveryGuide",
        related_name="chat_messages",
        null=True,
        on_delete=fields.SET_NULL,
    )
    request_id = fields.CharField(max_length=100, null=True)
    sequence_no = fields.IntField()
    role = fields.CharEnumField(ChatMessageRole)
    content = fields.TextField()
    status = fields.CharEnumField(ChatMessageStatus, default=ChatMessageStatus.PENDING)
    route_type = fields.CharEnumField(ChatRouteType, null=True)
    safety_status = fields.CharEnumField(ChatSafetyStatus, default=ChatSafetyStatus.PENDING)
    safety_reason_code = fields.CharField(max_length=100, null=True)
    verification_status = fields.CharEnumField(
        ChatVerificationStatus,
        default=ChatVerificationStatus.NOT_REQUIRED,
    )
    conflict_status = fields.CharEnumField(ChatConflictStatus, default=ChatConflictStatus.NOT_APPLICABLE)
    model_name = fields.CharField(max_length=100, null=True)
    model_version = fields.CharField(max_length=100, null=True)
    prompt_version = fields.CharField(max_length=100, null=True)
    schema_version = fields.CharField(max_length=50, null=True)
    patient_context_hash = fields.CharField(max_length=64, null=True)
    langsmith_trace_id = fields.CharField(max_length=100, null=True)
    error_code = fields.CharField(max_length=100, null=True)
    started_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "chat_messages"
        indexes = (
            ("reply_to_message",),
            ("guide",),
            ("request_id",),
            ("langsmith_trace_id",),
            ("created_at",),
        )
        unique_together = (("chat_session", "sequence_no"),)


class ChatMessageSource(models.Model):
    id = fields.BigIntField(primary_key=True)
    chat_message = fields.ForeignKeyField(
        "models.ChatMessage",
        related_name="sources",
        on_delete=fields.CASCADE,
    )
    source_type = fields.CharEnumField(ChatSourceType)
    extracted_field = fields.ForeignKeyField(
        "models.OcrExtractedField",
        related_name="chat_message_sources",
        null=True,
        on_delete=fields.SET_NULL,
    )
    public_dataset_key = fields.CharField(max_length=100, null=True)
    dataset_version = fields.CharField(max_length=100, null=True)
    vector_chunk_id = fields.CharField(max_length=255, null=True)
    source_record_key = fields.CharField(max_length=100, null=True)
    source_field = fields.CharField(max_length=100, null=True)
    chunk_type = fields.CharField(max_length=100, null=True)
    source_title = fields.CharField(max_length=255, null=True)
    source_organization = fields.CharField(max_length=255, null=True)
    source_url = fields.TextField(null=True)
    similarity_score = fields.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("1"))],
    )
    citation_order = fields.IntField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "chat_message_sources"
        indexes = (
            ("chat_message",),
            ("extracted_field",),
            ("public_dataset_key", "source_record_key"),
            ("vector_chunk_id",),
        )
        unique_together = (("chat_message", "citation_order"),)

