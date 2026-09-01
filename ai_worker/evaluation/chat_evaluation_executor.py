import asyncio
import time
from collections.abc import Callable
from typing import Protocol
from uuid import uuid4

from ai_worker.observability.chat_tracer import ChatTracer
from ai_worker.rag.query_builders.medication_knowledge_query_builder import (
    MedicationKnowledgeQueryBuilder,
)
from ai_worker.schemas.chat_evaluation import (
    ChatEvaluationCase,
    ChatEvaluationObservation,
)
from ai_worker.schemas.medication_chat import (
    MedicationChatRequest,
    MedicationChatResult,
)


class MedicationChatAnswerService(Protocol):
    async def answer(
        self,
        request: MedicationChatRequest,
    ) -> MedicationChatResult: ...


class ChatCoreEvaluationExecutor:
    def __init__(
        self,
        *,
        core_service: MedicationChatAnswerService,
        tracer: ChatTracer,
        user_id: int,
        care_episode_id: int | None = None,
        timeout_seconds: float = 30.0,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._core_service = core_service
        self._tracer = tracer
        self._user_id = user_id
        self._care_episode_id = care_episode_id
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._query_builder = MedicationKnowledgeQueryBuilder()

    async def execute(
        self,
        case: ChatEvaluationCase,
    ) -> ChatEvaluationObservation:
        query_plan = self._query_builder.build(case.question)
        inputs = (
            {"question": case.question} if self._tracer.capture_content else {"question_length": len(case.question)}
        )
        started_at = self._clock()
        async with self._tracer.span(
            "chat.evaluation.case",
            root=True,
            inputs=inputs,
            metadata={
                "query_id": case.query_id,
                "category": case.category.value,
            },
        ) as root_span:
            try:
                async with asyncio.timeout(self._timeout_seconds):
                    result = await self._core_service.answer(
                        MedicationChatRequest(
                            request_id=uuid4(),
                            user_id=self._user_id,
                            care_episode_id=self._care_episode_id,
                            question=case.question,
                        )
                    )
            except TimeoutError:
                elapsed_ms = self._elapsed_ms(started_at)
                root_span.end(
                    {
                        "status": "TIMEOUT",
                        "error_code": "API_TIMEOUT",
                    }
                )
                return ChatEvaluationObservation(
                    query_id=case.query_id,
                    normalized_entities=query_plan.entity_names,
                    section_types=query_plan.section_types,
                    response_time_ms=elapsed_ms,
                    langsmith_trace_id=root_span.trace_id,
                    error_code="API_TIMEOUT",
                )
            except Exception as error:
                elapsed_ms = self._elapsed_ms(started_at)
                error_code = getattr(error, "code", type(error).__name__)
                root_span.end(
                    {
                        "status": "FAILED",
                        "error_code": error_code,
                    }
                )
                return ChatEvaluationObservation(
                    query_id=case.query_id,
                    normalized_entities=query_plan.entity_names,
                    section_types=query_plan.section_types,
                    response_time_ms=elapsed_ms,
                    langsmith_trace_id=root_span.trace_id,
                    error_code=error_code,
                )

            elapsed_ms = self._elapsed_ms(started_at)
            source_kinds = list(dict.fromkeys(source.kind for source in result.sources))
            root_span.end(
                {
                    "status": "COMPLETED",
                    "route": result.route.value,
                    "safety_status": result.safety_status.value,
                    "source_count": len(source_kinds),
                }
            )
            return ChatEvaluationObservation(
                query_id=case.query_id,
                route=result.route,
                normalized_entities=query_plan.entity_names,
                section_types=query_plan.section_types,
                source_kinds=source_kinds,
                safety_status=result.safety_status,
                response_time_ms=elapsed_ms,
                langsmith_trace_id=root_span.trace_id,
                answer=result.answer,
            )

    def _elapsed_ms(self, started_at: float) -> float:
        return round((self._clock() - started_at) * 1000, 3)
