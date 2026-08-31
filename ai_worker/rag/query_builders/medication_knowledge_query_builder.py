import re

from pydantic import BaseModel, Field

from ai_worker.domain.interaction_question_detector import (
    is_interaction_question,
)
from ai_worker.rag.metadata.supplement_interaction_registry import (
    SupplementInteractionPair,
    find_supplement_interaction_pair,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType


class MedicationKnowledgeQueryPlan(BaseModel):
    original_query: str = Field(min_length=1)
    expanded_query: str = Field(min_length=1)
    entity_names: list[str] = Field(default_factory=list)
    section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    alternate_queries: list[str] = Field(default_factory=list)
    interaction_pair: SupplementInteractionPair | None = None
    has_medication_product_cue: bool = False


class MedicationKnowledgeQueryBuilder:
    _MEDICATION_PRODUCT_CUE = re.compile(
        r"(?:\d+(?:\.\d+)?\s*(?:mg|g|ml|밀리그램|그램|밀리리터)\b|"
        r"[가-힣A-Za-z0-9]+(?:정|캡슐|시럽|연고|크림|패치|패취|주사))",
        flags=re.IGNORECASE,
    )
    _ENTITY_TOKEN = re.compile(
        r"비타민\s*[A-Za-z0-9]+|오메가\s*3|[가-힣A-Za-z0-9.+-]{2,}",
        flags=re.IGNORECASE,
    )
    _STOPWORDS = {
        "기능",
        "기능성",
        "효과",
        "효능",
        "먹어",
        "먹나요",
        "복용",
        "섭취",
        "알려줘",
        "알려주세요",
        "얼마나",
        "하루에",
        "주의사항",
        "부작용",
        "상호작용",
        "같이",
        "함께",
        "무슨",
        "어떤",
        "왜",
    }

    def build(self, question: str) -> MedicationKnowledgeQueryPlan:
        normalized = question.strip()
        if not normalized:
            raise ValueError("약·영양제 검색 질문은 비어 있을 수 없습니다.")

        interaction_pair = find_supplement_interaction_pair(normalized)
        section_types, expansion_terms = self._intent(
            normalized,
            has_interaction_pair=interaction_pair is not None,
        )
        entity_names = (
            list(interaction_pair.canonical_names) if interaction_pair is not None else self._entity_names(normalized)
        )
        expanded_query = " ".join(
            dict.fromkeys(
                [
                    normalized,
                    *entity_names,
                    *expansion_terms,
                ]
            )
        )
        return MedicationKnowledgeQueryPlan(
            original_query=normalized,
            expanded_query=expanded_query,
            entity_names=entity_names,
            section_types=section_types,
            alternate_queries=([interaction_pair.english_query] if interaction_pair is not None else []),
            interaction_pair=interaction_pair,
            has_medication_product_cue=bool(self._MEDICATION_PRODUCT_CUE.search(normalized)),
        )

    @classmethod
    def _entity_names(cls, question: str) -> list[str]:
        names: list[str] = []
        for match in cls._ENTITY_TOKEN.finditer(question):
            value = re.sub(r"\s+", " ", match.group()).strip()
            value = re.sub(r"(?:은|는|이|가|을|를|과|와|도|의)$", "", value)
            if not value or value in cls._STOPWORDS or value.isdigit():
                continue
            names.append(value)
        return list(dict.fromkeys(names))

    @staticmethod
    def _intent(
        question: str,
        *,
        has_interaction_pair: bool = False,
    ) -> tuple[list[KnowledgeSectionType], list[str]]:
        if has_interaction_pair or is_interaction_question(question):
            return [KnowledgeSectionType.INTERACTION], ["상호작용", "병용 주의"]
        if any(keyword in question for keyword in ("하루", "얼마", "섭취량", "복용량", "용량")):
            return [KnowledgeSectionType.DAILY_INTAKE], ["일일섭취량", "섭취 기준"]
        if any(keyword in question for keyword in ("주의", "부작용", "조심", "위험")):
            return [KnowledgeSectionType.CAUTION], ["섭취 시 주의사항", "부작용"]
        if any(keyword in question for keyword in ("효능", "효과", "기능", "왜 먹")):
            return [KnowledgeSectionType.FUNCTION], ["건강기능식품", "기능성", "효능", "섭취 목적"]
        return [], []
