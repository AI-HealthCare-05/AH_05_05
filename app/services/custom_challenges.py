from __future__ import annotations

import builtins
from collections.abc import Callable, Collection
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import cast

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.exceptions import IntegrityError
from tortoise.queryset import QuerySet
from tortoise.transactions import in_transaction

from app.core import config as _config
from app.core.config import Config
from app.core.exceptions import (
    CustomChallengeAlreadyActiveError,
    CustomChallengeCancelNotAllowedError,
    CustomChallengeIdempotencyConflictError,
    CustomChallengeInvalidTargetsError,
    CustomChallengeParticipationNotFoundError,
    CustomChallengeTemplateUnavailableError,
    CustomChallengeTypeUnsupportedError,
)
from app.dtos.custom_challenges import (
    CustomChallengeJoinRequest,
    CustomChallengeOccurrenceResponse,
    CustomChallengeParticipationListResponse,
    CustomChallengeParticipationResponse,
    CustomChallengeRecommendation,
    CustomChallengeRecommendationListResponse,
    CustomChallengeRecommendationTarget,
    CustomChallengeRewardBadge,
    CustomChallengeRewardClaimResponse,
    CustomChallengeTargetResponse,
)
from app.models.care import CareEpisode
from app.models.challenges import Badge, CustomChallengeTemplate
from app.models.custom_challenges import (
    CustomChallengeBadgeAward,
    CustomChallengeOccurrence,
    CustomChallengeParticipation,
    CustomChallengeTarget,
)
from app.models.enums import (
    CareEpisodeStatus,
    ChallengeParticipationStatus,
    CustomChallengeType,
    MealSlot,
    SupplementStatus,
)
from app.models.medications import MedicationDose
from app.models.supplement_nutrients import SupplementDose, UserSupplementNutrient
from app.models.users import User, UserSettings
from app.services.custom_challenge_badges import CustomChallengeBadgeService
from app.services.custom_challenge_goal_planner import KST, GoalKey, GoalWindow, PlannedGoal, plan_goals, seven_day_end
from app.services.custom_challenge_lifecycle import CustomChallengeLifecycleService

config = cast(Config, _config)

DEFAULT_MEAL_TIMES = {
    MealSlot.MORNING: time(8, 0),
    MealSlot.LUNCH: time(13, 0),
    MealSlot.EVENING: time(19, 0),
    MealSlot.BEDTIME: time(22, 0),
}
SLOT_ORDER = {slot: index for index, slot in enumerate(MealSlot)}
SLOT_TIME_FIELDS = {
    MealSlot.MORNING: "morning_medication_time",
    MealSlot.LUNCH: "lunch_medication_time",
    MealSlot.EVENING: "evening_medication_time",
    MealSlot.BEDTIME: "bedtime_medication_time",
}
PERCENT_QUANTUM = Decimal("0.01")


def custom_challenge_meal_times(settings: UserSettings | None) -> dict[MealSlot, time]:
    """Return planner meal times without creating or mutating user settings."""
    if settings is None:
        return DEFAULT_MEAL_TIMES.copy()
    return {slot: _normalize_time(getattr(settings, field_name)) for slot, field_name in SLOT_TIME_FIELDS.items()}


def _normalize_time(value: time | timedelta) -> time:
    if isinstance(value, time):
        return value
    seconds = int(value.total_seconds()) % (24 * 60 * 60)
    return time(seconds // 3600, (seconds % 3600) // 60, seconds % 60)


def medication_goal_windows(episode: CareEpisode) -> list[GoalWindow]:
    """Normalize one scheduled episode into planner windows for join and reconciliation."""
    windows: list[GoalWindow] = []
    for medication in episode.medications:
        days = medication.days or episode.medication_days
        if medication.times_per_day is None or days is None:
            continue
        last_date = episode.medication_start_date + timedelta(days=days - 1)
        for medication_slot in medication.slots:
            first_date = episode.medication_start_date
            if SLOT_ORDER[medication_slot.slot] < SLOT_ORDER[episode.medication_start_slot]:
                first_date += timedelta(days=1)
            if first_date <= last_date:
                windows.append(
                    GoalWindow(
                        source_id=episode.id,
                        slot=medication_slot.slot,
                        first_date=first_date,
                        last_date=last_date,
                    )
                )
    return windows


def supplement_goal_windows(registration: UserSupplementNutrient) -> list[GoalWindow]:
    """Normalize one supplement registration into planner windows."""
    return [
        GoalWindow(
            source_id=registration.id,
            slot=supplement_slot.slot,
            first_date=registration.start_date,
            last_date=registration.end_date,
        )
        for supplement_slot in registration.slots
    ]


def medication_challenge_end(windows: builtins.list[GoalWindow]) -> datetime | None:
    last_dates = [window.last_date for window in windows if window.last_date is not None]
    if not last_dates:
        return None
    return datetime.combine(max(last_dates) + timedelta(days=1), time.min, tzinfo=config.TIMEZONE)


async def completed_join_day_keys(
    *,
    user_id: int,
    source_kind: CustomChallengeType,
    source_ids: Collection[int],
    joined_at: datetime,
    connection: BaseDBAsyncClient | None = None,
    recorded_before_join: bool = False,
) -> set[GoalKey]:
    """Read dose keys only; joining must not award credit for already-taken doses.

    At join the transaction holds the user's lock, shared with dose saves. For
    reconciliation only pre-join records are excluded; later completions must
    remain attached to their existing goals and continue supporting undo.
    """
    if not source_ids:
        return set()
    joined_date = joined_at.astimezone(KST).date()
    query: QuerySet[MedicationDose] | QuerySet[SupplementDose]
    if source_kind is CustomChallengeType.MEDICATION:
        query = MedicationDose.filter(user_id=user_id, care_episode_id__in=source_ids, dose_date=joined_date)
        source_field = "care_episode_id"
    elif source_kind is CustomChallengeType.SUPPLEMENT:
        query = SupplementDose.filter(
            registration__user_id=user_id, registration_id__in=source_ids, dose_date=joined_date
        )
        source_field = "registration_id"
    else:
        return set()
    if recorded_before_join:
        # A pre-existing row can share the join timestamp at DB precision.
        # Existing goal keys are preserved separately by the reconciler.
        query = query.filter(taken_at__lte=joined_at)
    if connection is not None:
        query = query.using_db(connection)
    rows = await query.values_list(source_field, "dose_date", "slot")
    return {(source_id, dose_date, _meal_slot(slot)) for source_id, dose_date, slot in rows}


class CustomChallengeService:
    def __init__(
        self,
        now_provider: Callable[[], datetime] | None = None,
        lifecycle: CustomChallengeLifecycleService | None = None,
        badge_service: CustomChallengeBadgeService | None = None,
    ) -> None:
        self._now_provider = now_provider or (lambda: datetime.now(config.TIMEZONE))
        self._lifecycle = lifecycle or CustomChallengeLifecycleService()
        self._badge_service = badge_service or CustomChallengeBadgeService()

    async def recommendations(self, user: User) -> CustomChallengeRecommendationListResponse:
        now = await self._finalize_due_for_user(user.id)
        meal_times = await self._meal_times(user.id)
        templates = await self._active_templates()
        medication_sources = await self._eligible_medication_sources(
            user.id,
            now,
            meal_times,
        )
        supplement_sources = await self._eligible_supplement_sources(
            user.id,
            now,
            meal_times,
        )
        active_target_participations = await self._active_target_participations(user.id)

        recommendations: builtins.list[CustomChallengeRecommendation] = []
        for template in templates:
            challenge_type = self._template_type(template)
            if challenge_type is None or challenge_type is CustomChallengeType.VISIT:
                continue
            sources = medication_sources if challenge_type is CustomChallengeType.MEDICATION else supplement_sources
            if not sources:
                continue
            recommendations.append(
                CustomChallengeRecommendation(
                    template_id=template.id,
                    challenge_type=challenge_type,
                    challenge_name=template.name,
                    reward_badge=self._reward_badge(template),
                    targets=[
                        CustomChallengeRecommendationTarget(
                            id=source_id,
                            name=name,
                            existing_participation_id=active_target_participations.get((challenge_type, source_id)),
                        )
                        for source_id, name, _windows, _goals in sources
                    ],
                )
            )
        return CustomChallengeRecommendationListResponse(
            items=recommendations,
            total_count=len(recommendations),
        )

    async def join(
        self,
        user: User,
        template_id: int,
        request: CustomChallengeJoinRequest,
    ) -> CustomChallengeParticipationResponse:
        target_ids = tuple(request.target_ids)
        try:
            participation_id = await self._join_transaction(
                user_id=user.id,
                template_id=template_id,
                target_ids=target_ids,
                idempotency_key=request.idempotency_key,
            )
        except IntegrityError:
            existing = await CustomChallengeParticipation.get_or_none(
                user_id=user.id,
                idempotency_key=request.idempotency_key,
            )
            if existing is None:
                raise
            await self._assert_idempotent_request(existing, template_id, target_ids)
            participation_id = existing.id
        return await self.get(user, participation_id)

    async def list(self, user: User) -> CustomChallengeParticipationListResponse:
        await self._finalize_due_for_user(user.id)
        participations = await CustomChallengeParticipation.filter(user_id=user.id).order_by("-joined_at", "-id")
        items = [await self._to_response(participation) for participation in participations]
        return CustomChallengeParticipationListResponse(items=items, total_count=len(items))

    async def get(self, user: User, participation_id: int) -> CustomChallengeParticipationResponse:
        await self._finalize_due_for_user(user.id)
        participation = await CustomChallengeParticipation.get_or_none(id=participation_id, user_id=user.id)
        if participation is None:
            raise CustomChallengeParticipationNotFoundError()
        return await self._to_response(participation)

    async def claim_reward(
        self,
        user: User,
        participation_id: int,
    ) -> CustomChallengeRewardClaimResponse:
        award = None
        newly_awarded = False
        async with in_transaction() as connection:
            locked_user = await User.filter(id=user.id).using_db(connection).select_for_update().first()
            if locked_user is None:
                raise CustomChallengeParticipationNotFoundError()
            now = self._now()
            await self._lifecycle.finalize_due_for_user(
                user_id=user.id,
                now=now,
                connection=connection,
            )
            participation = await (
                CustomChallengeParticipation.filter(id=participation_id, user_id=user.id)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if participation is None:
                raise CustomChallengeParticipationNotFoundError()
            if participation.status is ChallengeParticipationStatus.ACTIVE:
                await self._lifecycle.finalize_if_complete(participation, now, connection)
            award = await self._badge_service.get_for_participation(
                user.id,
                participation.id,
                using_db=connection,
            )
            if award is None and (
                participation.status is ChallengeParticipationStatus.COMPLETED
                and participation.finalized_at is not None
                and participation.target_count > 0
                and participation.completed_count == participation.target_count
            ):
                award, newly_awarded = await self._badge_service.award_for_completed_participation_with_status(
                    participation,
                    using_db=connection,
                )

            response = CustomChallengeRewardClaimResponse(
                participation=await self._to_response(participation, connection=connection),
                award=self._badge_service.response(award) if award is not None else None,
                newly_awarded=newly_awarded,
            )
        return response

    async def cancel(self, user: User, participation_id: int) -> CustomChallengeParticipationResponse:
        async with in_transaction() as connection:
            locked_user = await User.filter(id=user.id).using_db(connection).select_for_update().first()
            if locked_user is None:
                raise CustomChallengeParticipationNotFoundError()
            now = self._now()
            await self._lifecycle.finalize_due_for_user(
                user_id=user.id,
                now=now,
                connection=connection,
            )
            participation = await (
                CustomChallengeParticipation.filter(id=participation_id, user_id=user.id)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if participation is None:
                raise CustomChallengeParticipationNotFoundError()
            if participation.status is ChallengeParticipationStatus.ACTIVE:
                await self._lifecycle.finalize_cancelled(participation, now, connection)

        # Commit any due result finalization before rejecting cancellation.
        if participation.status is not ChallengeParticipationStatus.CANCELLED:
            raise CustomChallengeCancelNotAllowedError()
        return await self._to_response(participation)

    async def _join_transaction(
        self,
        *,
        user_id: int,
        template_id: int,
        target_ids: tuple[int, ...],
        idempotency_key: str,
    ) -> int:
        async with in_transaction() as connection:
            locked_user = await User.filter(id=user_id).using_db(connection).select_for_update().first()
            if locked_user is None:
                raise CustomChallengeParticipationNotFoundError()
            now = self._now()
            await self._lifecycle.finalize_due_for_user(
                user_id=user_id,
                now=now,
                connection=connection,
            )
            existing = (
                await CustomChallengeParticipation.filter(
                    user_id=user_id,
                    idempotency_key=idempotency_key,
                )
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if existing is not None:
                await self._assert_idempotent_request(existing, template_id, target_ids, connection)
                return existing.id

            template, challenge_type = await self._join_template(template_id, target_ids, connection)
            await self._lock_sources(user_id, target_ids, challenge_type, connection)
            settings = await self._lock_or_create_settings(user_id, connection)
            meal_times = custom_challenge_meal_times(settings)
            sources = await self._requested_sources(
                user_id,
                target_ids,
                challenge_type,
                now,
                meal_times,
                connection,
            )
            if tuple(source[0] for source in sources) != target_ids:
                raise CustomChallengeInvalidTargetsError()

            end_at = (
                medication_challenge_end(sources[0][2])
                if challenge_type is CustomChallengeType.MEDICATION
                else seven_day_end(now)
            )
            if end_at is None or end_at <= now:
                raise CustomChallengeInvalidTargetsError()

            await self._assert_no_active_duplicate(
                user_id=user_id,
                challenge_type=challenge_type,
                target_ids=target_ids,
                connection=connection,
            )
            participation = await CustomChallengeParticipation.create(
                user_id=user_id,
                template_id=template_id,
                reward_badge_id=template.reward_badge_id,
                challenge_type=challenge_type,
                challenge_name=template.name,
                idempotency_key=idempotency_key,
                joined_at=now,
                end_at=end_at,
                status=ChallengeParticipationStatus.ACTIVE,
                using_db=connection,
            )
            for source_id, name, _windows, goals in sources:
                target_values: dict[str, int] = {}
                if challenge_type is CustomChallengeType.MEDICATION:
                    target_values["care_episode_id"] = source_id
                else:
                    target_values["supplement_registration_id"] = source_id
                target = await CustomChallengeTarget.create(
                    participation_id=participation.id,
                    source_id_snapshot=source_id,
                    target_name_snapshot=name,
                    using_db=connection,
                    **target_values,
                )
                await CustomChallengeOccurrence.bulk_create(
                    [
                        CustomChallengeOccurrence(
                            target_id=target.id,
                            scheduled_date=goal.scheduled_date,
                            slot=goal.slot,
                            scheduled_at=goal.scheduled_at,
                        )
                        for goal in goals
                    ],
                    using_db=connection,
                )
            return participation.id

    async def _join_template(
        self,
        template_id: int,
        target_ids: tuple[int, ...],
        connection: BaseDBAsyncClient,
    ) -> tuple[CustomChallengeTemplate, CustomChallengeType]:
        template = (
            await CustomChallengeTemplate.filter(id=template_id, is_active=True)
            .using_db(connection)
            .select_for_update()
            .prefetch_related("challenge_type__group", "check_type__group")
            .first()
        )
        challenge_type = self._template_type(template) if template is not None else None
        if template is None or challenge_type is None:
            raise CustomChallengeTemplateUnavailableError()
        if challenge_type is CustomChallengeType.VISIT:
            raise CustomChallengeTypeUnsupportedError()
        if challenge_type is CustomChallengeType.MEDICATION and len(target_ids) != 1:
            raise CustomChallengeInvalidTargetsError()
        return template, challenge_type

    @staticmethod
    async def _lock_sources(
        user_id: int,
        target_ids: tuple[int, ...],
        challenge_type: CustomChallengeType,
        connection: BaseDBAsyncClient,
    ) -> None:
        # Match MedicationScheduleService's established order: User -> source -> settings.
        source_model = CareEpisode if challenge_type is CustomChallengeType.MEDICATION else UserSupplementNutrient
        await (
            source_model.filter(id__in=target_ids, user_id=user_id)
            .using_db(connection)
            .select_for_update()
            .order_by("id")
        )

    @staticmethod
    async def _lock_or_create_settings(
        user_id: int,
        connection: BaseDBAsyncClient,
    ) -> UserSettings:
        settings = await UserSettings.filter(user_id=user_id).using_db(connection).select_for_update().first()
        if settings is None:
            settings = await UserSettings.create(user_id=user_id, using_db=connection)
        return settings

    async def _requested_sources(
        self,
        user_id: int,
        target_ids: tuple[int, ...],
        challenge_type: CustomChallengeType,
        now: datetime,
        meal_times: dict[MealSlot, time],
        connection: BaseDBAsyncClient,
    ) -> builtins.list[tuple[int, str, builtins.list[GoalWindow], builtins.list[PlannedGoal]]]:
        if challenge_type is CustomChallengeType.MEDICATION:
            return await self._eligible_medication_sources(
                user_id,
                now,
                meal_times,
                requested_ids=target_ids,
                connection=connection,
            )
        return await self._eligible_supplement_sources(
            user_id,
            now,
            meal_times,
            requested_ids=target_ids,
            connection=connection,
        )

    async def _eligible_medication_sources(
        self,
        user_id: int,
        now: datetime,
        meal_times: dict[MealSlot, time],
        *,
        requested_ids: tuple[int, ...] | None = None,
        connection: BaseDBAsyncClient | None = None,
        lock: bool = False,
    ) -> builtins.list[tuple[int, str, builtins.list[GoalWindow], builtins.list[PlannedGoal]]]:
        query = CareEpisode.filter(
            user_id=user_id,
            status=CareEpisodeStatus.ACTIVE,
            medication_start_date__isnull=False,
            medication_start_slot__isnull=False,
        ).order_by("id")
        if requested_ids is not None:
            query = query.filter(id__in=requested_ids)
        if connection is not None:
            query = query.using_db(connection)
        if lock:
            query = query.select_for_update()
        episodes = await query.prefetch_related("medications__slots")
        completed_keys = await completed_join_day_keys(
            user_id=user_id,
            source_kind=CustomChallengeType.MEDICATION,
            source_ids=[episode.id for episode in episodes],
            joined_at=now,
            connection=connection,
        )
        result: builtins.list[tuple[int, str, builtins.list[GoalWindow], builtins.list[PlannedGoal]]] = []
        for episode in episodes:
            windows = medication_goal_windows(episode)
            end_at = medication_challenge_end(windows)
            if end_at is None or end_at <= now:
                continue
            goals = plan_goals(
                windows=windows,
                meal_times=meal_times,
                joined_at=now,
                end_at=end_at,
                include_join_slot=True,
                excluded_keys=completed_keys,
            )
            if goals:
                name = episode.alias or episode.hospital_name or f"복약 기록 {episode.id}"
                result.append((episode.id, name, windows, goals))
        return result

    async def _eligible_supplement_sources(
        self,
        user_id: int,
        now: datetime,
        meal_times: dict[MealSlot, time],
        *,
        requested_ids: tuple[int, ...] | None = None,
        connection: BaseDBAsyncClient | None = None,
        lock: bool = False,
    ) -> builtins.list[tuple[int, str, builtins.list[GoalWindow], builtins.list[PlannedGoal]]]:
        query = UserSupplementNutrient.filter(
            user_id=user_id,
            status=SupplementStatus.ACTIVE,
        ).order_by("id")
        if requested_ids is not None:
            query = query.filter(id__in=requested_ids)
        if connection is not None:
            query = query.using_db(connection)
        if lock:
            query = query.select_for_update()
        registrations = await query.prefetch_related("slots", "supplement_nutrient")
        completed_keys = await completed_join_day_keys(
            user_id=user_id,
            source_kind=CustomChallengeType.SUPPLEMENT,
            source_ids=[registration.id for registration in registrations],
            joined_at=now,
            connection=connection,
        )
        end_at = seven_day_end(now)
        result: builtins.list[tuple[int, str, builtins.list[GoalWindow], builtins.list[PlannedGoal]]] = []
        for registration in registrations:
            windows = supplement_goal_windows(registration)
            goals = plan_goals(
                windows=windows,
                meal_times=meal_times,
                joined_at=now,
                end_at=end_at,
                include_join_slot=True,
                excluded_keys=completed_keys,
            )
            if goals:
                product = registration.supplement_nutrient
                name = registration.custom_name or (product.name if product is not None else None)
                result.append((registration.id, name or f"영양제 {registration.id}", windows, goals))
        return result

    async def _assert_idempotent_request(
        self,
        existing: CustomChallengeParticipation,
        template_id: int,
        target_ids: tuple[int, ...],
        connection: BaseDBAsyncClient | None = None,
    ) -> None:
        query = CustomChallengeTarget.filter(participation_id=existing.id).order_by("source_id_snapshot")
        if connection is not None:
            query = query.using_db(connection)
        existing_target_ids = tuple(await query.values_list("source_id_snapshot", flat=True))
        if existing.template_id != template_id or existing_target_ids != target_ids:
            raise CustomChallengeIdempotencyConflictError()

    async def _assert_no_active_duplicate(
        self,
        *,
        user_id: int,
        challenge_type: CustomChallengeType,
        target_ids: tuple[int, ...],
        connection: BaseDBAsyncClient,
    ) -> None:
        participations = (
            await CustomChallengeParticipation.filter(
                user_id=user_id,
                challenge_type=challenge_type,
                status=ChallengeParticipationStatus.ACTIVE,
            )
            .using_db(connection)
            .select_for_update()
            .order_by("id")
        )
        for participation in participations:
            existing_ids = tuple(
                await CustomChallengeTarget.filter(participation_id=participation.id)
                .using_db(connection)
                .order_by("source_id_snapshot")
                .values_list("source_id_snapshot", flat=True)
            )
            # User and source rows are locked before this check, so concurrent
            # joins cannot create overlapping active targets. Idempotent retries
            # have already returned above, including historical participations.
            if set(existing_ids).intersection(target_ids):
                raise CustomChallengeAlreadyActiveError()

    async def _active_templates(self) -> builtins.list[CustomChallengeTemplate]:
        return (
            await CustomChallengeTemplate.filter(is_active=True)
            .prefetch_related("challenge_type__group", "check_type__group", "reward_badge")
            .order_by("id")
        )

    @staticmethod
    def _template_type(template: CustomChallengeTemplate) -> CustomChallengeType | None:
        type_code = template.challenge_type
        if type_code is None:
            return None
        for code, group_code in (
            (type_code, "CST_CHL_TYPE"),
            (template.check_type, "CST_CHK_TYPE"),
        ):
            if (
                not code.is_active
                or not code.group.is_active
                or code.group.category != "CHL"
                or code.group.group_code != group_code
            ):
                return None
        if template.check_type.detail_code != "AUTO":
            return None
        try:
            return CustomChallengeType(type_code.detail_code)
        except ValueError:
            return None

    @staticmethod
    def _reward_badge(template: CustomChallengeTemplate) -> CustomChallengeRewardBadge | None:
        badge = template.reward_badge
        if badge is None or not badge.is_active:
            return None
        return CustomChallengeRewardBadge(
            id=badge.id, name=badge.name, description=badge.description, image_path=badge.image_path
        )

    async def _active_target_participations(
        self,
        user_id: int,
    ) -> dict[tuple[CustomChallengeType, int], int]:
        targets = (
            await CustomChallengeTarget.filter(
                participation__user_id=user_id,
                participation__status=ChallengeParticipationStatus.ACTIVE,
            )
            .prefetch_related("participation")
            .order_by("participation__joined_at", "participation_id", "id")
        )
        return {
            (
                target.participation.challenge_type,
                target.source_id_snapshot,
            ): target.participation_id
            for target in targets
        }

    async def _meal_times(self, user_id: int) -> dict[MealSlot, time]:
        settings = await UserSettings.get_or_none(user_id=user_id)
        return custom_challenge_meal_times(settings)

    async def _to_response(
        self,
        participation: CustomChallengeParticipation,
        *,
        connection: BaseDBAsyncClient | None = None,
    ) -> CustomChallengeParticipationResponse:
        if connection is None:
            await participation.fetch_related("reward_badge")
            badge = participation.reward_badge
        else:
            badge = (
                await Badge.filter(id=participation.reward_badge_id).using_db(connection).first()
                if participation.reward_badge_id is not None
                else None
            )
        reward_badge = self._participation_reward_badge(badge)
        if participation.finalized_at is not None:
            award_query = CustomChallengeBadgeAward.filter(participation_id=participation.id)
            if connection is not None:
                award_query = award_query.using_db(connection)
            award = await award_query.first()
            if award is not None:
                reward_badge = CustomChallengeRewardBadge(
                    id=award.badge_id,
                    name=award.badge_name,
                    description=(badge.description if badge else None),
                    image_path=award.badge_image_path,
                )
        targets_query = CustomChallengeTarget.filter(participation_id=participation.id).order_by("source_id_snapshot")
        if connection is not None:
            targets_query = targets_query.using_db(connection)
        targets = await targets_query
        target_ids = [target.id for target in targets]
        occurrences_query = CustomChallengeOccurrence.filter(target_id__in=target_ids).order_by(
            "scheduled_at",
            "target_id",
            "slot",
            "id",
        )
        if connection is not None:
            occurrences_query = occurrences_query.using_db(connection)
        occurrences = await occurrences_query if target_ids else []
        if participation.finalized_at is not None:
            completed = {occurrence.id for occurrence in occurrences if occurrence.is_completed}
            target_count = participation.target_count
            completed_count = participation.completed_count
            progress_rate = participation.progress_rate
        else:
            completed = await self._completed_occurrence_ids(
                participation,
                targets,
                occurrences,
                connection=connection,
            )
            target_count = len(occurrences)
            completed_count = len(completed)
            progress_rate = (
                (Decimal(completed_count) * Decimal(100) / Decimal(target_count)).quantize(PERCENT_QUANTUM)
                if target_count
                else Decimal("0.00")
            )
        # A day is achieved only when every actual goal across its targets is complete.
        # Reuse the resolved IDs above so finalized responses retain frozen snapshots.
        completed_by_date: dict[date, bool] = {}
        for occurrence in occurrences:
            completed_by_date[occurrence.scheduled_date] = (
                completed_by_date.get(occurrence.scheduled_date, True) and occurrence.id in completed
            )
        target_day_count = len(completed_by_date)
        completed_day_count = sum(completed_by_date.values())
        day_progress_rate = (
            (Decimal(completed_day_count) * Decimal(100) / Decimal(target_day_count)).quantize(PERCENT_QUANTUM)
            if target_day_count
            else Decimal("0.00")
        )
        occurrence_responses = [
            CustomChallengeOccurrenceResponse(
                id=occurrence.id,
                target_id=occurrence.target_id,
                scheduled_date=occurrence.scheduled_date,
                slot=occurrence.slot,
                scheduled_at=self._aware(occurrence.scheduled_at),
                is_completed=occurrence.id in completed,
            )
            for occurrence in occurrences
        ]
        return CustomChallengeParticipationResponse(
            id=participation.id,
            template_id=participation.template_id,
            challenge_type=participation.challenge_type,
            challenge_name=participation.challenge_name,
            reward_badge=reward_badge,
            status=participation.status,
            joined_at=self._aware(participation.joined_at),
            end_at=self._aware(participation.end_at),
            actual_end_date=occurrences[-1].scheduled_date if occurrences else None,
            target_count=target_count,
            completed_count=completed_count,
            progress_rate=progress_rate,
            target_day_count=target_day_count,
            completed_day_count=completed_day_count,
            day_progress_rate=day_progress_rate,
            targets=[
                CustomChallengeTargetResponse(
                    id=target.id,
                    source_id=target.source_id_snapshot,
                    name=target.target_name_snapshot,
                )
                for target in targets
            ],
            occurrences=occurrence_responses,
        )

    async def _completed_occurrence_ids(
        self,
        participation: CustomChallengeParticipation,
        targets: builtins.list[CustomChallengeTarget],
        occurrences: builtins.list[CustomChallengeOccurrence],
        *,
        connection: BaseDBAsyncClient | None = None,
    ) -> set[int]:
        if participation.challenge_type is CustomChallengeType.MEDICATION:
            source_to_target = {
                target.care_episode_id: target.id for target in targets if target.care_episode_id is not None
            }
            rows_query = MedicationDose.filter(
                user_id=participation.user_id,
                care_episode_id__in=source_to_target,
            )
            if connection is not None:
                rows_query = rows_query.using_db(connection)
            rows = await rows_query.values_list("care_episode_id", "dose_date", "slot")
        elif participation.challenge_type is CustomChallengeType.SUPPLEMENT:
            source_to_target = {
                target.supplement_registration_id: target.id
                for target in targets
                if target.supplement_registration_id is not None
            }
            rows_query = SupplementDose.filter(
                registration_id__in=source_to_target,
                registration__user_id=participation.user_id,
            )
            if connection is not None:
                rows_query = rows_query.using_db(connection)
            rows = await rows_query.values_list("registration_id", "dose_date", "slot")
        else:
            return set()
        completed_keys = {
            (source_to_target[source_id], dose_date, _meal_slot(slot))
            for source_id, dose_date, slot in rows
            if source_id in source_to_target
        }
        return {
            occurrence.id
            for occurrence in occurrences
            if (occurrence.target_id, occurrence.scheduled_date, _meal_slot(occurrence.slot)) in completed_keys
        }

    @staticmethod
    def _participation_reward_badge(badge: Badge | None) -> CustomChallengeRewardBadge | None:
        if badge is None:
            return None
        return CustomChallengeRewardBadge(
            id=badge.id,
            name=badge.name,
            description=badge.description,
            image_path=badge.image_path,
        )

    def _now(self) -> datetime:
        return self._aware(self._now_provider())

    async def _finalize_due_for_user(self, user_id: int) -> datetime:
        async with in_transaction() as connection:
            locked_user = await User.filter(id=user_id).using_db(connection).select_for_update().first()
            if locked_user is None:
                raise CustomChallengeParticipationNotFoundError()
            now = self._now()
            await self._lifecycle.finalize_due_for_user(
                user_id=user_id,
                now=now,
                connection=connection,
            )
        return now

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=config.TIMEZONE)
        return value.astimezone(config.TIMEZONE)


def _meal_slot(value: MealSlot | str) -> MealSlot:
    return value if isinstance(value, MealSlot) else MealSlot(value)
