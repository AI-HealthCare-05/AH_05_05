from decimal import Decimal

from tortoise import fields, models
from tortoise.indexes import Index
from tortoise.validators import MinValueValidator

from app.models.enums import (
    BadgeAwardStatus,
    ChallengeParticipationStatus,
    ChallengeVerificationStatus,
)


class Badge(models.Model):
    id = fields.BigIntField(primary_key=True, description="배지 ID")
    name = fields.CharField(max_length=100, unique=True, description="배지 이름")
    description = fields.CharField(max_length=500, null=True, description="배지 설명")
    image_path = fields.CharField(max_length=500, description="배지 이미지 상대 경로")
    is_active = fields.BooleanField(default=True, description="배지 사용 여부")
    created_by_admin = fields.ForeignKeyField(
        "models.Admin",
        related_name="created_badges",
        null=True,
        on_delete=fields.SET_NULL,
        description="등록 관리자 ID",
    )
    updated_by_admin = fields.ForeignKeyField(
        "models.Admin",
        related_name="updated_badges",
        null=True,
        on_delete=fields.SET_NULL,
        description="최종 수정 관리자 ID",
    )
    created_at = fields.DatetimeField(auto_now_add=True, description="등록 일시")
    updated_at = fields.DatetimeField(auto_now=True, null=True, description="최종 수정 일시")

    class Meta:
        table = "badges"
        indexes = (
            Index(fields=("is_active",), name="idx_badges_active"),
            Index(fields=("created_by_admin_id",), name="idx_badges_created_admin"),
            Index(fields=("updated_by_admin_id",), name="idx_badges_updated_admin"),
        )


class Challenge(models.Model):
    id = fields.BigIntField(primary_key=True, description="챌린지 ID")
    name = fields.CharField(max_length=100, description="챌린지명")
    challenge_type = fields.ForeignKeyField(
        "models.CommonCode",
        related_name="typed_challenges",
        on_delete=fields.RESTRICT,
        description="챌린지 유형 공통코드 ID(CHL/CHL_TYPE)",
    )
    phrase = fields.CharField(max_length=255, description="챌린지 화면에 표시할 짧은 문구")
    description = fields.TextField(null=True, description="챌린지 상세 설명")
    recruit_start_at = fields.DatetimeField(description="모집 시작 일시")
    recruit_end_at = fields.DatetimeField(description="모집 종료 일시")
    challenge_period = fields.ForeignKeyField(
        "models.CommonCode",
        related_name="period_challenges",
        on_delete=fields.RESTRICT,
        description="챌린지 기간 공통코드 ID(CHL/CHL_PERIOD)",
    )
    check_type = fields.ForeignKeyField(
        "models.CommonCode",
        related_name="check_type_challenges",
        on_delete=fields.RESTRICT,
        description="인증 방식 공통코드 ID(CHL/CHK_TYPE)",
    )
    check_frequency = fields.ForeignKeyField(
        "models.CommonCode",
        related_name="check_frequency_challenges",
        on_delete=fields.RESTRICT,
        description="인증 빈도 공통코드 ID(CHL/CHK_FREQ)",
    )
    reward_badge = fields.ForeignKeyField(
        "models.Badge",
        related_name="reward_challenges",
        null=True,
        on_delete=fields.RESTRICT,
        description="챌린지 완료 시 지급할 배지 ID",
    )
    is_displayed = fields.BooleanField(default=False, description="사용자 화면 전시 여부")
    is_deleted = fields.BooleanField(default=False, description="소프트 삭제 여부")
    deleted_at = fields.DatetimeField(null=True, description="삭제 처리 일시")
    created_by_admin = fields.ForeignKeyField(
        "models.Admin",
        related_name="created_challenges",
        null=True,
        on_delete=fields.SET_NULL,
        description="등록 관리자 ID",
    )
    updated_by_admin = fields.ForeignKeyField(
        "models.Admin",
        related_name="updated_challenges",
        null=True,
        on_delete=fields.SET_NULL,
        description="최종 수정 관리자 ID",
    )
    created_at = fields.DatetimeField(auto_now_add=True, description="등록 일시")
    updated_at = fields.DatetimeField(auto_now=True, null=True, description="최종 수정 일시")

    class Meta:
        table = "challenges"
        indexes = (
            Index(
                fields=("is_displayed", "is_deleted", "recruit_start_at", "recruit_end_at"),
                name="idx_challenges_display_period",
            ),
            Index(fields=("challenge_type_id", "is_deleted"), name="idx_challenges_type"),
            Index(fields=("challenge_period_id",), name="idx_challenges_period"),
            Index(fields=("check_type_id",), name="idx_challenges_check_type"),
            Index(fields=("check_frequency_id",), name="idx_challenges_check_frequency"),
            Index(fields=("reward_badge_id",), name="idx_challenges_reward_badge"),
            Index(fields=("created_by_admin_id",), name="idx_challenges_created_admin"),
            Index(fields=("updated_by_admin_id",), name="idx_challenges_updated_admin"),
        )


class UserChallenge(models.Model):
    id = fields.BigIntField(primary_key=True, description="사용자 챌린지 참여 ID")
    user = fields.ForeignKeyField(
        "models.User",
        related_name="challenge_participations",
        on_delete=fields.RESTRICT,
        description="참여 사용자 ID",
    )
    challenge = fields.ForeignKeyField(
        "models.Challenge",
        related_name="participations",
        on_delete=fields.RESTRICT,
        description="공식 챌린지 ID",
    )
    status = fields.CharEnumField(
        ChallengeParticipationStatus,
        default=ChallengeParticipationStatus.ACTIVE,
        description="참여 상태",
    )
    joined_at = fields.DatetimeField(auto_now_add=True, description="참여 신청 일시")
    started_at = fields.DatetimeField(description="실제 챌린지 시작 일시")
    end_at = fields.DatetimeField(description="사용자별 챌린지 종료 예정 일시")
    target_count = fields.IntField(default=0, validators=[MinValueValidator(0)])
    completed_count = fields.IntField(default=0, validators=[MinValueValidator(0)])
    progress_rate = fields.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    completed_at = fields.DatetimeField(null=True, description="챌린지 완료 일시")
    cancelled_at = fields.DatetimeField(null=True, description="참여 취소 일시")
    created_at = fields.DatetimeField(auto_now_add=True, description="등록 일시")
    updated_at = fields.DatetimeField(auto_now=True, null=True, description="최종 수정 일시")

    class Meta:
        table = "user_challenges"
        unique_together = (("user", "challenge"),)
        indexes = (
            Index(fields=("user_id", "status", "joined_at"), name="idx_user_challenges_user_status"),
            Index(fields=("challenge_id", "status"), name="idx_user_challenges_challenge_status"),
            Index(fields=("end_at",), name="idx_user_challenges_end_at"),
        )


class ChallengeProgress(models.Model):
    id = fields.BigIntField(primary_key=True, description="진행률 ID")
    user_challenge = fields.ForeignKeyField(
        "models.UserChallenge",
        related_name="progress_periods",
        on_delete=fields.RESTRICT,
        description="사용자 챌린지 참여 ID",
    )
    period_start = fields.DateField(description="진행률 집계 시작일")
    period_end = fields.DateField(description="진행률 집계 종료일")
    target_count = fields.IntField(default=0, validators=[MinValueValidator(0)])
    completed_count = fields.IntField(default=0, validators=[MinValueValidator(0)])
    progress_rate = fields.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0"))
    is_completed = fields.BooleanField(default=False, description="해당 기간 목표 달성 여부")
    completed_at = fields.DatetimeField(null=True, description="해당 기간 목표 달성 일시")
    created_at = fields.DatetimeField(auto_now_add=True, description="등록 일시")
    updated_at = fields.DatetimeField(auto_now=True, null=True, description="최종 수정 일시")

    class Meta:
        table = "challenge_progress"
        unique_together = (("user_challenge", "period_start", "period_end"),)
        indexes = (
            Index(
                fields=("user_challenge_id", "is_completed"),
                name="idx_challenge_progress_completed",
            ),
            Index(fields=("period_end",), name="idx_challenge_progress_period_end"),
        )


class ChallengeVerification(models.Model):
    id = fields.BigIntField(primary_key=True, description="챌린지 인증 ID")
    user_challenge = fields.ForeignKeyField(
        "models.UserChallenge",
        related_name="verifications",
        on_delete=fields.RESTRICT,
        description="사용자 챌린지 참여 ID",
    )
    progress = fields.ForeignKeyField(
        "models.ChallengeProgress",
        related_name="verifications",
        on_delete=fields.RESTRICT,
        description="인증이 반영될 진행률 ID",
    )
    verification_date = fields.DateField(description="사용자 기준 인증일")
    content = fields.CharField(max_length=500, null=True, description="사용자 인증 내용")
    image_path = fields.CharField(max_length=500, null=True, description="인증 이미지 상대 경로")
    status = fields.CharEnumField(
        ChallengeVerificationStatus,
        default=ChallengeVerificationStatus.PENDING,
        description="인증 처리 상태",
    )
    rejection_reason = fields.CharField(max_length=500, null=True, description="인증 반려 사유")
    reviewed_by_admin = fields.ForeignKeyField(
        "models.Admin",
        related_name="reviewed_challenge_verifications",
        null=True,
        on_delete=fields.SET_NULL,
        description="수동 인증 검토 관리자 ID",
    )
    reviewed_at = fields.DatetimeField(null=True, description="승인 또는 반려 처리 일시")
    idempotency_key = fields.CharField(max_length=64, unique=True, description="인증 중복 등록 방지 키")
    submitted_at = fields.DatetimeField(auto_now_add=True, description="인증 제출 일시")
    created_at = fields.DatetimeField(auto_now_add=True, description="등록 일시")
    updated_at = fields.DatetimeField(auto_now=True, null=True, description="최종 수정 일시")

    class Meta:
        table = "challenge_verifications"
        unique_together = (("user_challenge", "verification_date"),)
        indexes = (
            Index(fields=("status", "submitted_at"), name="idx_challenge_verifications_review"),
            Index(fields=("progress_id",), name="idx_challenge_verifications_progress"),
            Index(fields=("reviewed_by_admin_id",), name="idx_challenge_verifications_admin"),
        )


class UserBadge(models.Model):
    id = fields.BigIntField(primary_key=True, description="사용자 배지 지급 ID")
    user = fields.ForeignKeyField(
        "models.User",
        related_name="awarded_badges",
        on_delete=fields.RESTRICT,
        description="배지 지급 사용자 ID",
    )
    badge = fields.ForeignKeyField(
        "models.Badge",
        related_name="user_awards",
        on_delete=fields.RESTRICT,
        description="지급 배지 ID",
    )
    challenge = fields.ForeignKeyField(
        "models.Challenge",
        related_name="badge_awards",
        on_delete=fields.RESTRICT,
        description="배지 지급 기준 챌린지 ID",
    )
    user_challenge = fields.ForeignKeyField(
        "models.UserChallenge",
        related_name="badge_awards",
        on_delete=fields.RESTRICT,
        description="완료한 사용자 챌린지 참여 ID",
    )
    status = fields.CharEnumField(
        BadgeAwardStatus,
        default=BadgeAwardStatus.AWARDED,
        description="배지 지급 상태",
    )
    badge_name = fields.CharField(max_length=100, description="지급 당시 배지 이름 스냅샷")
    badge_image_path = fields.CharField(max_length=500, description="지급 당시 활성 배지 이미지 경로")
    awarded_at = fields.DatetimeField(auto_now_add=True, description="배지 지급 일시")
    revoked_at = fields.DatetimeField(null=True, description="배지 회수 일시")
    revoke_reason = fields.CharField(max_length=500, null=True, description="배지 회수 사유")
    created_at = fields.DatetimeField(auto_now_add=True, description="등록 일시")
    updated_at = fields.DatetimeField(auto_now=True, null=True, description="최종 수정 일시")

    class Meta:
        table = "user_badges"
        unique_together = (("user_challenge", "badge"),)
        indexes = (
            Index(fields=("user_id", "status", "awarded_at"), name="idx_user_badges_user_status"),
            Index(fields=("challenge_id", "awarded_at"), name="idx_user_badges_challenge"),
        )
