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

PAIR_KEY = "a" * 64


def build_input() -> EvidenceReasoningInput:
    return EvidenceReasoningInput(
        question="마그네슘과 아연을 같이 먹어도 되나요?",
        entity_names=["마그네슘", "아연"],
        requested_section_types=[KnowledgeSectionType.INTERACTION],
        interaction_pair_keys=[PAIR_KEY],
        evidence_items=[
            EvidenceItem(
                evidence_id="chunk:abc",
                content="사람 대상 연구에서 두 성분을 함께 섭취한 조건을 비교했다.",
                section_types=[KnowledgeSectionType.INTERACTION],
                pair_keys=[PAIR_KEY],
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


async def test_chain_rejects_interaction_claim_backed_by_wrong_pair() -> None:
    class Client:
        async def ainvoke(self, messages):
            return {
                "reasoning_status": "SUPPORTED",
                "interaction_decision": "INTERACTION_CONFIRMED",
                "claims": [
                    {
                        "section_type": "INTERACTION",
                        "statement": "다른 조합의 근거입니다.",
                        "evidence_ids": ["chunk:abc"],
                        "scope_note": None,
                    }
                ],
                "supported_action": None,
                "missing_section_types": [],
                "conflict_evidence_ids": [],
            }

    payload = build_input().model_dump()
    payload["evidence_items"][0]["pair_keys"] = ["b" * 64]
    chain = build_interaction_evidence_reasoning_chain(
        model="test-model",
        client=Client(),
    )

    with pytest.raises(ValueError, match="요청한 상호작용 조합"):
        await chain.ainvoke(EvidenceReasoningInput.model_validate(payload))


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


def test_evidence_input_rejects_non_canonical_interaction_pair_key() -> None:
    payload = build_input().model_dump()
    payload["interaction_pair_keys"] = ["supplement:마그네슘|supplement:아연"]

    with pytest.raises(ValueError, match="SHA-256"):
        EvidenceReasoningInput.model_validate(payload)


def test_evidence_output_rejects_more_than_four_claims() -> None:
    with pytest.raises(ValueError):
        EvidenceReasoningOutput(
            reasoning_status="SUPPORTED",
            interaction_decision="INTERACTION_CONFIRMED",
            claims=[
                EvidenceClaim(
                    section_type=KnowledgeSectionType.INTERACTION,
                    statement=f"근거 요약 {index}",
                    evidence_ids=["chunk:abc"],
                )
                for index in range(5)
            ],
        )


def test_evidence_claim_rejects_oversized_statement() -> None:
    with pytest.raises(ValueError):
        EvidenceClaim(
            section_type=KnowledgeSectionType.INTERACTION,
            statement="가" * 241,
            evidence_ids=["chunk:abc"],
        )


def test_evidence_claim_rejects_whitespace_only_statement() -> None:
    with pytest.raises(ValueError):
        EvidenceClaim(
            section_type=KnowledgeSectionType.INTERACTION,
            statement=" ",
            evidence_ids=["chunk:abc"],
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
