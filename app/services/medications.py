import base64
from datetime import date, datetime, time, timedelta
from typing import cast

from tortoise.expressions import Q

from app.core import config
from app.core.exceptions import (
    InvalidDoseDateError,
    InvalidDoseDateRangeError,
    InvalidDoseSlotError,
    MedicationNoteNotFoundError,
    MedicationRecordForbiddenError,
    MedicationRecordNotFoundError,
)
from app.dtos.medications import (
    CareEpisodeAliasResponse,
    CreateMedicationNoteRequest,
    MedicationDoseResponse,
    MedicationMealTimes,
    MedicationNoteListResponse,
    MedicationNoteMedicationResponse,
    MedicationNoteResponse,
    MedicationOverview,
    MedicationOverviewItem,
    MedicationStart,
    SaveMedicationDoseRequest,
    UpdateMedicationNoteRequest,
)
from app.models.care import CareEpisode
from app.models.enums import CareEpisodeStatus, MealSlot
from app.models.medications import Medication, MedicationDose, MedicationNote
from app.models.users import User, UserSettings
from app.services.medication_period import medication_end_date, resolve_medication_overview_range

MAX_DOSE_HISTORY_DAYS = 366
UNKNOWN_DAYS = 1
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
    async def list_overviews(
        self,
        user: User,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> list[MedicationOverview]:
        today = datetime.now(config.TIMEZONE).date()
        resolved_from, resolved_to = resolve_medication_overview_range(from_date, to_date, today)
        episodes = (
            await CareEpisode.filter(
                user_id=user.id,
                status=CareEpisodeStatus.ACTIVE,
                source_ocr_job_id__isnull=False,
                medication_start_date__gte=resolved_from,
                medication_start_date__lte=resolved_to,
            )
            .prefetch_related("medications__slots")
            .order_by("-medication_start_date", "-id")
        )
        settings = await UserSettings.get_or_none(user_id=user.id)
        meal_times = self._meal_times(settings)

        overviews: list[MedicationOverview] = []
        for episode in episodes:
            medications = sorted(episode.medications, key=lambda medication: medication.id)  # type: ignore[attr-defined]
            if medications:
                overviews.append(self._overview(episode, medications, meal_times, today))
        return overviews

    async def list_doses(
        self,
        user: User,
        from_date: date,
        to_date: date,
    ) -> list[MedicationDoseResponse]:
        if from_date > to_date or (to_date - from_date).days + 1 > MAX_DOSE_HISTORY_DAYS:
            raise InvalidDoseDateRangeError()

        doses = await MedicationDose.filter(
            user_id=user.id,
            dose_date__gte=from_date,
            dose_date__lte=to_date,
        )
        ordered = sorted(doses, key=lambda dose: (dose.dose_date, SLOT_POSITION[dose.slot], dose.id))
        return [self._dose_response(dose) for dose in ordered]

    async def save_dose(self, user: User, request: SaveMedicationDoseRequest) -> MedicationDoseResponse:
        today = datetime.now(config.TIMEZONE).date()
        earliest = today - timedelta(days=MAX_DOSE_HISTORY_DAYS - 1)
        if request.date < earliest or request.date > today:
            raise InvalidDoseDateError()

        episode = await self._get_owned_episode(request.record_id, user)
        slot = self._parse_slot(request.slot)
        if request.taken:
            await MedicationDose.get_or_create(
                user_id=user.id,
                dose_date=request.date,
                slot=slot,
                care_episode_id=episode.id,
            )
        else:
            await MedicationDose.filter(
                user_id=user.id,
                dose_date=request.date,
                slot=slot,
                care_episode_id=episode.id,
            ).delete()
        return MedicationDoseResponse(
            date=request.date,
            slot=slot.value.lower(),
            taken=request.taken,
            record_id=episode.id,
        )

    async def cancel(self, user: User, record_id: int) -> None:
        episode = await self._get_episode(user, record_id)
        if episode.status == CareEpisodeStatus.CANCELLED:
            return
        episode.status = CareEpisodeStatus.CANCELLED
        episode.updated_at = datetime.now(config.TIMEZONE)
        await episode.save(update_fields=["status", "updated_at"])

    async def update_episode_alias(
        self,
        user: User,
        record_id: int,
        alias: str | None,
    ) -> CareEpisodeAliasResponse:
        """본인 처방의 표시 별칭만 변경한다.

        별칭은 OCR이 만든 ``title``과 별개의 사용자 표시 값이다. 소유자가 아닌 처방은
        존재 여부를 숨기기 위해 기존 취소 API와 달리 404로 처리한다.
        """
        episode = await self._get_owned_episode(record_id, user)
        normalized_alias = alias.strip() if alias is not None else None
        episode.alias = normalized_alias or None
        episode.updated_at = datetime.now(config.TIMEZONE)
        await episode.save(update_fields=["alias", "updated_at"])
        return CareEpisodeAliasResponse(alias=episode.alias)

    async def create_note(
        self,
        user: User,
        request: CreateMedicationNoteRequest,
    ) -> MedicationNoteResponse:
        episode = await self._get_owned_episode(request.care_episode_id, user)
        if request.medication_id is not None:
            await self._get_episode_medication(episode.id, request.medication_id)
        note = await MedicationNote.create(
            user_id=user.id,
            care_episode_id=episode.id,
            medication_id=request.medication_id,
            dosed_at=request.dosed_at,
            body=request.body,
        )
        return await self._note_response(note)

    async def list_notes_page(
        self,
        user: User,
        *,
        episode_id: int | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> MedicationNoteListResponse:
        query = MedicationNote.filter(user_id=user.id)
        if episode_id is not None:
            query = query.filter(care_episode_id=episode_id)
        total = await query.count()
        cursor_key = self._decode_note_cursor(cursor)
        if cursor_key is not None:
            cursor_dosed_at, cursor_id = cursor_key
            query = query.filter(
                Q(dosed_at__lt=cursor_dosed_at)
                | (Q(dosed_at=cursor_dosed_at) & Q(id__lt=cursor_id))
            )

        page = list(await query.order_by("-dosed_at", "-id").limit(limit + 1))
        has_next = len(page) > limit
        page = page[:limit]
        next_cursor = self._encode_note_cursor(page[-1]) if has_next and page else None
        return MedicationNoteListResponse(
            items=[await self._note_response(note) for note in page],
            total=total,
            next_cursor=next_cursor,
        )

    async def list_notes(
        self,
        user: User,
        *,
        episode_id: int | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> list[MedicationNoteResponse]:
        page = await self.list_notes_page(
            user,
            episode_id=episode_id,
            limit=limit,
            cursor=cursor,
        )
        return page.items

    async def get_note(self, user: User, note_id: int) -> MedicationNoteResponse:
        note = await self._get_owned_note(user, note_id)
        return await self._note_response(note)

    async def update_note(
        self,
        user: User,
        note_id: int,
        request: UpdateMedicationNoteRequest,
    ) -> MedicationNoteResponse:
        note = await self._get_owned_note(user, note_id)
        if "medication_id" in request.model_fields_set:
            if request.medication_id is not None:
                await self._get_episode_medication(note.care_episode_id, request.medication_id)
            note.medication_id = request.medication_id
        if "dosed_at" in request.model_fields_set:
            note.dosed_at = request.dosed_at
        if "body" in request.model_fields_set:
            note.body = request.body
        note.updated_at = datetime.now(config.TIMEZONE)
        await note.save(update_fields=["medication_id", "dosed_at", "body", "updated_at"])
        return await self._note_response(note)

    async def delete_note(self, user: User, note_id: int) -> None:
        note = await self._get_owned_note(user, note_id)
        await note.delete()

    @staticmethod
    async def _get_owned_episode(record_id: int, user: User) -> CareEpisode:
        episode = await CareEpisode.get_or_none(id=record_id)
        if episode is None or cast(int, episode.user_id) != user.id:  # type: ignore[attr-defined]
            raise MedicationRecordNotFoundError()
        return episode

    @staticmethod
    async def _get_episode_medication(episode_id: int, medication_id: int) -> Medication:
        medication = await Medication.get_or_none(id=medication_id, care_episode_id=episode_id)
        if medication is None:
            raise MedicationRecordNotFoundError()
        return medication

    @staticmethod
    async def _get_owned_note(user: User, note_id: int) -> MedicationNote:
        note = await MedicationNote.get_or_none(id=note_id, user_id=user.id)
        if note is None:
            raise MedicationNoteNotFoundError()
        return note

    @staticmethod
    async def _note_response(note: MedicationNote) -> MedicationNoteResponse:
        episode = await CareEpisode.get(id=note.care_episode_id)
        medications = await Medication.filter(care_episode_id=episode.id).order_by("id")
        available_medications = [
            MedicationNoteMedicationResponse(
                id=medication.id,
                name=medication.name,
                dose=medication.strength,
            )
            for medication in medications
        ]
        selected_medication = next(
            (medication for medication in available_medications if medication.id == note.medication_id),
            None,
        )
        return MedicationNoteResponse(
            id=note.id,
            care_episode_id=cast(int, note.care_episode_id),  # type: ignore[attr-defined]
            care_episode_title=episode.title,
            care_episode_alias=episode.alias,
            care_episode_start_date=episode.medication_start_date,
            care_episode_status=episode.status,
            available_medications=available_medications,
            medication_id=cast(int | None, note.medication_id),  # type: ignore[attr-defined]
            medication=selected_medication,
            dosed_at=note.dosed_at,
            body=note.body,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )

    @staticmethod
    def _encode_note_cursor(note: MedicationNote) -> str:
        value = f"{note.dosed_at.isoformat()}|{note.id}"
        return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")

    @staticmethod
    def _decode_note_cursor(cursor: str | None) -> tuple[datetime, int] | None:
        if not cursor:
            return None
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            value = base64.urlsafe_b64decode(padded.encode()).decode()
            dosed_at_value, note_id_value = value.rsplit("|", 1)
            dosed_at = datetime.fromisoformat(dosed_at_value)
            note_id = int(note_id_value)
            if note_id <= 0:
                return None
            return dosed_at, note_id
        except (ValueError, UnicodeDecodeError, base64.binascii.Error):
            return None

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
        if start_date is None:
            raise ValueError("Medication overview requires a start date")
        start_slot = episode.medication_start_slot or MealSlot.MORNING

        known_days = [medication.days for medication in medications if medication.days is not None]
        fallback_days = episode.medication_days or (max(known_days) if known_days else UNKNOWN_DAYS)

        items = [
            MedicationService._medication_item(medication, start_date, today, fallback_days)
            for medication in medications
        ]
        end_date = medication_end_date(episode, medications)
        overview = MedicationOverview(
            record_id=episode.id,
            document_image_url=(
                f"/api/v1/ocr/jobs/{episode.source_ocr_job_id}/image" if episode.source_ocr_job_id is not None else ""
            ),
            start=MedicationStart(date=start_date, slot=start_slot.value.lower()),
            end_date=end_date,
            days_remaining=max((end_date - today).days + 1, 0),
            is_finished=end_date < today,
            meal_times=meal_times,
            medications=items,
        )
        if episode.alias is not None:
            overview.alias = episode.alias
        return overview

    @staticmethod
    def _medication_item(
        medication: Medication,
        start_date: date,
        today: date,
        fallback_days: int,
    ) -> MedicationOverviewItem:
        until_complete = medication.days is None
        days = medication.days if medication.days is not None else fallback_days
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
            dose=medication.strength or "",
            days=days,
            days_remaining=None if as_needed else max((end_date - today).days + 1, 0),
            slots=slots,
            as_needed=as_needed,
            **({"until_complete": True} if until_complete else {}),
        )

    @staticmethod
    def _dose_response(dose: MedicationDose) -> MedicationDoseResponse:
        return MedicationDoseResponse(
            date=dose.dose_date,
            slot=dose.slot.value.lower(),
            taken=True,
            record_id=cast(int, dose.care_episode_id),  # type: ignore[attr-defined]
        )
