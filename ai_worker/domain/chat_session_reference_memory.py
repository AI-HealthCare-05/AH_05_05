import re
from dataclasses import dataclass

from ai_worker.schemas.medication_chat import (
    MedicationChatSessionReference,
)
from ai_worker.schemas.medication_search import MedicationQueryEntityType


@dataclass(frozen=True)
class ChatSessionReferenceResolution:
    """현재 질문에 적용된 세션 참조와 표시 가능한 단일 제품명을 함께 보관한다."""

    question: str
    referenced_product_name: str | None = None


class ChatSessionReferenceMemory:
    """저장된 구조화 엔터티를 현재 질문의 지시어에 연결한다."""

    _SINGLE_DRUG_REFERENCE_PATTERN = re.compile(r"그\s*약")
    _SINGLE_INGREDIENT_REFERENCE_PATTERN = re.compile(r"그\s*(?:성분|영양제)")
    _GROUP_REFERENCE_PATTERN = re.compile(r"그\s*중")

    def resolve_question(
        self,
        *,
        question: str,
        reference: MedicationChatSessionReference,
    ) -> str:
        return self.resolve(
            question=question,
            reference=reference,
        ).question

    def resolve(
        self,
        *,
        question: str,
        reference: MedicationChatSessionReference,
    ) -> ChatSessionReferenceResolution:
        product_name = self._single_name(
            reference=reference,
            entity_types={
                MedicationQueryEntityType.PRODUCT_NAME,
                MedicationQueryEntityType.BRAND_ALIAS,
            },
        )
        if product_name and self._SINGLE_DRUG_REFERENCE_PATTERN.search(question):
            return ChatSessionReferenceResolution(
                question=self._SINGLE_DRUG_REFERENCE_PATTERN.sub(
                    product_name,
                    question,
                    count=1,
                ),
                referenced_product_name=product_name,
            )

        ingredient_name = self._single_name(
            reference=reference,
            entity_types={
                MedicationQueryEntityType.INGREDIENT_NAME,
                MedicationQueryEntityType.INGREDIENT_FAMILY,
            },
        )
        if ingredient_name and self._SINGLE_INGREDIENT_REFERENCE_PATTERN.search(question):
            return ChatSessionReferenceResolution(
                question=self._SINGLE_INGREDIENT_REFERENCE_PATTERN.sub(
                    ingredient_name,
                    question,
                    count=1,
                )
            )

        names = list(dict.fromkeys(entity.name for entity in reference.entities))
        if names and self._GROUP_REFERENCE_PATTERN.search(question):
            return ChatSessionReferenceResolution(
                question=self._GROUP_REFERENCE_PATTERN.sub(
                    f"{', '.join(names)} 중",
                    question,
                    count=1,
                )
            )
        return ChatSessionReferenceResolution(question=question)

    @staticmethod
    def _single_name(
        *,
        reference: MedicationChatSessionReference,
        entity_types: set[MedicationQueryEntityType],
    ) -> str | None:
        names = list(dict.fromkeys(entity.name for entity in reference.entities if entity.entity_type in entity_types))
        return names[0] if len(names) == 1 else None
