import pytest

from ai_worker.domain.errors import ChatAnswerGenerationError
from ai_worker.llm.generators.medication_answer_generator import (
    OpenAIMedicationAnswerGenerator,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationAnswerFallbackReason,
    MedicationAnswerRewriteStatus,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
    MedicationChatSource,
    MedicationChatSourceKind,
)


class FakeAnswerClient:
    def __init__(self, response=None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.messages = None

    async def ainvoke(self, messages):
        self.messages = messages
        if self.error is not None:
            raise self.error
        return self.response


def build_request() -> MedicationChatRequest:
    return MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="타이레놀정500밀리그람 주의사항을 알려줘",
    )


def build_result() -> MedicationChatResult:
    return MedicationChatResult(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        answer=("일반 제품 안내\n- 정해진 용법을 지킵니다.\n\n이 안내는 의료진의 진료를 대체하지 않습니다."),
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        sources=[
            MedicationChatSource(
                kind=MedicationChatSourceKind.MEDICATION_GUIDE,
                title="e약은요 · 타이레놀정500밀리그람",
                medication_guide_id=12,
            )
        ],
        prompt_version="medication-chat-prompt-v1",
        schema_version="medication-chat-result-v1",
    )


async def test_generator_rewrites_draft_and_preserves_grounding_metadata() -> None:
    client = FakeAnswerClient(
        response={"answer": ("정해진 용법을 지켜 복용해야 합니다. 이 안내는 의료진의 진료를 대체하지 않습니다.")}
    )
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=client,
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=build_result(),
    )

    assert outcome.result.answer.startswith("정해진 용법")
    assert outcome.result.sources == build_result().sources
    assert outcome.result.model_name == "gpt-4o-mini"
    assert outcome.observation.status == MedicationAnswerRewriteStatus.REWRITTEN
    assert outcome.observation.fallback_used is False
    assert outcome.observation.fallback_reason is None
    assert client.messages is not None


async def test_generator_skips_llm_when_no_grounded_sources() -> None:
    client = FakeAnswerClient(error=AssertionError("호출하면 안 됩니다."))
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=client,
    )
    initial = build_result().model_copy(update={"sources": []})

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result == initial
    assert outcome.observation.status == MedicationAnswerRewriteStatus.SKIPPED
    assert outcome.observation.fallback_reason == MedicationAnswerFallbackReason.NO_GROUNDED_SOURCES
    assert outcome.observation.generated_answer_hash is None


async def test_generator_wraps_client_failure() -> None:
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeAnswerClient(error=RuntimeError("openai down")),
    )

    with pytest.raises(ChatAnswerGenerationError) as exc_info:
        await generator.generate(
            request=build_request(),
            context=ActiveIntakeContext(user_id=1),
            result=build_result(),
        )
    assert exc_info.value.reason_code == MedicationAnswerFallbackReason.CLIENT_ERROR


async def test_generator_removes_markdown_heading_and_bold_markers() -> None:
    grounded_result = build_result().model_copy(
        update={
            "answer": (
                "일반 제품 안내\n"
                "- 사용법: 1일 1~2캡슐을 나누어 복용합니다.\n\n"
                "이 안내는 의료진의 진료를 대체하지 않습니다."
            )
        }
    )
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeAnswerClient(
            response={
                "answer": (
                    "# 마그오캡슐500mg 안내\n"
                    "**사용법**: 1일 1~2캡슐을 나누어 복용합니다.\n\n"
                    "이 안내는 의료진의 진료를 대체하지 않습니다."
                )
            }
        ),
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=grounded_result,
    )

    assert "#" not in outcome.result.answer
    assert "**" not in outcome.result.answer
    assert "사용법: 1일 1~2캡슐" in outcome.result.answer


async def test_generator_falls_back_to_safe_draft_when_rewrite_adds_claims() -> None:
    initial = build_result()
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeAnswerClient(
            response={"answer": ("이 약은 하루 10정을 먹어도 안전합니다. 이 안내는 의료진의 진료를 대체하지 않습니다.")}
        ),
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result.answer == initial.answer
    assert outcome.result.safety_status == SafetyStatus.SAFE
    assert outcome.result.safety_reason_codes == []
    assert outcome.result.model_name == "gpt-4o-mini"
    assert outcome.observation.status == MedicationAnswerRewriteStatus.DRAFT_FALLBACK
    assert outcome.observation.fallback_used is True
    assert outcome.observation.fallback_reason == MedicationAnswerFallbackReason.UNSUPPORTED_SAFETY_ASSERTION


async def test_generator_reports_dosage_fallback_reason() -> None:
    initial = build_result()
    generator = OpenAIMedicationAnswerGenerator(
        model="gpt-4o-mini",
        client=FakeAnswerClient(response={"answer": "이 약은 하루 10정을 복용하세요. 의료진과 상담하세요."}),
    )

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result.answer == initial.answer
    assert outcome.observation.fallback_reason == (MedicationAnswerFallbackReason.GENERATED_DOSAGE_NOT_IN_DRAFT)


async def test_generator_skips_llm_for_clarification_route() -> None:
    client = FakeAnswerClient(error=AssertionError("호출하면 안 됩니다."))
    generator = OpenAIMedicationAnswerGenerator(model="gpt-4o-mini", client=client)
    initial = build_result().model_copy(update={"route": MedicationChatRoute.CLARIFICATION})

    outcome = await generator.generate(
        request=build_request(),
        context=ActiveIntakeContext(user_id=1),
        result=initial,
    )

    assert outcome.result == initial
    assert outcome.observation.fallback_reason == (MedicationAnswerFallbackReason.CLARIFICATION_REQUIRED)
