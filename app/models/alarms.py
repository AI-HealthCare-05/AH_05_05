from tortoise import fields, models
from tortoise.indexes import Index

from app.models.enums import AlarmEventType, AlarmStatus, AlarmType, MealSlot


class PushSubscription(models.Model):
    id = fields.BigIntField(primary_key=True)
    user: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.User",
        related_name="push_subscriptions",
        on_delete=fields.CASCADE,
    )
    endpoint = fields.CharField(max_length=500, unique=True)
    p256dh_key = fields.CharField(max_length=255)
    auth_key = fields.CharField(max_length=255)
    platform = fields.CharField(max_length=50, null=True)
    user_agent = fields.CharField(max_length=255, null=True)
    is_active = fields.BooleanField(default=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    last_used_at = fields.DatetimeField(null=True)

    class Meta:
        table = "push_subscriptions"
        indexes = (("user", "is_active"),)


class Alarm(models.Model):
    id = fields.BigIntField(primary_key=True)
    user: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.User", related_name="alarms", on_delete=fields.CASCADE
    )
    care_episode: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.CareEpisode",
        related_name="alarms",
        null=True,
        on_delete=fields.CASCADE,
    )
    source_guide: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.RecoveryGuide",
        related_name="alarms",
        null=True,
        on_delete=fields.SET_NULL,
    )
    follow_up_visit: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.FollowUpVisit",
        related_name="alarms",
        null=True,
        on_delete=fields.CASCADE,
    )
    alarm_type = fields.CharEnumField(AlarmType, default=AlarmType.MEDICATION)
    meal_slot = fields.CharEnumField(MealSlot, null=True)
    title = fields.CharField(max_length=255)
    message = fields.CharField(max_length=500, null=True)
    scheduled_at = fields.DatetimeField()
    recurrence_rule = fields.CharField(max_length=100, null=True)
    timezone = fields.CharField(max_length=50, default="Asia/Seoul")
    next_trigger_at = fields.DatetimeField()
    status = fields.CharEnumField(AlarmStatus, default=AlarmStatus.ACTIVE)
    last_triggered_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    cancelled_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(null=True)

    class Meta:
        table = "alarms"
        unique_together = (("user", "alarm_type", "meal_slot"),)
        indexes = (
            ("user", "status"),
            Index(fields=("status", "next_trigger_at"), name="idx_due_alarms"),
            ("care_episode",),
            ("follow_up_visit",),
        )


class AlarmEvent(models.Model):
    id = fields.BigIntField(primary_key=True)
    alarm: fields.ForeignKeyRelation[models.Model] = fields.ForeignKeyField(
        "models.Alarm",
        related_name="events",
        on_delete=fields.CASCADE,
    )
    event_type = fields.CharEnumField(AlarmEventType)
    push_subscription: fields.ForeignKeyNullableRelation[models.Model] = fields.ForeignKeyField(
        "models.PushSubscription",
        related_name="alarm_events",
        null=True,
        on_delete=fields.SET_NULL,
    )
    event_at = fields.DatetimeField(auto_now_add=True)
    payload: fields.JSONField[dict[str, object] | list[object]] = fields.JSONField(null=True)
    error_code = fields.CharField(max_length=100, null=True)
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "alarm_events"
        indexes = (("alarm", "event_type"), ("event_at",))
