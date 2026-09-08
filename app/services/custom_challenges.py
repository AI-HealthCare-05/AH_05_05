from __future__ import annotations

import builtins
from collections.abc import Callable
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import cast

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core import config as _config
from app.core.config import Config
from app.core.exceptions import (
    CustomChallengeAlreadyActiveError,
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
    CustomChallengeTargetResponse,
)
from app.models.care import CareEpisode
from app.models.challenges import CustomChallengeTemplate
from app.models.custom_challenges import (
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
from app.services.custom_challenge_goal_planner import GoalWindow, PlannedGoal, plan_goals, seven_day_end

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
    return {
        slot: _normalize_time(getattr(settings, field_name))
        for slot, field_name in SLOT_TIME_FIELDS.items()
    }


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


class CustomChallengeService:
    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        self._now_provider = now_provider or (lambda: datetime.now(config.TIMEZONE))

    async def recommendations(self, user: User) -> CustomChallengeRecommendationListResponse:
        now = self._now()
        meal_times = await self._meal_times(user.id)
        templates = await self._active_mapped_templates()
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
            challenge_type = config.CUSTOM_CHALLENGE_TEMPLATE_TYPES[template.id]
            if challenge_type is CustomChallengeType.VISIT:
                continue
            sources = medication_sources if challenge_type is CustomChallengeType.MEDICATION else supplement_sources
            if not sources:
                continue
            recommendations.append(
                CustomChallengeRecommendation(
                    template_id=template.id,
                    challenge_type=challenge_type,
                    challenge_name=template.name,
                    targets=[
                        CustomChallengeRecommendationTarget(
                            id=source_id,
                            name=name,
                            existing_participation_id=active_target_participations.get(
                                (challenge_type, source_id)
                            ),
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
        participations = await CustomChallengeParticipation.filter(user_id=user.id).order_by("-joined_at", "-id")
        items = [await self._to_response(participation) for participation in participations]
        return CustomChallengeParticipationListResponse(items=items, total_count=len(items))

    async def get(self, user: User, participation_id: int) -> CustomChallengeParticipationResponse:
        participation = await CustomChallengeParticipation.get_or_none(id=participation_id, user_id=user.id)
        if participation is None:
            raise CustomChallengeParticipationNotFoundError()
        return await self._to_response(participation)

    async def _join_transaction(
        self,
        *,
        user_id: int,
        template_id: int,
        target_ids: tuple[int, ...],
        idempotency_key: str,
    ) -> int:
        now = self._now()
        end_at = seven_day_end(now)
        async with in_transaction() as connection:
            locked_user = (
                await User.filter(id=user_id).using_db(connection).select_for_update().first()
            )
            if locked_user is None:
                raise CustomChallengeParticipationNotFoundError()
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

            await self._assert_no_active_duplicate(
                user_id=user_id,
                challenge_type=challenge_type,
                target_ids=target_ids,
                connection=connection,
            )
            participation = await CustomChallengeParticipation.create(
                user_id=user_id,
                template_id=template_id,
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
            .first()
        )
        challenge_type = config.CUSTOM_CHALLENGE_TEMPLATE_TYPES.get(template_id)
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
        await source_model.filter(id__in=target_ids, user_id=user_id).using_db(connection).select_for_update().order_by(
            "id"
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
    ) -> builtins.list[
        tuple[int, str, builtins.list[GoalWindow], builtins.list[PlannedGoal]]
    ]:
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
    ) -> builtins.list[
        tuple[int, str, builtins.list[GoalWindow], builtins.list[PlannedGoal]]
    ]:
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
        end_at = seven_day_end(now)
        result: builtins.list[
            tuple[int, str, builtins.list[GoalWindow], builtins.list[PlannedGoal]]
        ] = []
        for episode in episodes:
            windows = medication_goal_windows(episode)
            goals = plan_goals(
                windows=windows,
                meal_times=meal_times,
                joined_at=now,
                end_at=end_at,
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
    ) -> builtins.list[
        tuple[int, str, builtins.list[GoalWindow], builtins.list[PlannedGoal]]
    ]:
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
        end_at = seven_day_end(now)
        result: builtins.list[
            tuple[int, str, builtins.list[GoalWindow], builtins.list[PlannedGoal]]
        ] = []
        for registration in registrations:
            windows = supplement_goal_windows(registration)
            goals = plan_goals(
                windows=windows,
                meal_times=meal_times,
                joined_at=now,
                end_at=end_at,
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
        expected_type = config.CUSTOM_CHALLENGE_TEMPLATE_TYPES.get(template_id)
        if (
            existing.template_id != template_id
            or existing.challenge_type != expected_type
            or existing_target_ids != target_ids
        ):
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
            if existing_ids == target_ids:
                raise CustomChallengeAlreadyActiveError()

    async def _active_mapped_templates(self) -> builtins.list[CustomChallengeTemplate]:
        template_ids = sorted(config.CUSTOM_CHALLENGE_TEMPLATE_TYPES)
        if not template_ids:
            return []
        return await CustomChallengeTemplate.filter(id__in=template_ids, is_active=True).order_by("id")

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
    ) -> CustomChallengeParticipationResponse:
        targets = await CustomChallengeTarget.filter(participation_id=participation.id).order_by("source_id_snapshot")
        target_ids = [target.id for target in targets]
        occurrences = (
            await CustomChallengeOccurrence.filter(target_id__in=target_ids).order_by(
                "scheduled_at",
                "target_id",
                "slot",
                "id",
            )
            if target_ids
            else []
        )
        completed = await self._completed_occurrence_ids(participation, targets, occurrences)
        target_count = len(occurrences)
        completed_count = len(completed)
        progress_rate = (
            (Decimal(completed_count) * Decimal(100) / Decimal(target_count)).quantize(PERCENT_QUANTUM)
            if target_count
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
            status=participation.status,
            joined_at=self._aware(participation.joined_at),
            end_at=self._aware(participation.end_at),
            actual_end_date=occurrences[-1].scheduled_date,
            target_count=target_count,
            completed_count=completed_count,
            progress_rate=progress_rate,
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
    ) -> set[int]:
        if participation.challenge_type is CustomChallengeType.MEDICATION:
            source_to_target = {
                target.care_episode_id: target.id for target in targets if target.care_episode_id is not None
            }
            rows = await MedicationDose.filter(
                user_id=participation.user_id,
                care_episode_id__in=source_to_target,
            ).values_list("care_episode_id", "dose_date", "slot")
        elif participation.challenge_type is CustomChallengeType.SUPPLEMENT:
            source_to_target = {
                target.supplement_registration_id: target.id
                for target in targets
                if target.supplement_registration_id is not None
            }
            rows = await SupplementDose.filter(
                registration_id__in=source_to_target,
                registration__user_id=participation.user_id,
            ).values_list("registration_id", "dose_date", "slot")
        else:
            return set()
        completed_keys = {(source_to_target[source_id], dose_date, slot) for source_id, dose_date, slot in rows}
        return {
            occurrence.id
            for occurrence in occurrences
            if (occurrence.target_id, occurrence.scheduled_date, occurrence.slot) in completed_keys
        }

    def _now(self) -> datetime:
        return self._aware(self._now_provider())

    @staticmethod
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=config.TIMEZONE)
        return value.astimezone(config.TIMEZONE)
