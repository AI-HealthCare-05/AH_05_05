from datetime import datetime, time, timedelta

from fastapi import HTTPException, status
from tortoise.transactions import in_transaction

from app.core import config
from app.dtos.medication_schedule import (
    MedicationMealTimesResponse,
    MedicationScheduleResponse,
    MedicationScheduleSaveRequest,
    MedicationScheduleSaveResponse,
    MedicationStartResponse,
    ScheduledMedicationResponse,
)
from app.models.care import CareEpisode
from app.models.enums import MealSlot
from app.models.medications import Medication, MedicationSlot
from app.models.users import User, UserSettings


def _slot_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw).lower()


def _format_clock(value: time | timedelta) -> str:
    if isinstance(value, time):
        return value.strftime("%H:%M")
    total_minutes = int(value.total_seconds() // 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours % 24:02d}:{minutes:02d}"


class MedicationScheduleService:
    async def get_schedule(self, user: User, record_id: int) -> MedicationScheduleResponse:
        episode = await CareEpisode.filter(id=record_id, user_id=user.id).first()
        if episode is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="복약 기록을 찾지 못했어요.")

        medications = await Medication.filter(care_episode_id=episode.id).order_by("id")
        medication_ids = [medication.id for medication in medications]
        slot_rows = (
            await MedicationSlot.filter(medication_id__in=medication_ids).order_by("id") if medication_ids else []
        )
        slots_by_medication: dict[int, list[str]] = {}
        for row in slot_rows:
            slots_by_medication.setdefault(row.medication_id, []).append(_slot_value(row.slot))

        settings = await UserSettings.get_or_none(user_id=user.id)
        meal_times = None
        if settings is not None:
            meal_times = MedicationMealTimesResponse(
                morning=_format_clock(settings.morning_medication_time),
                lunch=_format_clock(settings.lunch_medication_time),
                evening=_format_clock(settings.evening_medication_time),
                bedtime=_format_clock(settings.bedtime_medication_time),
            )

        start = None
        if episode.medication_start_date is not None and episode.medication_start_slot is not None:
            start = MedicationStartResponse(
                date=episode.medication_start_date,
                slot=_slot_value(episode.medication_start_slot),
            )

        return MedicationScheduleResponse(
            start=start,
            meal_times=meal_times,
            medications=[
                ScheduledMedicationResponse(
                    medication_id=medication.id,
                    name=medication.name,
                    dose=medication.dose or "",
                    times_per_day=medication.times_per_day,
                    timing=medication.administration or "",
                    slots=slots_by_medication.get(medication.id, []),
                )
                for medication in medications
            ],
        )

    async def save_schedule(
        self,
        user: User,
        request: MedicationScheduleSaveRequest,
    ) -> MedicationScheduleSaveResponse:
        async with in_transaction() as connection:
            episode = await (
                CareEpisode.filter(id=request.record_id, user_id=user.id)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            if episode is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="복약 기록을 찾지 못했어요.",
                )

            medications = await Medication.filter(care_episode_id=episode.id).using_db(connection)
            regular = {medication.id: medication for medication in medications if medication.times_per_day is not None}
            submitted = {item.medication_id: item for item in request.medications}
            if set(submitted) != set(regular):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="이 복약 기록의 정기약 전체 시간을 다시 확인해주세요.",
                )

            settings, _ = await UserSettings.get_or_create(user_id=user.id, using_db=connection)
            settings.morning_medication_time = time.fromisoformat(request.meal_times.morning)
            settings.lunch_medication_time = time.fromisoformat(request.meal_times.lunch)
            settings.evening_medication_time = time.fromisoformat(request.meal_times.evening)
            settings.bedtime_medication_time = time.fromisoformat(request.meal_times.bedtime)
            await settings.save(
                using_db=connection,
                update_fields=[
                    "morning_medication_time",
                    "lunch_medication_time",
                    "evening_medication_time",
                    "bedtime_medication_time",
                ],
            )

            episode.medication_start_date = request.start.date
            episode.medication_start_slot = MealSlot(request.start.slot.upper())
            prescribed_days = [medication.days for medication in medications if medication.days is not None]
            if prescribed_days:
                end_date = request.start.date + timedelta(days=max(prescribed_days) - 1)
                end_at = datetime.combine(end_date, time.max, tzinfo=config.TIMEZONE)
                # 과거 약봉투를 뒤늦게 등록할 수 있다. 이때 복약 종료일은 care episode가
                # 생성된 시각보다 앞서므로 started_at 이후만 허용하는 DB 제약에 넣지 않는다.
                # 복약 화면의 종료일은 medication_start_date + medications.days로 계산한다.
                care_end_at = end_at if end_at >= episode.started_at else None
                episode.default_end_at = care_end_at
                episode.planned_end_at = care_end_at
            await episode.save(
                using_db=connection,
                update_fields=[
                    "medication_start_date",
                    "medication_start_slot",
                    "default_end_at",
                    "planned_end_at",
                ],
            )

            medication_ids = [medication.id for medication in medications]
            if medication_ids:
                await MedicationSlot.filter(medication_id__in=medication_ids).using_db(connection).delete()
            for item in request.medications:
                for slot in item.slots:
                    await MedicationSlot.create(
                        using_db=connection,
                        medication_id=item.medication_id,
                        slot=MealSlot(slot.upper()),
                    )

        return MedicationScheduleSaveResponse(saved=True)
