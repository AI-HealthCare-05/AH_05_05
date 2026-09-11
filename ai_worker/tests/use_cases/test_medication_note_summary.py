from datetime import datetime

import pytest

from ai_worker.schemas.medication_chat import MedicationChatRequest, MedicationChatRoute
from ai_worker.schemas.medication_note_summary import (
    MedicationNoteEpisodeSummaryPayload,
    MedicationNoteSummaryEpisode,
    MedicationNoteSummaryNote,
    MedicationNoteSummaryNotePayload,
    MedicationNoteSummaryPayload,
    MedicationNoteSummaryScope,
    MedicationNoteSummarySelection,
)
from ai_worker.use_cases.medication_note_summary import MedicationNoteSummaryUseCase


class StaticSummaryProvider:
    def __init__(self, selection: MedicationNoteSummarySelection) -> None:
        self.selection = selection
        self.received_input: tuple[int, MedicationNoteSummaryScope] | None = None

    async def list_episodes(
        self,
        *,
        user_id: int,
        scope: MedicationNoteSummaryScope,
    ) -> MedicationNoteSummarySelection:
        self.received_input = (user_id, scope)
        return self.selection


class StaticSummaryGenerator:
    def __init__(self, payload: MedicationNoteSummaryPayload) -> None:
        self.payload = payload
        self.called = False

    async def generate(
        self,
        *,
        selection: MedicationNoteSummarySelection,
    ) -> MedicationNoteSummaryPayload:
        del selection
        self.called = True
        return self.payload


def _request() -> MedicationChatRequest:
    return MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="복약메모 정리해줘",
    )


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
                    )
                ],
            )
        ],
    )


def _payload() -> MedicationNoteSummaryPayload:
    return MedicationNoteSummaryPayload(
        episodes=[
            MedicationNoteEpisodeSummaryPayload(
                care_episode_id=10,
                note_summaries=[
                    MedicationNoteSummaryNotePayload(
                        medication_note_id=100,
                        summary="두통이 지속된다고 기록함.",
                    )
                ],
                one_line_summary="두통이 지속된 증상을 기록함.",
            )
        ]
    )


@pytest.mark.asyncio
async def test_summary_use_case_returns_assistant_result_without_rag_dependencies() -> None:
    provider = StaticSummaryProvider(_selection())
    generator = StaticSummaryGenerator(_payload())
    result = await MedicationNoteSummaryUseCase(
        provider=provider,
        generator=generator,
    ).execute(
        request=_request(),
        scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
        context_hash="a" * 64,
    )

    assert result.route is MedicationChatRoute.MEDICATION_NOTE_SUMMARY
    assert "💉 **과거 복약 정보 · A병원 진료**" in result.answer
    assert provider.received_input == (1, MedicationNoteSummaryScope.RECENT_SIX_MONTHS)
    assert generator.called is True


@pytest.mark.asyncio
async def test_summary_use_case_skips_llm_when_no_notes_exist() -> None:
    generator = StaticSummaryGenerator(_payload())
    result = await MedicationNoteSummaryUseCase(
        provider=StaticSummaryProvider(
            MedicationNoteSummarySelection(
                scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
            )
        ),
        generator=generator,
    ).execute(
        request=_request(),
        scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
        context_hash="a" * 64,
    )

    assert result.answer == "📝 최근 6개월 동안 기록된 복약메모가 없습니다."
    assert generator.called is False
