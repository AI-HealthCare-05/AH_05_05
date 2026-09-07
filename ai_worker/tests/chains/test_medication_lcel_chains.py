from langchain_core.runnables import RunnableLambda

from ai_worker.chains.medication_answer_chain import (
    MedicationAnswerChainInput,
    build_medication_answer_chain,
)
from ai_worker.chains.medication_query_plan_chain import (
    MedicationQueryPlanChainInput,
    build_medication_query_plan_chain,
)
from ai_worker.llm.generators.medication_answer_generator import (
    MedicationAnswerPayload,
)
from ai_worker.schemas.enums import SafetyStatus
from ai_worker.schemas.knowledge import KnowledgeSectionType
from ai_worker.schemas.medication_chat import (
    ActiveIntakeContext,
    MedicationChatRequest,
    MedicationChatResult,
    MedicationChatRoute,
)
from ai_worker.schemas.medication_search import (
    MEDICATION_QUESTION_INTERPRETATION_VERSION,
    MedicationExpressionCorrection,
    MedicationExpressionResolutionStatus,
    MedicationKnowledgeQueryPlan,
    MedicationQuestionConfidence,
    MedicationQuestionIntent,
    MedicationQuestionResolution,
    MedicationQuestionScope,
)


async def test_query_plan_chain_returns_typed_interaction_plan() -> None:
    chain = build_medication_query_plan_chain()
    resolution = MedicationQuestionResolution(
        original_question="칼슘과 철분을 같이 먹어도 되나요?",
        resolved_question="칼슘과 철분을 같이 먹어도 되나요?",
        scope=MedicationQuestionScope.IN_SCOPE,
        status=MedicationExpressionResolutionStatus.UNCHANGED,
    )

    planning = await chain.ainvoke(
        MedicationQueryPlanChainInput(
            question=resolution.resolved_question,
            supplement_names=["칼슘", "철분"],
            resolution=resolution,
        )
    )

    plan = planning.query_plan
    assert isinstance(plan, MedicationKnowledgeQueryPlan)
    assert plan.entity_names == ["칼슘", "철분"]
    assert plan.section_types == [KnowledgeSectionType.INTERACTION]
    assert planning.interpretation.intent == MedicationQuestionIntent.INTERACTION
    assert planning.interpretation.confidence == MedicationQuestionConfidence.HIGH
    assert planning.interpretation.normalized_entity_names == ["칼슘", "철분"]
    assert planning.interpretation.needs_clarification is False
    assert planning.interpretation.interpretation_version == MEDICATION_QUESTION_INTERPRETATION_VERSION
    assert planning.interpretation.reason_codes == [
        "ENTITY_IDENTIFIED",
        "INTERACTION_PAIR_IDENTIFIED",
    ]


async def test_query_plan_chain_marks_missing_resolution_as_low_confidence() -> None:
    planning = await build_medication_query_plan_chain().ainvoke(
        MedicationQueryPlanChainInput(
            question="마그네슘은 왜 먹나요?",
            supplement_names=["마그네슘"],
        )
    )

    assert planning.interpretation.confidence == MedicationQuestionConfidence.LOW
    assert planning.interpretation.reason_codes == [
        "QUESTION_RESOLUTION_UNAVAILABLE",
        "ENTITY_IDENTIFIED",
    ]


async def test_query_plan_chain_preserves_correction_as_structured_reason() -> None:
    chain = build_medication_query_plan_chain()
    resolution = MedicationQuestionResolution(
        original_question="타이래놀 주의사항",
        resolved_question="타이레놀 주의사항",
        scope=MedicationQuestionScope.IN_SCOPE,
        status=MedicationExpressionResolutionStatus.AUTO_CORRECTED,
        corrections=[
            MedicationExpressionCorrection(
                original="타이래놀",
                replacement="타이레놀",
            )
        ],
    )

    planning = await chain.ainvoke(
        MedicationQueryPlanChainInput(
            question=resolution.resolved_question,
            resolution=resolution,
        )
    )

    assert planning.interpretation.intent == (MedicationQuestionIntent.MEDICATION_GUIDE)
    assert planning.interpretation.confidence == MedicationQuestionConfidence.MEDIUM
    assert planning.interpretation.correction_count == 1
    assert planning.interpretation.reason_codes == [
        "EXPRESSION_AUTO_CORRECTED",
        "ENTITY_IDENTIFIED",
    ]


async def test_answer_chain_builds_messages_from_typed_input() -> None:
    observed_messages = []

    async def answer_from_messages(messages):
        observed_messages.extend(messages)
        return {
            "answer": "확인된 근거만 간결하게 설명합니다.",
            "section_types": ["CAUTION"],
        }

    chain = build_medication_answer_chain(
        response_runnable=RunnableLambda(answer_from_messages),
    )
    request = MedicationChatRequest(
        request_id="6925e6ec-259c-4a96-8e69-6d5e8a626f1e",
        user_id=1,
        question="타이레놀 주의사항을 알려줘",
    )
    result = MedicationChatResult(
        request_id=request.request_id,
        answer="주의사항: 확인된 초안입니다.",
        route=MedicationChatRoute.MEDICATION_GUIDE,
        safety_status=SafetyStatus.SAFE,
        prompt_version="draft-v1",
        schema_version="medication-chat-result-v1",
    )

    payload = await chain.ainvoke(
        MedicationAnswerChainInput(
            request=request,
            context=ActiveIntakeContext(user_id=1),
            result=result,
        )
    )

    assert isinstance(payload, MedicationAnswerPayload)
    assert payload.answer == "확인된 근거만 간결하게 설명합니다."
    assert payload.section_types == [KnowledgeSectionType.CAUTION]
    assert len(observed_messages) == 2
    assert "타이레놀 주의사항을 알려줘" in observed_messages[-1].content
