from datetime import datetime, time, timedelta

from app.core import config
from app.dtos.medication_overview import (
    MedicationOverviewItemResponse,
    MedicationOverviewMealTimesResponse,
    MedicationOverviewResponse,
    MedicationOverviewStartResponse,
)
from app.models.care import CareEpisode
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


class MedicationOverviewService:
    async def list_overviews(self, user: User) -> list[MedicationOverviewResponse]:
        episodes = await (
            CareEpisode.filter(
                user_id=user.id,
                medication_start_date__not_isnull=True,
                medication_start_slot__not_isnull=True,
            )
            .exclude(status="CANCELLED")
            .order_by("-medication_start_date", "-id")
        )
        if not episodes:
            return []

        episode_ids = [episode.id for episode in episodes]
        medications = await Medication.filter(care_episode_id__in=episode_ids).order_by("id")
        if not medications:
            return []

        medication_ids = [medication.id for medication in medications]
        slot_rows = await MedicationSlot.filter(medication_id__in=medication_ids).order_by("id")
        slots_by_medication: dict[int, list[str]] = {}
        for row in slot_rows:
            slots_by_medication.setdefault(row.medication_id, []).append(_slot_value(row.slot))

        medications_by_episode: dict[int, list[Medication]] = {}
        for medication in medications:
            medications_by_episode.setdefault(medication.care_episode_id, []).append(medication)

        settings = await UserSettings.get_or_none(user_id=user.id)
        meal_times = MedicationOverviewMealTimesResponse(
            morning=_format_clock(settings.morning_medication_time) if settings else "08:00",
            lunch=_format_clock(settings.lunch_medication_time) if settings else "13:00",
            evening=_format_clock(settings.evening_medication_time) if settings else "19:00",
            bedtime=_format_clock(settings.bedtime_medication_time) if settings else "22:00",
        )
        today = datetime.now(config.TIMEZONE).date()
        result: list[MedicationOverviewResponse] = []

        for episode in episodes:
            episode_medications = medications_by_episode.get(episode.id, [])
            if not episode_medications:
                continue
            start_date = episode.medication_start_date
            start_slot = episode.medication_start_slot
            if start_date is None or start_slot is None:
                continue

            fallback_days = episode.medication_days or 1
            prescribed_days = [medication.days or fallback_days for medication in episode_medications]
            episode_days = max(prescribed_days)
            end_date = start_date + timedelta(days=episode_days - 1)

            result.append(
                MedicationOverviewResponse(
                    record_id=episode.id,
                    document_image_url="",
                    start=MedicationOverviewStartResponse(
                        date=start_date,
                        slot=_slot_value(start_slot),
                    ),
                    end_date=end_date,
                    days_remaining=max(0, (end_date - today).days),
                    meal_times=meal_times,
                    medications=[
                        MedicationOverviewItemResponse(
                            medication_id=medication.id,
                            name=medication.name,
                            dose=medication.dose or "",
                            days=medication.days or fallback_days,
                            days_remaining=max(
                                0,
                                (
                                    start_date
                                    + timedelta(days=(medication.days or fallback_days) - 1)
                                    - today
                                ).days,
                            ),
                            slots=slots_by_medication.get(medication.id, []),
                            as_needed=medication.times_per_day is None,
                        )
                        for medication in episode_medications
                    ],
                )
            )

        return result
