from collections.abc import Callable
from datetime import date, timedelta

from tortoise.timezone import now

from ai_worker.domain.errors import (
    PatientContextNotFoundError,
    UnconfirmedPatientContextError,
)
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    ActiveMedication,
    ActiveSupplement,
)
from app.models.care import CareEpisode
from app.models.enums import CareEpisodeStatus, SupplementStatus
from app.models.medications import Medication
from app.models.supplement_nutrients import UserSupplementNutrient


def _service_today() -> date:
    return now().date()


class DbActiveIntakeContextProvider:
    def __init__(
        self,
        *,
        today_provider: Callable[[], date] = _service_today,
    ) -> None:
        self._today_provider = today_provider

    async def get_active_context(
        self,
        *,
        user_id: int,
        care_episode_id: int | None,
    ) -> ActiveIntakeContext:
        if care_episode_id is not None:
            await self._validate_preferred_episode(
                user_id=user_id,
                care_episode_id=care_episode_id,
            )

        episodes = await CareEpisode.filter(
            user_id=user_id,
            status=CareEpisodeStatus.ACTIVE,
            confirmed_at__not_isnull=True,
        )
        episodes_by_id = {episode.id: episode for episode in episodes}
        medication_rows = (
            await Medication.filter(
                care_episode_id__in=episodes_by_id,
            )
            .prefetch_related("slots")
            .order_by("id")
        )
        supplement_rows = await UserSupplementNutrient.filter(
            user_id=user_id,
            status=SupplementStatus.ACTIVE,
            supplement_nutrient_id__isnull=False,
        ).prefetch_related("supplement_nutrient", "slots")

        today = self._today_provider()
        medications = [
            self._to_active_medication(row)
            for row in medication_rows
            if self._is_current_medication(
                row,
                episode=episodes_by_id[row.care_episode_id],
                today=today,
            )
        ]
        supplements = [
            self._to_active_supplement(row)
            for row in supplement_rows
            if row.start_date <= today and (row.end_date is None or row.end_date >= today)
        ]

        return ActiveIntakeContext(
            user_id=user_id,
            preferred_care_episode_id=care_episode_id,
            medications=medications,
            supplements=supplements,
        )

    @staticmethod
    async def _validate_preferred_episode(
        *,
        user_id: int,
        care_episode_id: int,
    ) -> None:
        episode = await CareEpisode.filter(
            id=care_episode_id,
            user_id=user_id,
        ).first()
        if episode is None:
            raise PatientContextNotFoundError("요청한 사용자의 케어 에피소드를 찾을 수 없습니다.")
        if episode.confirmed_at is None or not episode.confirmation_hash:
            raise UnconfirmedPatientContextError("사용자가 확인하고 저장한 확정 복약정보가 아닙니다.")

    @staticmethod
    def _is_current_medication(
        medication: Medication,
        *,
        episode: CareEpisode,
        today: date,
    ) -> bool:
        start_date = episode.medication_start_date or medication.prescribed_at
        if start_date is None:
            return True
        if start_date > today:
            return False
        days = medication.days or episode.medication_days
        if days is None:
            return True
        last_day = start_date + timedelta(days=days - 1)
        return last_day >= today

    @staticmethod
    def _to_active_medication(
        medication: Medication,
    ) -> ActiveMedication:
        return ActiveMedication(
            medication_id=medication.id,
            care_episode_id=medication.care_episode_id,
            name=medication.name,
            dose=medication.dose_quantity,
            times_per_day=medication.times_per_day,
            days=medication.days,
            prescribed_at=medication.prescribed_at,
            scheduled_slots=sorted(slot.slot.value for slot in medication.slots),
        )

    @staticmethod
    def _to_active_supplement(
        registration: UserSupplementNutrient,
    ) -> ActiveSupplement:
        return ActiveSupplement(
            registration_id=registration.id,
            supplement_nutrient_id=registration.supplement_nutrient_id,
            name=registration.supplement_nutrient.name,
            dose_amount=str(registration.dose_amount),
            dose_unit=registration.dose_unit,
            start_date=registration.start_date,
            end_date=registration.end_date,
            note=registration.note,
            scheduled_slots=sorted(slot.slot.value for slot in registration.slots),
        )
