import pytest

from ai_worker.chains.semantic_question_router import (
    ROUTE_PROTOTYPES,
    LocalSemanticQuestionRouter,
    QuestionRoutingDecision,
    QuestionRoutingReasonCode,
    QuestionRoutingStage,
    SemanticRouterInput,
)
from ai_worker.schemas.medication_chat import MedicationChatRoute


class StaticEmbeddingModel:
    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._vectors[text] for text in texts]


def test_routing_decision_rejects_free_form_reasoning() -> None:
    with pytest.raises(ValueError):
        QuestionRoutingDecision.model_validate(
            {
                "stage": "SEMANTIC",
                "route": "INTERACTION",
                "confidence": "HIGH",
                "reasoning": "숨겨진 추론",
            }
        )


async def test_router_accepts_clear_interaction_when_score_and_margin_pass() -> None:
    vectors = {
        "같이 먹어도 돼?": [1.0, 0.0],
        **{
            prototype: ([1.0, 0.0] if route == MedicationChatRoute.INTERACTION else [0.0, 1.0])
            for route, prototype in ROUTE_PROTOTYPES.items()
        },
    }
    router = LocalSemanticQuestionRouter(
        embedder=StaticEmbeddingModel(vectors),
        min_score=0.78,
        min_margin=0.10,
    )

    decision = await router.ainvoke(
        SemanticRouterInput(question="같이 먹어도 돼?"),
    )

    assert decision.stage == QuestionRoutingStage.SEMANTIC
    assert decision.route == MedicationChatRoute.INTERACTION
    assert decision.reason_codes == [QuestionRoutingReasonCode.SEMANTIC_ROUTE_MATCHED]


async def test_router_falls_back_when_top_two_routes_are_too_close() -> None:
    vectors = {
        "애매한 질문": [1.0, 0.0],
        **{
            prototype: (
                [1.0, 0.0]
                if route in {MedicationChatRoute.INTERACTION, MedicationChatRoute.MEDICATION_GUIDE}
                else [0.0, 1.0]
            )
            for route, prototype in ROUTE_PROTOTYPES.items()
        },
    }
    router = LocalSemanticQuestionRouter(
        embedder=StaticEmbeddingModel(vectors),
        min_score=0.78,
        min_margin=0.10,
    )

    decision = await router.ainvoke(SemanticRouterInput(question="애매한 질문"))

    assert decision.stage == QuestionRoutingStage.FALLBACK
    assert decision.route is None
    assert decision.reason_codes == [QuestionRoutingReasonCode.MARGIN_BELOW_THRESHOLD]
