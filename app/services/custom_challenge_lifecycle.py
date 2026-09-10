from datetime import datetime
from decimal import Decimal

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.transactions import in_transaction

from app.core import config
from app.models.custom_challenges import (
    CustomChallengeOccurrence,
    CustomChallengeParticipation,
    CustomChallengeTarget,
)
from app.models.enums import ChallengeParticipationStatus, CustomChallengeType, MealSlot
from app.models.medications import MedicationDose
from app.models.supplement_nutrients import SupplementDose
from app.models.users import User

PERCENT_QUANTUM = Decimal("0.01")


class CustomChallengeLifecycleService:
    async def finalize_due(self, now: datetime | None = None) -> int:
        cutoff = self._aware(now or datetime.now(config.TIMEZONE))
        user_ids = await (
            CustomChallengeParticipation.filter(
                status=ChallengeParticipationStatus.ACTIVE,
                end_at__lte=cutoff,
            )
            .order_by("user_id")
            .distinct()
            .values_list("user_id", flat=True)
        )
        finalized = 0
        for user_id in user_ids:
            async with in_transaction() as connection:
                finalized += await self.finalize_due_for_user(
                    user_id=user_id,
                    now=cutoff,
                    connection=connection,
                )
        return finalized

    async def finalize_due_for_user(
        self,
        *,
        user_id: int,
        now: datetime,
        connection: BaseDBAsyncClient,
    ) -> int:
        cutoff = self._aware(now)
        locked_user = await User.filter(id=user_id).using_db(connection).select_for_update().first()
        if locked_user is None:
            return 0
        participations = await (
            CustomChallengeParticipation.filter(
                user_id=user_id,
                status=ChallengeParticipationStatus.ACTIVE,
                end_at__lte=cutoff,
            )
            .using_db(connection)
            .select_for_update()
            .order_by("end_at", "id")
        )
        for participation in participations:
            await self._finalize(participation, cutoff, connection)
        return len(participations)

    async def finalize_cancelled(
        self,
        participation: CustomChallengeParticipation,
        cancelled_at: datetime,
        connection: BaseDBAsyncClient,
    ) -> None:
        """Freeze an active participation after its owner and participation are locked."""
        await self._finalize(participation, cancelled_at, connection, cancelled=True)

    async def finalize_if_complete(
        self,
        participation: CustomChallengeParticipation,
        finalized_at: datetime,
        connection: BaseDBAsyncClient,
    ) -> bool:
        """Freeze a non-empty, fully complete active participation before its deadline."""
        if participation.status is not ChallengeParticipationStatus.ACTIVE:
            return False
        return await self._finalize(
            participation,
            finalized_at,
            connection,
            require_complete=True,
        )

    async def _finalize(
        self,
        participation: CustomChallengeParticipation,
        finalized_at: datetime,
        connection: BaseDBAsyncClient,
        *,
        cancelled: bool = False,
        require_complete: bool = False,
    ) -> bool:
        targets = await (
            CustomChallengeTarget.filter(participation_id=participation.id)
            .using_db(connection)
            .select_for_update()
            .order_by("id")
        )
        occurrences = (
            await CustomChallengeOccurrence.filter(target_id__in=[target.id for target in targets])
            .using_db(connection)
            .select_for_update()
            .order_by("id")
            if targets
            else []
        )
        completed_ids = await self._completed_occurrence_ids(
            participation,
            targets,
            occurrences,
            connection,
        )
        target_count = len(occurrences)
        completed_count = len(completed_ids)
        is_complete = not cancelled and target_count > 0 and completed_count == target_count
        if require_complete and not is_complete:
            return False

        for occurrence in occurrences:
            completed = occurrence.id in completed_ids
            if occurrence.is_completed != completed:
                occurrence.is_completed = completed
                await occurrence.save(using_db=connection, update_fields=["is_completed"])

        progress_rate = (
            (Decimal(completed_count) * Decimal(100) / Decimal(target_count)).quantize(PERCENT_QUANTUM)
            if target_count > 0
            else Decimal("0.00")
        )
        participation.target_count = target_count
        participation.completed_count = completed_count
        participation.progress_rate = progress_rate
        if cancelled:
            participation.status = ChallengeParticipationStatus.CANCELLED
        else:
            participation.status = (
                ChallengeParticipationStatus.COMPLETED if is_complete else ChallengeParticipationStatus.EXPIRED
            )
        participation.completed_at = finalized_at if is_complete else None
        participation.finalized_at = finalized_at
        await participation.save(
            using_db=connection,
            update_fields=[
                "target_count",
                "completed_count",
                "progress_rate",
                "status",
                "completed_at",
                "finalized_at",
            ],
        )
        return is_complete

    @staticmethod
    async def _completed_occurrence_ids(
        participation: CustomChallengeParticipation,
        targets: list[CustomChallengeTarget],
        occurrences: list[CustomChallengeOccurrence],
        connection: BaseDBAsyncClient,
    ) -> set[int]:
        if participation.challenge_type is CustomChallengeType.MEDICATION:
            source_to_target = {
                target.care_episode_id: target.id
                for target in targets
                if target.care_episode_id is not None
            }
            rows = await (
                MedicationDose.filter(
                    user_id=participation.user_id,
                    care_episode_id__in=source_to_target,
                )
                .using_db(connection)
                .values_list("care_episode_id", "dose_date", "slot")
            )
        elif participation.challenge_type is CustomChallengeType.SUPPLEMENT:
            source_to_target = {
                target.supplement_registration_id: target.id
                for target in targets
                if target.supplement_registration_id is not None
            }
            rows = await (
                SupplementDose.filter(
                    registration_id__in=source_to_target,
                    registration__user_id=participation.user_id,
                )
                .using_db(connection)
                .values_list("registration_id", "dose_date", "slot")
            )
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
    def _aware(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=config.TIMEZONE)
        return value.astimezone(config.TIMEZONE)


def _meal_slot(value: MealSlot | str) -> MealSlot:
    return value if isinstance(value, MealSlot) else MealSlot(value)
