from datetime import date, datetime, time, timedelta
from typing import cast

from app.core import config
from app.core.exceptions import (
    InvalidDoseDateError,
    InvalidDoseDateRangeError,
    InvalidDoseSlotError,
    MedicationRecordForbiddenError,
    MedicationRecordNotFoundError,
)
from app.dtos.medications import (
    MedicationDoseResponse,
    MedicationMealTimes,
    MedicationOverview,
    MedicationOverviewItem,
    MedicationStart,
    SaveMedicationDoseRequest,
)
from app.models.care import CareEpisode
from app.models.enums import CareEpisodeStatus, MealSlot
from app.models.medications import Medication, MedicationDose
from app.models.users import User, UserSettings

MAX_DOSE_HISTORY_DAYS = 93
SLOT_ORDER = (MealSlot.MORNING, MealSlot.LUNCH, MealSlot.EVENING, MealSlot.BEDTIME)
SLOT_BY_API_NAME = {slot.value.lower(): slot for slot in SLOT_ORDER}
SLOT_POSITION = {slot: position for position, slot in enumerate(SLOT_ORDER)}
DEFAULT_MEAL_TIMES = {
    MealSlot.MORNING: time(8, 0),
    MealSlot.LUNCH: time(13, 0),
    MealSlot.EVENING: time(19, 0),
    MealSlot.BEDTIME: time(22, 0),
}


class MedicationService:
    async def list_overviews(self, user: User) -> list[MedicationOverview]:
        episodes = await CareEpisode.filter(
            user_id=user.id,
            status=CareEpisodeStatus.ACTIVE,
            source_ocr_job_id__isnull=False,
            medication_start_date__isnull=False,
            medication_start_slot__isnull=False,
        ).prefetch_related("medications__slots").order_by("id")
        settings = await UserSettings.get_or_none(user_id=user.id)
        meal_times = self._meal_times(settings)
        today = datetime.now(config.TIMEZONE).date()

        overviews: list[MedicationOverview] = []
        for episode in episodes:
            medications = sorted(episode.medications, key=lambda medication: medication.id)  # type: ignore[attr-defined]
            if medications:
                overviews.append(self._overview(episode, medications, meal_times, today))
        return overviews

    async def list_doses(
        self,
        user: User,
        record_id: int,
        from_date: date,
        to_date: date,
    ) -> list[MedicationDoseResponse]:
        episode = await self._get_episode(user, record_id)
        if from_date > to_date or (to_date - from_date).days + 1 > MAX_DOSE_HISTORY_DAYS:
            raise InvalidDoseDateRangeError()

        doses = await MedicationDose.filter(
            user_id=user.id,
            care_episode_id=episode.id,
            dose_date__gte=from_date,
            dose_date__lte=to_date,
        )
        ordered = sorted(doses, key=lambda dose: (dose.dose_date, SLOT_POSITION[dose.slot], dose.id))
        return [self._dose_response(dose) for dose in ordered]

    async def save_dose(self, user: User, request: SaveMedicationDoseRequest) -> MedicationDoseResponse:
        episode = await self._get_episode(user, request.record_id)
        slot = self._parse_slot(request.slot)
        today = datetime.now(config.TIMEZONE).date()
        if (
            episode.medication_start_date is None
            or request.date < episode.medication_start_date
            or request.date > today
        ):
            raise InvalidDoseDateError()

        if request.taken:
            await MedicationDose.get_or_create(
                user_id=user.id,
                care_episode_id=episode.id,
                dose_date=request.date,
                slot=slot,
            )
        else:
            await MedicationDose.filter(
                user_id=user.id,
                care_episode_id=episode.id,
                dose_date=request.date,
                slot=slot,
            ).delete()
        return MedicationDoseResponse(
            record_id=episode.id,
            date=request.date,
            slot=slot.value.lower(),
            taken=request.taken,
        )

    @staticmethod
    async def _get_episode(user: User, record_id: int) -> CareEpisode:
        episode = await CareEpisode.get_or_none(id=record_id)
        if episode is None:
            raise MedicationRecordNotFoundError()
        if cast(int, episode.user_id) != user.id:  # type: ignore[attr-defined]
            raise MedicationRecordForbiddenError()
        return episode

    @staticmethod
    def _parse_slot(value: str) -> MealSlot:
        slot = SLOT_BY_API_NAME.get(value)
        if slot is None:
            raise InvalidDoseSlotError()
        return slot

    @staticmethod
    def _meal_times(settings: UserSettings | None) -> MedicationMealTimes:
        values = (
            DEFAULT_MEAL_TIMES
            if settings is None
            else {
                MealSlot.MORNING: settings.morning_medication_time,
                MealSlot.LUNCH: settings.lunch_medication_time,
                MealSlot.EVENING: settings.evening_medication_time,
                MealSlot.BEDTIME: settings.bedtime_medication_time,
            }
        )
        return MedicationMealTimes(
            morning=MedicationService._format_time(values[MealSlot.MORNING]),
            lunch=MedicationService._format_time(values[MealSlot.LUNCH]),
            evening=MedicationService._format_time(values[MealSlot.EVENING]),
            bedtime=MedicationService._format_time(values[MealSlot.BEDTIME]),
        )

    @staticmethod
    def _format_time(value: time | timedelta) -> str:
        if isinstance(value, timedelta):
            value = (datetime.min + value).time()
        return value.strftime("%H:%M")

    @staticmethod
    def _overview(
        episode: CareEpisode,
        medications: list[Medication],
        meal_times: MedicationMealTimes,
        today: date,
    ) -> MedicationOverview:
        start_date = episode.medication_start_date
        start_slot = episode.medication_start_slot
        if start_date is None or start_slot is None:
            raise ValueError("Medication overview requires a saved start point")

        items = [MedicationService._medication_item(episode, medication, start_date, today) for medication in medications]
        longest_days = max(item.days for item in items)
        end_date = start_date + timedelta(days=longest_days - 1)
        return MedicationOverview(
            record_id=episode.id,
            document_image_url=(
                f"/api/v1/ocr/jobs/{episode.source_ocr_job_id}/image" if episode.source_ocr_job_id is not None else ""
            ),
            start=MedicationStart(date=start_date, slot=start_slot.value.lower()),
            end_date=end_date,
            days_remaining=max((end_date - today).days + 1, 0),
            meal_times=meal_times,
            medications=items,
        )

    @staticmethod
    def _medication_item(
        episode: CareEpisode,
        medication: Medication,
        start_date: date,
        today: date,
    ) -> MedicationOverviewItem:
        until_complete = medication.days is None
        days = medication.days
        if days is None:
            days = episode.medication_days
        if days is None:
            raise ValueError("Medication days require a care episode fallback")
        as_needed = medication.times_per_day is None
        end_date = start_date + timedelta(days=days - 1)
        slots = (
            []
            if as_needed
            else sorted(
                (slot.slot.value.lower() for slot in medication.slots),  # type: ignore[attr-defined]
                key=lambda value: SLOT_POSITION[SLOT_BY_API_NAME[value]],
            )
        )
        return MedicationOverviewItem(
            medication_id=medication.id,
            name=medication.name,
            dose=medication.dose or "",
            days=days,
            days_remaining=None if as_needed else max((end_date - today).days + 1, 0),
            slots=slots,
            as_needed=as_needed,
            **({"until_complete": True} if until_complete else {}),
        )

    @staticmethod
    def _dose_response(dose: MedicationDose) -> MedicationDoseResponse:
        return MedicationDoseResponse(
            record_id=cast(int, dose.care_episode_id),  # type: ignore[attr-defined]
            date=dose.dose_date,
            slot=dose.slot.value.lower(),
            taken=True,
        )
