from contextlib import asynccontextmanager
from datetime import datetime

import pytest

from ai_worker.schemas.medication_chat import MedicationChatRequest
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


class RecordingSpan:
    trace_id = None

    def __init__(self, name: str, inputs, metadata) -> None:
        self.name = name
        self.inputs = inputs
        self.metadata = metadata
        self.outputs = None

    def end(self, outputs=None) -> None:
        self.outputs = outputs


class RecordingChatTracer:
    capture_content = False

    def __init__(self) -> None:
        self.spans: list[RecordingSpan] = []

    @asynccontextmanager
    async def span(self, name, *, inputs=None, metadata=None, **kwargs):
        del kwargs
        span = RecordingSpan(name, inputs, metadata)
        self.spans.append(span)
        yield span

    def anonymize_identifier(self, value):
        del value
        return None

    async def aclose(self) -> None:
        return None


class ScopeRecordingProvider:
    def __init__(self, selections: dict[MedicationNoteSummaryScope, MedicationNoteSummarySelection]) -> None:
        self._selections = selections
        self.scopes: list[MedicationNoteSummaryScope] = []

    async def list_episodes(self, *, user_id: int, scope: MedicationNoteSummaryScope):
        del user_id
        self.scopes.append(scope)
        return self._selections[scope]


class SummaryGenerator:
    async def generate(self, *, selection: MedicationNoteSummarySelection) -> MedicationNoteSummaryPayload:
        return MedicationNoteSummaryPayload(
            episodes=[
                MedicationNoteEpisodeSummaryPayload(
                    care_episode_id=episode.care_episode_id,
                    note_summaries=[
                        MedicationNoteSummaryNotePayload(
                            medication_note_id=note.medication_note_id,
                            summary=f"기록 {episode.care_episode_id}을 정리함.",
                        )
                        for note in episode.notes
                    ],
                    one_line_summary=f"진료 {episode.care_episode_id}의 기록을 정리함.",
                )
                for episode in selection.episodes
            ]
        )


def _request(question: str = "복약메모 정리해줘") -> MedicationChatRequest:
    return MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question=question,
    )


def _episode(index: int, *, body: str = "민감 메모 본문") -> MedicationNoteSummaryEpisode:
    return MedicationNoteSummaryEpisode(
        care_episode_id=index,
        care_episode_alias=f"{chr(64 + index)}병원 진료",
        medication_names=[f"약 {index}"],
        notes=[
            MedicationNoteSummaryNote(
                medication_note_id=index * 10,
                dosed_at=datetime(2026, 9, index, 9, 0),
                body=body,
            )
        ],
    )


@pytest.mark.asyncio
async def test_default_summary_has_three_episode_cap_and_exact_notice() -> None:
    provider = ScopeRecordingProvider(
        {
            MedicationNoteSummaryScope.RECENT_SIX_MONTHS: MedicationNoteSummarySelection(
                scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
                episodes=[_episode(1), _episode(2), _episode(3)],
                has_more_episodes=True,
            ),
            MedicationNoteSummaryScope.ALL_HISTORY: MedicationNoteSummarySelection(
                scope=MedicationNoteSummaryScope.ALL_HISTORY,
            ),
        }
    )
    result = await MedicationNoteSummaryUseCase(
        provider=provider,
        generator=SummaryGenerator(),
    ).execute(
        request=_request(),
        scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
        context_hash="a" * 64,
    )

    assert result.answer.count("💉 **과거 복약 정보 ·") == 3
    assert "📌 최근 3건의 진료 기록만 정리했습니다. 이전 진료 기록도 필요하면 말씀해 주세요." in result.answer
    assert provider.scopes == [MedicationNoteSummaryScope.RECENT_SIX_MONTHS]


@pytest.mark.asyncio
async def test_all_history_summary_does_not_add_recent_three_notice() -> None:
    provider = ScopeRecordingProvider(
        {
            MedicationNoteSummaryScope.RECENT_SIX_MONTHS: MedicationNoteSummarySelection(
                scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
            ),
            MedicationNoteSummaryScope.ALL_HISTORY: MedicationNoteSummarySelection(
                scope=MedicationNoteSummaryScope.ALL_HISTORY,
                episodes=[_episode(1), _episode(2), _episode(3), _episode(4)],
            ),
        }
    )
    result = await MedicationNoteSummaryUseCase(
        provider=provider,
        generator=SummaryGenerator(),
    ).execute(
        request=_request("전체 복약메모를 정리해줘"),
        scope=MedicationNoteSummaryScope.ALL_HISTORY,
        context_hash="a" * 64,
    )

    assert result.answer.count("💉 **과거 복약 정보 ·") == 4
    assert "최근 3건의 진료 기록만 정리했습니다" not in result.answer
    assert provider.scopes == [MedicationNoteSummaryScope.ALL_HISTORY]


@pytest.mark.asyncio
async def test_trace_does_not_include_note_body_when_content_capture_is_disabled() -> None:
    tracer = RecordingChatTracer()
    selection = MedicationNoteSummarySelection(
        scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
        episodes=[_episode(1, body="민감 메모 본문")],
    )
    await MedicationNoteSummaryUseCase(
        provider=ScopeRecordingProvider(
            {
                MedicationNoteSummaryScope.RECENT_SIX_MONTHS: selection,
                MedicationNoteSummaryScope.ALL_HISTORY: selection,
            }
        ),
        generator=SummaryGenerator(),
        tracer=tracer,
    ).execute(
        request=_request(),
        scope=MedicationNoteSummaryScope.RECENT_SIX_MONTHS,
        context_hash="a" * 64,
    )

    assert [span.name for span in tracer.spans] == [
        "medication_note_summary.load",
        "medication_note_summary.generate",
    ]
    assert "민감 메모 본문" not in str(
        [(span.inputs, span.metadata, span.outputs) for span in tracer.spans]
    )
