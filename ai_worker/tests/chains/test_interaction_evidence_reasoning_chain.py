import pytest

from ai_worker.chains.interaction_evidence_reasoning_chain import (
    build_interaction_evidence_reasoning_chain,
)
from ai_worker.schemas.evidence_reasoning import (
    EvidenceClaim,
    EvidenceItem,
    EvidenceReasoningInput,
    EvidenceReasoningOutput,
    InteractionEvidenceDecision,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType


def build_input() -> EvidenceReasoningInput:
    return EvidenceReasoningInput(
        question="마그네슘과 아연을 같이 먹어도 되나요?",
        entity_names=["마그네슘", "아연"],
        requested_section_types=[KnowledgeSectionType.INTERACTION],
        interaction_pair_keys=["supplement:마그네슘|supplement:아연"],
        evidence_items=[
            EvidenceItem(
                evidence_id="chunk:abc",
                content="사람 대상 연구에서 두 성분을 함께 섭취한 조건을 비교했다.",
                section_types=[KnowledgeSectionType.INTERACTION],
                pair_keys=["supplement:마그네슘|supplement:아연"],
                study_scope="HUMAN",
            )
        ],
    )


async def test_chain_accepts_claims_backed_by_input_evidence_ids() -> None:
    observed_messages = []

    class Client:
        async def ainvoke(self, messages):
            observed_messages.extend(messages)
            return {
                "reasoning_status": "SUPPORTED",
                "interaction_decision": "INTERACTION_CONFIRMED",
                "claims": [
                    {
                        "section_type": "INTERACTION",
                        "statement": "제시된 연구 조건에서 두 성분의 관계가 확인됐습니다.",
                        "evidence_ids": ["chunk:abc"],
                        "scope_note": "사람 대상 연구 조건에 한정합니다.",
                    }
                ],
                "supported_action": None,
                "missing_section_types": [],
                "conflict_evidence_ids": [],
            }

    chain = build_interaction_evidence_reasoning_chain(
        model="test-model",
        client=Client(),
    )

    output = await chain.ainvoke(build_input())

    assert output.interaction_decision is InteractionEvidenceDecision.INTERACTION_CONFIRMED
    assert output.claims[0].evidence_ids == ["chunk:abc"]
    assert len(observed_messages) == 2
    assert "역할(Role)" in observed_messages[0].content
    assert '"chunk:abc"' in observed_messages[1].content


async def test_chain_rejects_claim_with_unknown_evidence_id() -> None:
    class Client:
        async def ainvoke(self, messages):
            return {
                "reasoning_status": "SUPPORTED",
                "interaction_decision": "INTERACTION_CONFIRMED",
                "claims": [
                    {
                        "section_type": "INTERACTION",
                        "statement": "확인됐습니다.",
                        "evidence_ids": ["chunk:invented"],
                        "scope_note": None,
                    }
                ],
                "supported_action": None,
                "missing_section_types": [],
                "conflict_evidence_ids": [],
            }

    chain = build_interaction_evidence_reasoning_chain(
        model="test-model",
        client=Client(),
    )

    with pytest.raises(ValueError, match="입력 근거 ID"):
        await chain.ainvoke(build_input())


def test_output_rejects_free_form_chain_of_thought() -> None:
    with pytest.raises(ValueError):
        EvidenceReasoningOutput.model_validate(
            {
                "reasoning_status": "INSUFFICIENT",
                "interaction_decision": "NO_DIRECT_EVIDENCE",
                "claims": [],
                "supported_action": None,
                "missing_section_types": ["INTERACTION"],
                "conflict_evidence_ids": [],
                "reasoning": "내부 추론 원문",
            }
        )


def test_confirmed_decision_requires_interaction_claim() -> None:
    with pytest.raises(ValueError, match="INTERACTION claim"):
        EvidenceReasoningOutput(
            reasoning_status="SUPPORTED",
            interaction_decision="INTERACTION_CONFIRMED",
            claims=[
                EvidenceClaim(
                    section_type=KnowledgeSectionType.CAUTION,
                    statement="주의가 필요합니다.",
                    evidence_ids=["chunk:abc"],
                )
            ],
            missing_section_types=[],
        )


def test_conflicting_decision_requires_two_conflict_evidence_ids() -> None:
    with pytest.raises(ValueError, match="두 개 이상의 충돌 근거"):
        EvidenceReasoningOutput(
            reasoning_status="CONFLICTING",
            interaction_decision="CONFLICTING_EVIDENCE",
            claims=[],
            missing_section_types=[],
            conflict_evidence_ids=["chunk:abc"],
        )


async def test_interaction_request_rejects_not_applicable_decision() -> None:
    class Client:
        async def ainvoke(self, messages):
            return {
                "reasoning_status": "INSUFFICIENT",
                "interaction_decision": "NOT_APPLICABLE",
                "claims": [],
                "supported_action": None,
                "missing_section_types": ["INTERACTION"],
                "conflict_evidence_ids": [],
            }

    chain = build_interaction_evidence_reasoning_chain(
        model="test-model",
        client=Client(),
    )

    with pytest.raises(ValueError, match="상호작용 요청"):
        await chain.ainvoke(build_input())
