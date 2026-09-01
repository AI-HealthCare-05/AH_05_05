from contextlib import asynccontextmanager
from uuid import uuid4

from ai_worker.evaluation.chat_evaluation_executor import (
    ChatCoreEvaluationExecutor,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
)
from ai_worker.schemas.medication_search import (
    MedicationKnowledgeQueryPlan,
    MedicationSearchExecutionObservation,
)

from .test_chat_evaluator import build_case


class RecordingSpan:
    trace_id = "trace-123"

    def __init__(self) -> None:
        self.outputs: dict = {}

    def end(self, outputs=None) -> None:
        self.outputs.update(outputs or {})


class RecordingTracer:
    capture_content = False

    def __init__(self) -> None:
        self.names: list[str] = []
        self.span_instance = RecordingSpan()

    @asynccontextmanager
    async def span(self, name, **kwargs):
        self.names.append(name)
        yield self.span_instance

    def anonymize_identifier(self, value):
        return "anonymous"

    async def aclose(self) -> None:
        return None


class FakeCoreService:
    def __init__(self, result: MedicationChatResult) -> None:
        self._result = result
        self.requests: list[MedicationChatRequest] = []

    async def answer(self, request: MedicationChatRequest) -> MedicationChatResult:
        self.requests.append(request)
        return self._result


async def test_execute_collects_query_plan_result_latency_and_trace_id() -> None:
    tracer = RecordingTracer()
    core = FakeCoreService(
        MedicationChatResult(
            request_id=uuid4(),
            answer="칼슘과 철분 근거 설명",
            route=MedicationChatRoute.INTERACTION,
            safety_status=SafetyStatus.SAFE,
            sources=[
                MedicationChatSource(
                    kind=MedicationChatSourceKind.PUBLIC_KNOWLEDGE,
                    title="칼슘과 철 흡수 연구",
                )
            ],
            prompt_version="test-prompt-v1",
            schema_version="test-result-v1",
            search_observation=MedicationSearchExecutionObservation(
                query_plan=MedicationKnowledgeQueryPlan(
                    original_query="칼슘과 철분을 같이 먹어도 되나요?",
                    expanded_query="칼슘 철분 상호작용",
                    entity_names=["칼슘", "철분"],
                    section_types=[KnowledgeSectionType.INTERACTION],
                ),
                query_plan_hash="a" * 64,
                execution_plan_hash="b" * 64,
            ),
        )
    )
    executor = ChatCoreEvaluationExecutor(
        core_service=core,
        tracer=tracer,
        user_id=7,
        care_episode_id=11,
        clock=iter([1.0, 1.125]).__next__,
    )
    case = build_case(
        "calcium-iron",
        route=MedicationChatRoute.INTERACTION,
        entities=["칼슘", "철분"],
        sources=[MedicationChatSourceKind.PUBLIC_KNOWLEDGE],
    ).model_copy(update={"question": "칼슘과 철분을 같이 먹어도 되나요?"})

    observation = await executor.execute(case)

    assert tracer.names == ["chat.evaluation.case"]
    assert observation.query_id == "calcium-iron"
    assert observation.route == MedicationChatRoute.INTERACTION
    assert observation.normalized_entities == ["칼슘", "철분"]
    assert observation.section_types == [KnowledgeSectionType.INTERACTION]
    assert observation.source_kinds == [MedicationChatSourceKind.PUBLIC_KNOWLEDGE]
    assert observation.safety_status == SafetyStatus.SAFE
    assert observation.response_time_ms == 125.0
    assert observation.langsmith_trace_id == "trace-123"
    assert observation.query_plan_hash == "a" * 64
    assert observation.execution_plan_hash == "b" * 64
    assert core.requests[0].user_id == 7
    assert core.requests[0].care_episode_id == 11


async def test_execute_converts_timeout_to_observation() -> None:
    class SlowCoreService:
        async def answer(self, request: MedicationChatRequest) -> MedicationChatResult:
            import asyncio

            await asyncio.sleep(1)
            raise AssertionError("도달하면 안 됩니다.")

    executor = ChatCoreEvaluationExecutor(
        core_service=SlowCoreService(),
        tracer=RecordingTracer(),
        user_id=7,
        timeout_seconds=0.001,
    )
    case = build_case(
        "timeout",
        route=MedicationChatRoute.INTERACTION,
        entities=["칼슘", "철분"],
        sources=[MedicationChatSourceKind.PUBLIC_KNOWLEDGE],
    )

    observation = await executor.execute(case)

    assert observation.error_code == "API_TIMEOUT"
    assert observation.route is None
    assert observation.langsmith_trace_id == "trace-123"
