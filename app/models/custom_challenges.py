from decimal import Decimal

from tortoise import fields, models
from tortoise.indexes import Index
from tortoise.validators import MinValueValidator

from app.models.enums import ChallengeParticipationStatus, CustomChallengeType, MealSlot


class CustomChallengeParticipation(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="custom_challenge_participations",
        on_delete=fields.CASCADE,
    )
    template = fields.ForeignKeyField(
        "models.CustomChallengeTemplate",
        related_name="custom_challenge_participations",
        on_delete=fields.RESTRICT,
    )
    reward_badge = fields.ForeignKeyField(
        "models.Badge",
        related_name="custom_challenge_participations",
        null=True,
        on_delete=fields.RESTRICT,
        description="참여 당시 맞춤 챌린지 보상 배지 ID",
    )
    challenge_type = fields.CharEnumField(CustomChallengeType)
    challenge_name = fields.CharField(max_length=100)
    idempotency_key = fields.CharField(max_length=64)
    joined_at = fields.DatetimeField(auto_now_add=True)
    end_at = fields.DatetimeField()
    status = fields.CharEnumField(
        ChallengeParticipationStatus,
        default=ChallengeParticipationStatus.ACTIVE,
    )
    target_count = fields.IntField(default=0, validators=[MinValueValidator(0)])
    completed_count = fields.IntField(default=0, validators=[MinValueValidator(0)])
    progress_rate = fields.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    completed_at = fields.DatetimeField(null=True)
    finalized_at = fields.DatetimeField(null=True)

    class Meta:
        table = "custom_challenge_participations"
        unique_together = (("user", "idempotency_key"),)
        indexes = (
            Index(
                fields=("user_id", "status", "joined_at"),
                name="idx_custom_participation_user_status",
            ),
            Index(fields=("template_id",), name="idx_custom_participation_template"),
            Index(fields=("reward_badge_id",), name="idx_custom_participation_reward_badge"),
            Index(fields=("end_at",), name="idx_custom_participation_end_at"),
        )


class CustomChallengeTarget(models.Model):
    id = fields.BigIntField(primary_key=True)
    participation = fields.ForeignKeyField(
        "models.CustomChallengeParticipation",
        related_name="custom_challenge_targets",
        on_delete=fields.CASCADE,
    )
    care_episode = fields.ForeignKeyField(
        "models.CareEpisode",
        related_name="custom_challenge_targets",
        null=True,
        on_delete=fields.SET_NULL,
    )
    supplement_registration = fields.ForeignKeyField(
        "models.UserSupplementNutrient",
        related_name="custom_challenge_targets",
        null=True,
        on_delete=fields.SET_NULL,
    )
    follow_up_visit = fields.ForeignKeyField(
        "models.FollowUpVisit",
        related_name="custom_challenge_targets",
        null=True,
        on_delete=fields.SET_NULL,
    )
    source_id_snapshot = fields.BigIntField()
    target_name_snapshot = fields.TextField()

    class Meta:
        table = "custom_challenge_targets"
        unique_together = (("participation", "source_id_snapshot"),)
        indexes = (
            Index(fields=("care_episode_id",), name="idx_custom_target_care_episode"),
            Index(
                fields=("supplement_registration_id",),
                name="idx_custom_target_supplement_registration",
            ),
            Index(fields=("follow_up_visit_id",), name="idx_custom_target_follow_up_visit"),
        )


class CustomChallengeOccurrence(models.Model):
    id = fields.BigIntField(primary_key=True)
    target = fields.ForeignKeyField(
        "models.CustomChallengeTarget",
        related_name="custom_challenge_occurrences",
        on_delete=fields.CASCADE,
    )
    scheduled_date = fields.DateField()
    slot = fields.CharEnumField(MealSlot)
    scheduled_at = fields.DatetimeField()
    is_completed = fields.BooleanField(default=False)

    class Meta:
        table = "custom_challenge_occurrences"
        unique_together = (("target", "scheduled_date", "slot"),)
        indexes = (
            Index(
                fields=("target_id", "scheduled_at"),
                name="idx_custom_occurrence_schedule",
            ),
        )


class CustomChallengeBadgeAward(models.Model):
    id = fields.BigIntField(primary_key=True)
    user = fields.ForeignKeyField(
        "models.User",
        related_name="custom_challenge_badge_awards",
        on_delete=fields.RESTRICT,
    )
    badge = fields.ForeignKeyField(
        "models.Badge",
        related_name="custom_challenge_user_awards",
        on_delete=fields.RESTRICT,
    )
    participation = fields.ForeignKeyField(
        "models.CustomChallengeParticipation",
        related_name="badge_awards",
        on_delete=fields.RESTRICT,
    )
    badge_name = fields.CharField(max_length=100)
    badge_image_path = fields.CharField(max_length=500)
    awarded_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "custom_challenge_badge_awards"
        unique_together = (("participation", "badge"),)
        indexes = (
            Index(fields=("user_id", "awarded_at"), name="idx_custom_badge_award_user_awarded"),
            Index(fields=("badge_id",), name="idx_custom_badge_award_badge"),
        )
