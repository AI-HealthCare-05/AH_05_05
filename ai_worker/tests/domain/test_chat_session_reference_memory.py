from ai_worker.domain.chat_session_reference_memory import ChatSessionReferenceMemory
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.medication_chat import (
    MedicationChatSessionReference,
    MedicationChatSessionReferenceEntity,
)
from ai_worker.schemas.medication_search import MedicationQueryEntityType


def test_resolves_single_drug_reference_from_structured_session_entity() -> None:
    reference = MedicationChatSessionReference(
        entities=[
            MedicationChatSessionReferenceEntity(
                name="타이레놀정500밀리그람",
                entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                kind=InteractionEntityKind.DRUG,
            )
        ],
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
    reference = MedicationChatSessionReference(
        entities=[
            MedicationChatSessionReferenceEntity(
                name="와파린",
                entity_type=MedicationQueryEntityType.TOPIC,
            ),
            MedicationChatSessionReferenceEntity(
                name="비타민 K",
                entity_type=MedicationQueryEntityType.TOPIC,
            ),
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
    reference = MedicationChatSessionReference()

    assert (
        ChatSessionReferenceMemory().resolve_question(
            question="그 약의 복용법도 알려줘.",
            reference=reference,
        )
        == "그 약의 복용법도 알려줘."
    )


def test_does_not_keep_a_product_name_for_multiple_session_products() -> None:
    reference = MedicationChatSessionReference(
        entities=[
            MedicationChatSessionReferenceEntity(
                name="타이레놀정500밀리그람",
                entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                kind=InteractionEntityKind.DRUG,
            ),
            MedicationChatSessionReferenceEntity(
                name="마그오캡슐500밀리그람",
                entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                kind=InteractionEntityKind.DRUG,
            ),
        ]
    )

    resolution = ChatSessionReferenceMemory().resolve(
        question="그 약의 복용법도 알려줘.",
        reference=reference,
    )

    assert resolution.question == "그 약의 복용법도 알려줘."
    assert resolution.referenced_product_name is None
