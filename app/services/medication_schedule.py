import re
from datetime import date, datetime, time, timedelta

from tortoise.backends.base.client import BaseDBAsyncClient
from tortoise.transactions import in_transaction

from app.core import config
from app.core.exceptions import (
    InvalidMedicationScheduleError,
    MedicationScheduleFinishedError,
    MedicationScheduleNotFoundError,
)
from app.dtos.medication_schedule import (
    MedicationScheduleMealTimes,
    MedicationScheduleMedication,
    MedicationScheduleResponse,
    MedicationScheduleStart,
    SaveMedicationScheduleRequest,
)
from app.models.alarms import Alarm
from app.models.care import CareEpisode
from app.models.enums import AlarmStatus, AlarmType, CareEpisodeStatus, MealSlot
from app.models.medications import Medication, MedicationSlot
from app.models.users import User, UserSettings
from app.services.medication_period import medication_end_date

SLOT_ORDER = (MealSlot.MORNING, MealSlot.LUNCH, MealSlot.EVENING, MealSlot.BEDTIME)
SLOT_BY_NAME = {
    "morning": MealSlot.MORNING,
    "lunch": MealSlot.LUNCH,
    "evening": MealSlot.EVENING,
    "bedtime": MealSlot.BEDTIME,
}
SLOT_TIME_FIELDS = {
    MealSlot.MORNING: "morning_medication_time",
    MealSlot.LUNCH: "lunch_medication_time",
    MealSlot.EVENING: "evening_medication_time",
    MealSlot.BEDTIME: "bedtime_medication_time",
}
TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MEDICATION_ALARM_TITLE = "복약 알림"
MEDICATION_ALARM_MESSAGE = "약을 복용할 시간입니다."


class MedicationScheduleService:
    async def get(self, user: User, record_id: int) -> MedicationScheduleResponse:
        episode = await CareEpisode.filter(id=record_id, user_id=user.id).first()
        if episode is None:
            raise MedicationScheduleNotFoundError()

        medications = await Medication.filter(care_episode_id=episode.id).prefetch_related("slots").order_by("id")
        start = self._start_response(episode)
        settings = await UserSettings.get_or_none(user_id=user.id)
        return MedicationScheduleResponse(
            start=start,
            meal_times=self._meal_times_response(settings) if settings is not None else None,
            medications=[self._medication_response(medication) for medication in medications],
        )

    async def save(self, user: User, record_id: int, request: SaveMedicationScheduleRequest) -> None:
        start_date, start_slot, meal_times, assignments = self._validate_request(request)
        async with in_transaction() as connection:
            locked_user = await User.filter(id=user.id).using_db(connection).select_for_update().first()
            if locked_user is None:
                raise MedicationScheduleNotFoundError()
            episode = (
                await CareEpisode.filter(id=record_id, user_id=user.id).using_db(connection).select_for_update().first()
            )
            if episode is None:
                raise MedicationScheduleNotFoundError()

            medications = await Medication.filter(care_episode_id=episode.id).using_db(connection).order_by("id")
            if medication_end_date(episode, medications) < datetime.now(config.TIMEZONE).date():
                raise MedicationScheduleFinishedError()

            medication_ids = {medication.id for medication in medications}
            scheduled_ids = {medication.id for medication in medications if medication.times_per_day is not None}
            assignment_ids = [assignment[0] for assignment in assignments]
            if len(assignment_ids) != len(set(assignment_ids)) or set(assignment_ids) != scheduled_ids:
                raise InvalidMedicationScheduleError()

            settings, _ = await UserSettings.get_or_create(user_id=user.id, using_db=connection)
            for slot, value in meal_times.items():
                setattr(settings, SLOT_TIME_FIELDS[slot], value)
            await settings.save(using_db=connection, update_fields=list(SLOT_TIME_FIELDS.values()))

            episode.medication_start_date = start_date
            episode.medication_start_slot = start_slot
            episode.updated_at = datetime.now(config.TIMEZONE)
            await episode.save(
                using_db=connection,
                update_fields=["medication_start_date", "medication_start_slot", "updated_at"],
            )

            await MedicationSlot.filter(medication_id__in=medication_ids).using_db(connection).delete()
            slot_rows = [
                MedicationSlot(medication_id=medication_id, slot=slot)
                for medication_id, slots in assignments
                for slot in slots
            ]
            if slot_rows:
                await MedicationSlot.bulk_create(slot_rows, using_db=connection)
            await self._sync_medication_alarms(user.id, meal_times, connection)

    @classmethod
    async def _sync_medication_alarms(
        cls,
        user_id: int,
        meal_times: dict[MealSlot, time],
        connection: BaseDBAsyncClient,
    ) -> None:
        now = datetime.now(config.TIMEZONE)
        medications = (
            await Medication.filter(
                care_episode__user_id=user_id,
                care_episode__status=CareEpisodeStatus.ACTIVE,
            )
            .using_db(connection)
            .prefetch_related("care_episode", "slots")
        )
        windows = cls._medication_windows(medications)
        existing = {
            alarm.meal_slot: alarm
            for alarm in await Alarm.filter(user_id=user_id, alarm_type=AlarmType.MEDICATION)
            .using_db(connection)
            .select_for_update()
        }

        for slot in SLOT_ORDER:
            await cls._sync_slot_alarm(
                user_id=user_id,
                slot=slot,
                alarm_time=meal_times[slot],
                windows=windows[slot],
                alarm=existing.get(slot),
                now=now,
                connection=connection,
            )

    @staticmethod
    def _medication_windows(
        medications: list[Medication],
    ) -> dict[MealSlot, list[tuple[date, date]]]:
        windows: dict[MealSlot, list[tuple[date, date]]] = {slot: [] for slot in SLOT_ORDER}
        for medication in medications:
            episode = medication.care_episode
            start_date = episode.medication_start_date
            start_slot = episode.medication_start_slot
            days = medication.days or episode.medication_days
            if start_date is None or start_slot is None or days is None:
                continue

            end_date = start_date + timedelta(days=days - 1)
            for medication_slot in medication.slots:
                slot = medication_slot.slot
                first_date = start_date
                if SLOT_ORDER.index(slot) < SLOT_ORDER.index(start_slot):
                    first_date += timedelta(days=1)
                if first_date <= end_date:
                    windows[slot].append((first_date, end_date))
        return windows

    @classmethod
    async def _sync_slot_alarm(
        cls,
        *,
        user_id: int,
        slot: MealSlot,
        alarm_time: time,
        windows: list[tuple[date, date]],
        alarm: Alarm | None,
        now: datetime,
        connection: BaseDBAsyncClient,
    ) -> None:
        schedule = cls._next_alarm_schedule(windows, alarm_time, now)
        if schedule is None:
            if alarm is not None and alarm.status != AlarmStatus.CANCELLED:
                alarm.status = AlarmStatus.CANCELLED
                alarm.cancelled_at = now
                alarm.updated_at = now
                await alarm.save(
                    using_db=connection,
                    update_fields=["status", "cancelled_at", "updated_at"],
                )
            return

        next_trigger_at, last_date = schedule
        occurrence_count = (last_date - next_trigger_at.date()).days + 1
        values = {
            "care_episode_id": None,
            "title": MEDICATION_ALARM_TITLE,
            "message": MEDICATION_ALARM_MESSAGE,
            "scheduled_at": next_trigger_at,
            "recurrence_rule": f"FREQ=DAILY;COUNT={occurrence_count}",
            "timezone": str(config.TIMEZONE),
            "next_trigger_at": next_trigger_at,
            "status": AlarmStatus.ACTIVE,
            "last_triggered_at": None,
            "completed_at": None,
            "cancelled_at": None,
            "updated_at": now,
        }
        if alarm is None:
            await Alarm.create(
                using_db=connection,
                user_id=user_id,
                alarm_type=AlarmType.MEDICATION,
                meal_slot=slot,
                **values,
            )
            return

        for field_name, value in values.items():
            setattr(alarm, field_name, value)
        await alarm.save(using_db=connection, update_fields=list(values))

    @staticmethod
    def _next_alarm_schedule(
        windows: list[tuple[date, date]],
        alarm_time: time,
        now: datetime,
    ) -> tuple[datetime, date] | None:
        candidates: list[tuple[datetime, date]] = []
        for first_date, last_date in windows:
            candidate_date = max(first_date, now.date())
            candidate = datetime.combine(candidate_date, alarm_time, tzinfo=config.TIMEZONE)
            if candidate <= now:
                candidate += timedelta(days=1)
            if candidate.date() <= last_date:
                candidates.append((candidate, last_date))
        if not candidates:
            return None
        return min(candidate for candidate, _ in candidates), max(last_date for _, last_date in candidates)

    @staticmethod
    def _start_response(episode: CareEpisode) -> MedicationScheduleStart | None:
        if episode.medication_start_date is None or episode.medication_start_slot is None:
            return None
        return MedicationScheduleStart(
            date=episode.medication_start_date.isoformat(),
            slot=episode.medication_start_slot.name.lower(),
        )

    @staticmethod
    def _meal_times_response(settings: UserSettings) -> MedicationScheduleMealTimes:
        return MedicationScheduleMealTimes(
            **{
                slot.name.lower(): MedicationScheduleService._format_time(getattr(settings, field_name))
                for slot, field_name in SLOT_TIME_FIELDS.items()
            }
        )

    @staticmethod
    def _medication_response(medication: Medication) -> MedicationScheduleMedication:
        slots = sorted(
            (slot.slot.name.lower() for slot in medication.slots),  # type: ignore[attr-defined]
            key=lambda slot: SLOT_ORDER.index(SLOT_BY_NAME[slot]),
        )
        return MedicationScheduleMedication(
            medication_id=medication.id,
            name=medication.name,
            dose=medication.strength or "",
            times_per_day=medication.times_per_day,
            timing=medication.administration or "",
            slots=slots,
        )

    @staticmethod
    def _validate_request(
        request: SaveMedicationScheduleRequest,
    ) -> tuple[date, MealSlot, dict[MealSlot, time], list[tuple[int, list[MealSlot]]]]:
        if not DATE_PATTERN.fullmatch(request.start.date):
            raise InvalidMedicationScheduleError()
        try:
            start_date = date.fromisoformat(request.start.date)
        except ValueError as error:
            raise InvalidMedicationScheduleError() from error
        if start_date > datetime.now(config.TIMEZONE).date():
            raise InvalidMedicationScheduleError()

        start_slot = SLOT_BY_NAME.get(request.start.slot)
        if start_slot is None:
            raise InvalidMedicationScheduleError()

        meal_times = {
            MealSlot.MORNING: request.meal_times.morning,
            MealSlot.LUNCH: request.meal_times.lunch,
            MealSlot.EVENING: request.meal_times.evening,
            MealSlot.BEDTIME: request.meal_times.bedtime,
        }
        parsed_times = {slot: MedicationScheduleService._parse_time(value) for slot, value in meal_times.items()}
        if any(
            parsed_times[first] >= parsed_times[second]
            for first, second in zip(SLOT_ORDER, SLOT_ORDER[1:], strict=False)
        ):
            raise InvalidMedicationScheduleError()

        assignments: list[tuple[int, list[MealSlot]]] = []
        for assignment in request.medications:
            slots = [SLOT_BY_NAME.get(slot) for slot in assignment.slots]
            if not slots or any(slot is None for slot in slots) or len(slots) != len(set(slots)):
                raise InvalidMedicationScheduleError()
            assignments.append((assignment.medication_id, [slot for slot in slots if slot is not None]))
        return start_date, start_slot, parsed_times, assignments

    @staticmethod
    def _parse_time(value: str) -> time:
        if not TIME_PATTERN.fullmatch(value):
            raise InvalidMedicationScheduleError()
        try:
            parsed = time.fromisoformat(value)
        except ValueError as error:
            raise InvalidMedicationScheduleError() from error
        if parsed.minute not in {0, 30}:
            raise InvalidMedicationScheduleError()
        return parsed

    @staticmethod
    def _format_time(value: time | timedelta) -> str:
        if isinstance(value, timedelta):
            value = (datetime.min + value).time()
        return value.strftime("%H:%M")
