from datetime import datetime
from typing import Any

import pytest

from ai_worker.domain.errors import MedicationNoteSummaryGenerationError
from ai_worker.llm.generators.medication_note_summary_generator import (
    MedicationNoteSummaryGenerator,
)
from ai_worker.schemas.medication_note_summary import (
    MedicationNoteEpisodeSummaryPayload,
    MedicationNoteSummaryEpisode,
    MedicationNoteSummaryNote,
    MedicationNoteSummaryNotePayload,
    MedicationNoteSummaryPayload,
    MedicationNoteSummaryScope,
    MedicationNoteSummarySelection,
)


class StaticSummaryClient:
    def __init__(self, payload: MedicationNoteSummaryPayload) -> None:
        self._payload = payload

    async def ainvoke(self, messages: Any) -> MedicationNoteSummaryPayload:
        del messages
        return self._payload


def _selection() -> MedicationNoteSummarySelection:
    return MedicationNoteSummarySelection(
        scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
        episodes=[
            MedicationNoteSummaryEpisode(
                care_episode_id=10,
                care_episode_alias="A병원 진료",
                medication_names=["타이레놀정"],
                notes=[
                    MedicationNoteSummaryNote(
                        medication_note_id=100,
                        dosed_at=datetime(2026, 9, 3, 9, 0),
                        body="두통이 지속됨",
                    ),
                ],
            ),
        ],
    )


def _payload(*, note_id: int = 100, summary: str = "두통이 지속된다고 기록함.") -> MedicationNoteSummaryPayload:
    return MedicationNoteSummaryPayload(
        episodes=[
            MedicationNoteEpisodeSummaryPayload(
                care_episode_id=10,
                note_summaries=[
                    MedicationNoteSummaryNotePayload(
                        medication_note_id=note_id,
                        summary=summary,
                    ),
                ],
                one_line_summary="두통이 지속된 증상을 기록함.",
            ),
        ],
    )


@pytest.mark.asyncio
async def test_generator_rejects_note_identifier_not_present_in_selection() -> None:
    generator = MedicationNoteSummaryGenerator(
        client=StaticSummaryClient(_payload(note_id=999)),
    )

    with pytest.raises(MedicationNoteSummaryGenerationError, match="메모 식별자"):
        await generator.generate(selection=_selection())


@pytest.mark.asyncio
async def test_generator_rejects_causal_claims_about_medication() -> None:
    generator = MedicationNoteSummaryGenerator(
        client=StaticSummaryClient(
            _payload(summary="약물 부작용으로 두통이 발생했다고 기록함."),
        ),
    )

    with pytest.raises(MedicationNoteSummaryGenerationError, match="인과"):
        await generator.generate(selection=_selection())
