import time

from ai_worker.llm.assemblers.medication_note_summary_assembler import (
    MedicationNoteSummaryAssembler,
)
from ai_worker.llm.generators.medication_note_summary_generator import (
    MEDICATION_NOTE_SUMMARY_PROMPT_VERSION,
    MedicationNoteSummaryGenerator,
)
from ai_worker.observability.chat_tracer import ChatTracer, NoOpChatTracer
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_chat import (
    MedicationChatReasonCode,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
)
from ai_worker.schemas.medication_note_summary import (
    MedicationNoteSummaryProvider,
    MedicationNoteSummaryScope,
)

_MEDICATION_NOTE_SUMMARY_SCHEMA_VERSION = "medication-chat-result-v1"
_NO_RECENT_NOTES_ANSWER = "📝 최근 6개월 동안 기록된 복약메모가 없습니다."
_SUMMARY_UNAVAILABLE_ANSWER = "복약메모를 정리하지 못했습니다. 잠시 후 다시 시도해 주세요."


class MedicationNoteSummaryUseCase:
    """저장된 복약메모를 사실 중심의 일반 챗봇 답변으로 정리한다."""

    def __init__(
        self,
        *,
        provider: MedicationNoteSummaryProvider,
        generator: MedicationNoteSummaryGenerator,
        tracer: ChatTracer | None = None,
        assembler: MedicationNoteSummaryAssembler | None = None,
    ) -> None:
        self._provider = provider
        self._generator = generator
        self._tracer = tracer or NoOpChatTracer()
        self._assembler = assembler or MedicationNoteSummaryAssembler()

    async def execute(
        self,
        *,
        request: MedicationChatRequest,
        scope: MedicationNoteSummaryScope,
        context_hash: str | None,
    ) -> MedicationChatResult:
        started_at = time.perf_counter()
        async with self._tracer.span(
            "medication_note_summary.load",
            run_type="tool",
        ) as load_span:
            try:
                selection = await self._provider.list_episodes(
                    user_id=request.user_id,
                    scope=scope,
                )
            except Exception:
                load_span.end(
                    {
                        "scope": scope.value,
                        "status": "FAILED",
                        "duration_ms": round((time.perf_counter() - started_at) * 1000),
                    }
                )
                return self._result(
                    request=request,
                    context_hash=context_hash,
                    answer=_SUMMARY_UNAVAILABLE_ANSWER,
                    reason_code=MedicationChatReasonCode.MEDICATION_NOTE_SUMMARY_UNAVAILABLE,
                )
            load_span.end(
                {
                    "scope": scope.value,
                    "episode_count": len(selection.episodes),
                    "note_count": sum(len(episode.notes) for episode in selection.episodes),
                    "has_more_episodes": selection.has_more_episodes,
                    "status": "COMPLETED",
                    "duration_ms": round((time.perf_counter() - started_at) * 1000),
                }
            )

        if not selection.episodes:
            return self._result(
                request=request,
                context_hash=context_hash,
                answer=_NO_RECENT_NOTES_ANSWER,
                reason_code=MedicationChatReasonCode.MEDICATION_NOTE_SUMMARY_REQUESTED,
            )

        generate_started_at = time.perf_counter()
        async with self._tracer.span(
            "medication_note_summary.generate",
            run_type="chain",
        ) as generate_span:
            try:
                payload = await self._generator.generate(selection=selection)
                answer = self._assembler.assemble(
                    selection=selection,
                    payload=payload,
                )
            except Exception:
                generate_span.end(
                    {
                        "episode_count": len(selection.episodes),
                        "status": "FAILED",
                        "duration_ms": round((time.perf_counter() - generate_started_at) * 1000),
                    }
                )
                return self._result(
                    request=request,
                    context_hash=context_hash,
                    answer=_SUMMARY_UNAVAILABLE_ANSWER,
                    reason_code=MedicationChatReasonCode.MEDICATION_NOTE_SUMMARY_UNAVAILABLE,
                )
            generate_span.end(
                {
                    "episode_count": len(selection.episodes),
                    "note_count": sum(len(episode.notes) for episode in selection.episodes),
                    "status": "COMPLETED",
                    "duration_ms": round((time.perf_counter() - generate_started_at) * 1000),
                }
            )

        return self._result(
            request=request,
            context_hash=context_hash,
            answer=answer,
            reason_code=MedicationChatReasonCode.MEDICATION_NOTE_SUMMARY_REQUESTED,
        )

    @staticmethod
    def _result(
        *,
        request: MedicationChatRequest,
        context_hash: str | None,
        answer: str,
        reason_code: MedicationChatReasonCode,
    ) -> MedicationChatResult:
        return MedicationChatResult(
            request_id=request.request_id,
            answer=answer,
            route=MedicationChatRoute.MEDICATION_NOTE_SUMMARY,
            safety_status=SafetyStatus.SAFE,
            safety_reason_codes=[reason_code.value],
            prompt_version=MEDICATION_NOTE_SUMMARY_PROMPT_VERSION,
            schema_version=_MEDICATION_NOTE_SUMMARY_SCHEMA_VERSION,
            context_hash=context_hash,
        )
