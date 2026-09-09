from ai_worker.domain.chat_session_reference_memory import ChatSessionReferenceMemory
from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.enums import ChatRole
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.medication_search import MedicationQueryEntityType


def test_extracts_the_last_grounded_product_and_resolves_single_drug_reference() -> None:
    reference = ChatSessionReferenceMemory().from_history(
        [
            ChatHistoryMessage(role=ChatRole.USER, content="타이레놀정500밀리그람이 어떤 약인가요?"),
            ChatHistoryMessage(
                role=ChatRole.ASSISTANT,
                content="일반 제품 안내\n- 제품: 타이레놀정500밀리그람 (테스트제약)\n- 효능: 통증 완화",
            ),
        ]
    )

    assert [(entity.name, entity.kind, entity.entity_type) for entity in reference.entities] == [
        (
            "타이레놀정500밀리그람",
            InteractionEntityKind.DRUG,
            MedicationQueryEntityType.PRODUCT_NAME,
        )
    ]
    assert (
        ChatSessionReferenceMemory().resolve_question(
            question="그 약의 복용법도 알려줘.",
            reference=reference,
        )
        == "타이레놀정500밀리그람의 복용법도 알려줘."
    )


def test_expands_group_reference_but_keeps_untyped_interaction_names_for_catalog_revalidation() -> None:
    reference = ChatSessionReferenceMemory().from_history(
        [
            ChatHistoryMessage(
                role=ChatRole.ASSISTANT,
                content="확인된 상호작용\n- 와파린 ↔ 비타민 K: 승인 규칙 근거",
            )
        ]
    )

    assert [entity.name for entity in reference.entities] == ["와파린", "비타민 K"]
    assert all(entity.kind is None for entity in reference.entities)
    assert (
        ChatSessionReferenceMemory().resolve_question(
            question="그중 혈액 응고와 관련된 대상은 무엇인가요?",
            reference=reference,
        )
        == "와파린, 비타민 K 중 혈액 응고와 관련된 대상은 무엇인가요?"
    )


def test_does_not_resolve_a_reference_without_current_session_memory() -> None:
    reference = ChatSessionReferenceMemory().from_history([])

    assert (
        ChatSessionReferenceMemory().resolve_question(
            question="그 약의 복용법도 알려줘.",
            reference=reference,
        )
        == "그 약의 복용법도 알려줘."
    )
