import re

from ai_worker.schemas.chat import ChatHistoryMessage
from ai_worker.schemas.enums import ChatRole
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.medication_chat import (
    MedicationChatSessionReference,
    MedicationChatSessionReferenceEntity,
)
from ai_worker.schemas.medication_search import MedicationQueryEntityType


class ChatSessionReferenceMemory:
    """현재 세션의 근거가 있는 답변 형식에서만 참조 대상을 꺼낸다."""

    _PRODUCT_PATTERN = re.compile(
        r"(?ms)^일반 제품 안내\s*\n-\s*(?:기준\s*)?제품:\s*(?P<name>[^\n(]+)",
    )
    _INGREDIENT_FAMILY_PATTERN = re.compile(
        r"(?ms)^세부 성분 안내\s*\n-\s*(?P<name>[^\n]+?)는 여러 성분을 묶어 부르는 이름입니다\.",
    )
    _INTERACTION_SECTION_PATTERN = re.compile(
        r"(?ms)^확인된 상호작용\s*\n(?P<body>.*?)(?=\n\n|\Z)",
    )
    _INTERACTION_LINE_PATTERN = re.compile(
        r"(?m)^-\s*(?P<left>[^↔:\n]+?)\s*↔\s*(?P<right>[^:\n]+):",
    )
    _SINGLE_DRUG_REFERENCE_PATTERN = re.compile(r"그\s*약")
    _SINGLE_INGREDIENT_REFERENCE_PATTERN = re.compile(r"그\s*(?:성분|영양제)")
    _GROUP_REFERENCE_PATTERN = re.compile(r"그\s*중")

    def from_history(
        self,
        history: list[ChatHistoryMessage],
    ) -> MedicationChatSessionReference:
        for message in reversed(history):
            if message.role != ChatRole.ASSISTANT:
                continue
            entities = self._extract_entities(message.content)
            if entities:
                return MedicationChatSessionReference(entities=entities)
        return MedicationChatSessionReference()

    def resolve_question(
        self,
        *,
        question: str,
        reference: MedicationChatSessionReference,
    ) -> str:
        product_name = self._single_name(
            reference=reference,
            entity_types={
                MedicationQueryEntityType.PRODUCT_NAME,
                MedicationQueryEntityType.BRAND_ALIAS,
            },
        )
        if product_name and self._SINGLE_DRUG_REFERENCE_PATTERN.search(question):
            return self._SINGLE_DRUG_REFERENCE_PATTERN.sub(product_name, question, count=1)

        ingredient_name = self._single_name(
            reference=reference,
            entity_types={
                MedicationQueryEntityType.INGREDIENT_NAME,
                MedicationQueryEntityType.INGREDIENT_FAMILY,
            },
        )
        if ingredient_name and self._SINGLE_INGREDIENT_REFERENCE_PATTERN.search(question):
            return self._SINGLE_INGREDIENT_REFERENCE_PATTERN.sub(ingredient_name, question, count=1)

        names = list(dict.fromkeys(entity.name for entity in reference.entities))
        if names and self._GROUP_REFERENCE_PATTERN.search(question):
            return self._GROUP_REFERENCE_PATTERN.sub(f"{', '.join(names)} 중", question, count=1)
        return question

    def _extract_entities(
        self,
        content: str,
    ) -> list[MedicationChatSessionReferenceEntity]:
        product_match = self._PRODUCT_PATTERN.search(content)
        if product_match is not None:
            return [
                MedicationChatSessionReferenceEntity(
                    name=product_match.group("name").strip(),
                    entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                    kind=InteractionEntityKind.DRUG,
                )
            ]

        ingredient_match = self._INGREDIENT_FAMILY_PATTERN.search(content)
        if ingredient_match is not None:
            return [
                MedicationChatSessionReferenceEntity(
                    name=ingredient_match.group("name").strip(),
                    entity_type=MedicationQueryEntityType.INGREDIENT_FAMILY,
                    kind=InteractionEntityKind.SUPPLEMENT,
                )
            ]

        section_match = self._INTERACTION_SECTION_PATTERN.search(content)
        if section_match is None:
            return []
        entities = []
        for match in self._INTERACTION_LINE_PATTERN.finditer(section_match.group("body")):
            entities.extend(
                [
                    MedicationChatSessionReferenceEntity(
                        name=match.group("left").strip(),
                        entity_type=MedicationQueryEntityType.TOPIC,
                    ),
                    MedicationChatSessionReferenceEntity(
                        name=match.group("right").strip(),
                        entity_type=MedicationQueryEntityType.TOPIC,
                    ),
                ]
            )
        return self._deduplicate(entities)

    @staticmethod
    def _single_name(
        *,
        reference: MedicationChatSessionReference,
        entity_types: set[MedicationQueryEntityType],
    ) -> str | None:
        names = list(dict.fromkeys(entity.name for entity in reference.entities if entity.entity_type in entity_types))
        return names[0] if len(names) == 1 else None

    @staticmethod
    def _deduplicate(
        entities: list[MedicationChatSessionReferenceEntity],
    ) -> list[MedicationChatSessionReferenceEntity]:
        unique: dict[str, MedicationChatSessionReferenceEntity] = {}
        for entity in entities:
            unique.setdefault(entity.name.casefold(), entity)
        return list(unique.values())[:4]
