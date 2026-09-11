from collections import defaultdict
from collections.abc import Callable
from datetime import date

from dateutil.relativedelta import relativedelta
from tortoise.timezone import now

from ai_worker.schemas.medication_note_summary import (
    MedicationNoteSummaryEpisode,
    MedicationNoteSummaryNote,
    MedicationNoteSummaryScope,
    MedicationNoteSummarySelection,
)
from app.models.enums import CareEpisodeStatus
from app.models.medications import MedicationNote

_RECENT_SCOPE_MONTHS = 6
_RECENT_SCOPE_EPISODE_LIMIT = 3
_INCLUDED_EPISODE_STATUSES = (
    CareEpisodeStatus.ACTIVE,
    CareEpisodeStatus.COMPLETED,
)


def _service_today() -> date:
    return now().date()


class DbMedicationNoteSummaryProvider:
    """사용자가 기록한 복약메모를 진료 건별 사실 데이터로 읽는다."""

    def __init__(
        self,
        *,
        today_provider: Callable[[], date] = _service_today,
    ) -> None:
        self._today_provider = today_provider

    async def list_episodes(
        self,
        *,
        user_id: int,
        scope: MedicationNoteSummaryScope,
    ) -> MedicationNoteSummarySelection:
        filters: dict[str, object] = {
            "user_id": user_id,
            "care_episode__status__in": _INCLUDED_EPISODE_STATUSES,
        }
        if scope is MedicationNoteSummaryScope.RECENT_SIX_MONTHS:
            filters["dosed_at__gte"] = self._today_provider() - relativedelta(
                months=_RECENT_SCOPE_MONTHS,
            )

        notes = await (
            MedicationNote.filter(**filters)
            .prefetch_related("care_episode__medications", "medication")
            .order_by("-dosed_at", "-id")
        )
        grouped_notes: dict[int, list[MedicationNote]] = defaultdict(list)
        for note in notes:
            grouped_notes[note.care_episode_id].append(note)

        episodes = [self._to_episode(group_notes) for group_notes in grouped_notes.values()]
        episodes.sort(
            key=lambda episode: max(note.dosed_at for note in episode.notes),
            reverse=True,
        )

        if scope is MedicationNoteSummaryScope.ALL_HISTORY:
            return MedicationNoteSummarySelection(
                scope=scope,
                episodes=episodes,
            )

        return MedicationNoteSummarySelection(
            scope=scope,
            episodes=episodes[:_RECENT_SCOPE_EPISODE_LIMIT],
            has_more_episodes=len(episodes) > _RECENT_SCOPE_EPISODE_LIMIT,
        )

    @staticmethod
    def _to_episode(
        notes: list[MedicationNote],
    ) -> MedicationNoteSummaryEpisode:
        first_note = notes[0]
        care_episode = first_note.care_episode
        medications = sorted(
            care_episode.medications,
            key=lambda medication: medication.id,
        )
        ordered_notes = sorted(
            notes,
            key=lambda note: (note.dosed_at, note.id),
        )
        return MedicationNoteSummaryEpisode(
            care_episode_id=care_episode.id,
            care_episode_alias=care_episode.alias,
            hospital_name=care_episode.hospital_name,
            medication_names=[medication.name for medication in medications],
            notes=[
                MedicationNoteSummaryNote(
                    medication_note_id=note.id,
                    dosed_at=note.dosed_at,
                    body=note.body,
                    medication_name=(note.medication.name if note.medication is not None else None),
                )
                for note in ordered_notes
            ],
        )
