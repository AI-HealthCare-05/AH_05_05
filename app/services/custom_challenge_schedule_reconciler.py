from collections.abc import Collection
from datetime import datetime
from typing import cast

from tortoise.backends.base.client import BaseDBAsyncClient

from app.core import config
from app.models.care import CareEpisode
from app.models.custom_challenges import (
    CustomChallengeOccurrence,
    CustomChallengeParticipation,
    CustomChallengeTarget,
)
from app.models.enums import (
    CareEpisodeStatus,
    ChallengeParticipationStatus,
    CustomChallengeType,
    SupplementStatus,
)
from app.models.supplement_nutrients import UserSupplementNutrient
from app.models.users import UserSettings
from app.services.custom_challenge_goal_planner import (
    GoalKey,
    GoalWindow,
    PlannedGoal,
    plan_goals,
)
from app.services.custom_challenges import (
    custom_challenge_meal_times,
    medication_goal_windows,
    supplement_goal_windows,
)


class CustomChallengeScheduleReconciler:
    """Diff future goals inside a caller-owned source mutation transaction."""

    async def reconcile(
        self,
        *,
        user_id: int,
        source_kind: CustomChallengeType,
        source_ids: Collection[int] | None,
        changed_at: datetime,
        connection: BaseDBAsyncClient,
    ) -> None:
        if source_kind not in {
            CustomChallengeType.MEDICATION,
            CustomChallengeType.SUPPLEMENT,
        }:
            raise ValueError("only medication and supplement schedules can be reconciled")
        if changed_at.tzinfo is None or changed_at.utcoffset() is None:
            raise ValueError("changed_at must be timezone-aware")
        changed_at = changed_at.astimezone(config.TIMEZONE)

        selected_ids = None if source_ids is None else tuple(sorted(set(source_ids)))
        if selected_ids == ():
            return

        participations = await (
            CustomChallengeParticipation.filter(
                user_id=user_id,
                challenge_type=source_kind,
                status=ChallengeParticipationStatus.ACTIVE,
            )
            .using_db(connection)
            .select_for_update()
            .order_by("id")
        )
        if not participations:
            return
        participations_by_id = {participation.id: participation for participation in participations}

        targets_query = CustomChallengeTarget.filter(
            participation_id__in=participations_by_id,
        )
        if selected_ids is not None:
            targets_query = targets_query.filter(source_id_snapshot__in=selected_ids)
        targets = await (
            targets_query.using_db(connection)
            .select_for_update()
            .order_by("participation_id", "id")
        )
        if not targets:
            return

        settings = await UserSettings.filter(user_id=user_id).using_db(connection).first()
        meal_times = custom_challenge_meal_times(settings)
        windows_by_source = await self._windows_by_source(
            user_id=user_id,
            source_kind=source_kind,
            targets=targets,
            connection=connection,
        )

        for target in targets:
            participation = participations_by_id[cast(int, target.participation_id)]
            occurrences = await (
                CustomChallengeOccurrence.filter(target_id=target.id)
                .using_db(connection)
                .select_for_update()
                .order_by("id")
            )
            past = [row for row in occurrences if _database_datetime(row.scheduled_at) < changed_at]
            future = [row for row in occurrences if _database_datetime(row.scheduled_at) >= changed_at]
            preserved_keys: set[GoalKey] = {
                (target.source_id_snapshot, row.scheduled_date, row.slot) for row in past
            }
            desired = plan_goals(
                windows=windows_by_source.get(target.source_id_snapshot, []),
                meal_times=meal_times,
                joined_at=_database_datetime(participation.joined_at),
                end_at=_database_datetime(participation.end_at),
                not_before=changed_at,
                preserved_keys=preserved_keys,
            )
            await self._replace_future(
                target_id=target.id,
                future=future,
                desired=desired,
                connection=connection,
            )

    @staticmethod
    async def _windows_by_source(
        *,
        user_id: int,
        source_kind: CustomChallengeType,
        targets: list[CustomChallengeTarget],
        connection: BaseDBAsyncClient,
    ) -> dict[int, list[GoalWindow]]:
        if source_kind is CustomChallengeType.MEDICATION:
            source_ids = {
                cast(int, target.care_episode_id)
                for target in targets
                if target.care_episode_id is not None
                and cast(int, target.care_episode_id) == target.source_id_snapshot
            }
            episodes = (
                await CareEpisode.filter(
                    id__in=source_ids,
                    user_id=user_id,
                    status=CareEpisodeStatus.ACTIVE,
                    medication_start_date__isnull=False,
                    medication_start_slot__isnull=False,
                )
                .using_db(connection)
                .prefetch_related("medications__slots")
                .order_by("id")
                if source_ids
                else []
            )
            return {episode.id: medication_goal_windows(episode) for episode in episodes}

        source_ids = {
            cast(int, target.supplement_registration_id)
            for target in targets
            if target.supplement_registration_id is not None
            and cast(int, target.supplement_registration_id) == target.source_id_snapshot
        }
        registrations = (
            await UserSupplementNutrient.filter(
                id__in=source_ids,
                user_id=user_id,
                status=SupplementStatus.ACTIVE,
            )
            .using_db(connection)
            .prefetch_related("slots")
            .order_by("id")
            if source_ids
            else []
        )
        return {
            registration.id: supplement_goal_windows(registration)
            for registration in registrations
        }

    @staticmethod
    async def _replace_future(
        *,
        target_id: int,
        future: list[CustomChallengeOccurrence],
        desired: list[PlannedGoal],
        connection: BaseDBAsyncClient,
    ) -> None:
        existing_by_key = {
            (row.scheduled_date, row.slot): row
            for row in future
        }
        desired_by_key = {
            (goal.scheduled_date, goal.slot): goal
            for goal in desired
        }

        for key in existing_by_key.keys() & desired_by_key.keys():
            occurrence = existing_by_key[key]
            planned = desired_by_key[key]
            if _database_datetime(occurrence.scheduled_at) != planned.scheduled_at:
                occurrence.scheduled_at = planned.scheduled_at
                await occurrence.save(using_db=connection, update_fields=["scheduled_at"])

        deleted_ids = [
            occurrence.id
            for key, occurrence in existing_by_key.items()
            if key not in desired_by_key
        ]
        if deleted_ids:
            await CustomChallengeOccurrence.filter(id__in=deleted_ids).using_db(connection).delete()

        new_goals = [
            goal
            for key, goal in desired_by_key.items()
            if key not in existing_by_key
        ]
        if new_goals:
            await CustomChallengeOccurrence.bulk_create(
                [
                    CustomChallengeOccurrence(
                        target_id=target_id,
                        scheduled_date=goal.scheduled_date,
                        slot=goal.slot,
                        scheduled_at=goal.scheduled_at,
                    )
                    for goal in new_goals
                ],
                using_db=connection,
            )


def _database_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=config.TIMEZONE)
    return value.astimezone(config.TIMEZONE)
