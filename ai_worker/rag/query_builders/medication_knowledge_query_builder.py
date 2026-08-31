import re
from enum import StrEnum
from itertools import combinations

from pydantic import BaseModel, ConfigDict, Field

from ai_worker.domain.interaction_question_detector import (
    is_interaction_question,
)
from ai_worker.rag.metadata.supplement_interaction_registry import (
    SupplementInteractionPair,
    find_supplement_interaction_pair,
)
from ai_worker.schemas.interaction import (
    InteractionEntityKind,
    InteractionPairType,
)
from ai_worker.schemas.knowledge import KnowledgeSectionType


class MedicationQueryEntityType(StrEnum):
    PRODUCT_NAME = "PRODUCT_NAME"
    BRAND_ALIAS = "BRAND_ALIAS"
    INGREDIENT_NAME = "INGREDIENT_NAME"
    FOOD_CATEGORY = "FOOD_CATEGORY"


class MedicationQueryEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    surface: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    entity_type: MedicationQueryEntityType
    candidate_types: list[MedicationQueryEntityType] = Field(
        default_factory=list,
    )
    kind: InteractionEntityKind


class MedicationInteractionQueryPair(BaseModel):
    model_config = ConfigDict(frozen=True)

    left_name: str = Field(min_length=1)
    right_name: str = Field(min_length=1)
    pair_type: InteractionPairType


class MedicationKnowledgeQueryPlan(BaseModel):
    original_query: str = Field(min_length=1)
    expanded_query: str = Field(min_length=1)
    entity_names: list[str] = Field(default_factory=list)
    entities: list[MedicationQueryEntity] = Field(default_factory=list)
    section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    alternate_queries: list[str] = Field(default_factory=list)
    interaction_pair: SupplementInteractionPair | None = None
    interaction_pairs: list[MedicationInteractionQueryPair] = Field(
        default_factory=list,
    )
    interaction_types: list[InteractionPairType] = Field(default_factory=list)
    has_medication_product_cue: bool = False


class MedicationQueryEntityNormalizer:
    _MEDICATION_PRODUCT_CUE = re.compile(
        r"(?:\d+(?:\.\d+)?\s*(?:mg|g|ml|밀리그램|그램|밀리리터)\b|"
        r"[가-힣A-Za-z0-9]+(?:정|캡슐|시럽|연고|크림|패치|패취|주사))",
        flags=re.IGNORECASE,
    )
    _ENTITY_TOKEN = re.compile(
        r"비타민\s*[A-Za-z0-9]+|오메가\s*3|[가-힣A-Za-z0-9.+-]{2,}",
        flags=re.IGNORECASE,
    )
    _TRAILING_PARTICLE = re.compile(
        r"(?:으로|에서|부터|까지|처럼|보다|에게|한테|하고|이며|이나|"
        r"이랑|랑|은|는|이|가|을|를|과|와|도|의|로)$"
    )
    _NON_ENTITY_PREDICATE = re.compile(
        r"^(?:"
        r"먹(?:어|으면|나요|어야|을|는|지|고|어도)|"
        r"피하(?:면|나요|야|지|고|는|여|할)|"
        r"주의(?:하(?:면|나요|야|지|고|는|여)|할|해야)|"
        r"떨어지(?:면|나요|는|고|지)|"
        r"알려|요약해|등록해|확인해|검색해"
        r")[가-힣]*$"
    )
    _STOPWORDS = {
        "공공자료",
        "관련",
        "같",
        "기능",
        "기능성",
        "내",
        "내가",
        "되나요",
        "효과",
        "효능",
        "먹어",
        "먹어도",
        "먹어야",
        "먹",
        "먹나요",
        "복용",
        "복용하면",
        "복용법",
        "복용하나요",
        "섭취",
        "섭취법",
        "알려줘",
        "알려주세요",
        "요약",
        "요약해줘",
        "얼마나",
        "어떻게",
        "일반적",
        "일반적으로",
        "흡수",
        "흡수에",
        "수치",
        "영향",
        "미치는",
        "낮아질",
        "있나요",
        "일시적인가요",
        "하루에",
        "하나요",
        "피해야",
        "중인",
        "등록한",
        "우선순위",
        "우선순위로",
        "시간",
        "띄워",
        "추가",
        "점",
        "주의사항",
        "부작용",
        "상호작용",
        "단일제",
        "복합제",
        "같이",
        "함께",
        "영양제",
        "약",
        "의약품",
        "무슨",
        "어떤",
        "왜",
    }
    _SUPPLEMENT_NAMES = {
        "마그네슘",
        "칼슘",
        "철",
        "철분",
        "아연",
        "구리",
        "셀레늄",
        "엽산",
        "오메가3",
        "프로바이오틱스",
        "유산균",
    }
    _BRAND_ALIASES = {
        "타이레놀",
    }
    _BRAND_INGREDIENT_ALIASES = {
        "타이레놀": "아세트아미노펜",
    }
    _FOOD_EXACT_NAMES = {
        "과일주스",
        "자몽",
        "자몽주스",
        "오렌지주스",
        "사과주스",
        "우유",
        "커피",
        "술",
        "알코올",
    }
    _FOOD_SUFFIXES = ("주스", "음식", "식품", "음료")

    def normalize(
        self,
        question: str,
        *,
        interaction_question: bool = False,
    ) -> list[MedicationQueryEntity]:
        entities: list[MedicationQueryEntity] = []
        seen: set[str] = set()
        for match in self._ENTITY_TOKEN.finditer(question):
            surface = self._clean_surface(match.group())
            canonical_name = self._canonical_name(surface)
            if not self._is_entity_candidate(surface, canonical_name):
                continue
            candidate_types = self._candidate_types(canonical_name)
            entity_type = self._entity_type(canonical_name)
            if interaction_question and canonical_name in self._BRAND_INGREDIENT_ALIASES:
                canonical_name = self._BRAND_INGREDIENT_ALIASES[canonical_name]
                entity_type = MedicationQueryEntityType.INGREDIENT_NAME
            canonical_key = canonical_name.casefold()
            if canonical_key in seen:
                continue
            entities.append(
                MedicationQueryEntity(
                    surface=surface,
                    canonical_name=canonical_name,
                    entity_type=entity_type,
                    candidate_types=candidate_types,
                    kind=self._entity_kind(canonical_name),
                )
            )
            seen.add(canonical_key)
        return entities

    @classmethod
    def has_medication_product_cue(cls, question: str) -> bool:
        return bool(cls._MEDICATION_PRODUCT_CUE.search(question))

    @classmethod
    def _clean_surface(cls, value: str) -> str:
        normalized = re.sub(r"\s+", " ", value).strip(" .,!?:;()[]{}\"'")
        if normalized in cls._STOPWORDS:
            return normalized
        previous = ""
        while previous != normalized:
            previous = normalized
            normalized = cls._TRAILING_PARTICLE.sub("", normalized)
        if normalized.endswith("나"):
            candidate = normalized[:-1]
            if (
                cls._is_food(candidate)
                or cls._is_supplement(candidate)
                or candidate in cls._BRAND_ALIASES
                or cls._MEDICATION_PRODUCT_CUE.fullmatch(candidate)
            ):
                normalized = candidate
        return normalized.strip()

    @classmethod
    def _canonical_name(cls, value: str) -> str:
        compact = re.sub(r"\s+", "", value)
        vitamin_match = re.fullmatch(
            r"비타민([A-Za-z0-9]+)(?:제)?",
            compact,
            flags=re.IGNORECASE,
        )
        if vitamin_match:
            return f"비타민 {vitamin_match.group(1).upper()}"
        if compact.casefold() == "오메가3":
            return "오메가3"
        if compact.endswith("제") and compact[:-1] in cls._SUPPLEMENT_NAMES:
            return compact[:-1]
        return value

    @classmethod
    def _is_entity_candidate(
        cls,
        surface: str,
        canonical_name: str,
    ) -> bool:
        return bool(
            canonical_name
            and canonical_name not in cls._STOPWORDS
            and surface not in cls._STOPWORDS
            and not canonical_name.isdigit()
            and cls._NON_ENTITY_PREDICATE.fullmatch(canonical_name) is None
        )

    @classmethod
    def _entity_kind(cls, canonical_name: str) -> InteractionEntityKind:
        if cls._is_food(canonical_name):
            return InteractionEntityKind.FOOD
        if cls._is_supplement(canonical_name):
            return InteractionEntityKind.SUPPLEMENT
        return InteractionEntityKind.DRUG

    @classmethod
    def _entity_type(
        cls,
        canonical_name: str,
    ) -> MedicationQueryEntityType:
        if cls._is_food(canonical_name):
            return MedicationQueryEntityType.FOOD_CATEGORY
        if cls._MEDICATION_PRODUCT_CUE.search(canonical_name):
            return MedicationQueryEntityType.PRODUCT_NAME
        if canonical_name in cls._BRAND_ALIASES:
            return MedicationQueryEntityType.BRAND_ALIAS
        return MedicationQueryEntityType.INGREDIENT_NAME

    @classmethod
    def _candidate_types(
        cls,
        canonical_name: str,
    ) -> list[MedicationQueryEntityType]:
        if canonical_name in cls._BRAND_INGREDIENT_ALIASES:
            return [
                MedicationQueryEntityType.PRODUCT_NAME,
                MedicationQueryEntityType.BRAND_ALIAS,
                MedicationQueryEntityType.INGREDIENT_NAME,
            ]
        return [cls._entity_type(canonical_name)]

    @classmethod
    def _is_supplement(cls, canonical_name: str) -> bool:
        return canonical_name.startswith("비타민 ") or canonical_name in cls._SUPPLEMENT_NAMES

    @classmethod
    def _is_food(cls, canonical_name: str) -> bool:
        return canonical_name in cls._FOOD_EXACT_NAMES or canonical_name.endswith(cls._FOOD_SUFFIXES)


class MedicationKnowledgeQueryBuilder:
    _MEDICATION_PRODUCT_CUE = MedicationQueryEntityNormalizer._MEDICATION_PRODUCT_CUE
    _MAX_INTERACTION_PAIRS = 6
    _PAIR_TYPE_BY_KINDS = {
        frozenset({InteractionEntityKind.DRUG}): InteractionPairType.DRUG_DRUG,
        frozenset(
            {
                InteractionEntityKind.DRUG,
                InteractionEntityKind.SUPPLEMENT,
            }
        ): InteractionPairType.DRUG_SUPPLEMENT,
        frozenset({InteractionEntityKind.SUPPLEMENT}): InteractionPairType.SUPPLEMENT_SUPPLEMENT,
        frozenset(
            {
                InteractionEntityKind.DRUG,
                InteractionEntityKind.FOOD,
            }
        ): InteractionPairType.DRUG_FOOD,
    }
    _PAIR_TYPE_PRIORITY = {
        InteractionPairType.DRUG_DRUG: 0,
        InteractionPairType.DRUG_SUPPLEMENT: 1,
        InteractionPairType.DRUG_FOOD: 2,
        InteractionPairType.SUPPLEMENT_SUPPLEMENT: 3,
    }

    def __init__(self) -> None:
        self._entity_normalizer = MedicationQueryEntityNormalizer()

    def build(self, question: str) -> MedicationKnowledgeQueryPlan:
        normalized = question.strip()
        if not normalized:
            raise ValueError("약·영양제 검색 질문은 비어 있을 수 없습니다.")

        interaction_pair = find_supplement_interaction_pair(normalized)
        section_types, expansion_terms = self._intent(
            normalized,
            has_interaction_pair=interaction_pair is not None,
        )
        interaction_question = KnowledgeSectionType.INTERACTION in section_types
        entities = self._entity_normalizer.normalize(
            normalized,
            interaction_question=interaction_question,
        )
        search_expansion_terms = self._search_expansion_terms(
            entities=entities,
            section_types=section_types,
            default_terms=expansion_terms,
        )
        entity_names = [entity.canonical_name for entity in entities]
        interaction_pairs = self._interaction_pairs(entities) if interaction_question else []
        alternate_queries: list[str] = []
        if interaction_pair is not None:
            alternate_queries.append(interaction_pair.english_query)
        if len(interaction_pairs) > 1:
            alternate_queries.extend(f"{pair.left_name} {pair.right_name} 상호작용" for pair in interaction_pairs)
        elif interaction_pair is None and interaction_pairs:
            pair = interaction_pairs[0]
            alternate_queries.append(
                f"{pair.left_name} {pair.right_name} 상호작용",
            )
        elif (
            len(entities) == 1
            and entities[0].kind == InteractionEntityKind.DRUG
            and entities[0].entity_type == MedicationQueryEntityType.INGREDIENT_NAME
            and search_expansion_terms
        ):
            alternate_queries.extend(
                self._drug_section_queries(
                    entity_name=entities[0].canonical_name,
                    section_types=section_types,
                ),
            )
        expanded_query = " ".join(
            dict.fromkeys(
                [
                    normalized,
                    *entity_names,
                    *search_expansion_terms,
                ]
            )
        )
        return MedicationKnowledgeQueryPlan(
            original_query=normalized,
            expanded_query=expanded_query,
            entity_names=entity_names,
            entities=entities,
            section_types=section_types,
            alternate_queries=alternate_queries,
            interaction_pair=interaction_pair,
            interaction_pairs=interaction_pairs,
            interaction_types=list(dict.fromkeys(pair.pair_type for pair in interaction_pairs)),
            has_medication_product_cue=self._entity_normalizer.has_medication_product_cue(normalized),
        )

    @staticmethod
    def _search_expansion_terms(
        *,
        entities: list[MedicationQueryEntity],
        section_types: list[KnowledgeSectionType],
        default_terms: list[str],
    ) -> list[str]:
        if not (
            len(entities) == 1
            and entities[0].kind == InteractionEntityKind.DRUG
            and entities[0].entity_type == MedicationQueryEntityType.INGREDIENT_NAME
        ):
            return default_terms

        terms: list[str] = []
        if KnowledgeSectionType.FUNCTION in section_types:
            terms.extend(["효능", "효과"])
        if KnowledgeSectionType.DAILY_INTAKE in section_types:
            terms.extend(["용법", "용량"])
        if KnowledgeSectionType.CAUTION in section_types:
            terms.extend(["주의사항", "부작용"])
        return terms

    @staticmethod
    def _drug_section_queries(
        *,
        entity_name: str,
        section_types: list[KnowledgeSectionType],
    ) -> list[str]:
        section_terms = {
            KnowledgeSectionType.FUNCTION: ["효능", "효과"],
            KnowledgeSectionType.DAILY_INTAKE: ["용법", "용량"],
            KnowledgeSectionType.CAUTION: ["주의사항", "부작용"],
        }
        return [
            " ".join([entity_name, *section_terms[section_type]])
            for section_type in section_types
            if section_type in section_terms
        ]

    @classmethod
    def _interaction_pairs(
        cls,
        entities: list[MedicationQueryEntity],
    ) -> list[MedicationInteractionQueryPair]:
        pairs: list[MedicationInteractionQueryPair] = []
        for left_entity, right_entity in combinations(entities, 2):
            pair_type = cls._PAIR_TYPE_BY_KINDS.get(frozenset({left_entity.kind, right_entity.kind}))
            if pair_type is None:
                continue
            pairs.append(
                MedicationInteractionQueryPair(
                    left_name=left_entity.canonical_name,
                    right_name=right_entity.canonical_name,
                    pair_type=pair_type,
                )
            )
        return sorted(
            pairs,
            key=lambda pair: cls._PAIR_TYPE_PRIORITY[pair.pair_type],
        )[: cls._MAX_INTERACTION_PAIRS]

    @staticmethod
    def _intent(
        question: str,
        *,
        has_interaction_pair: bool = False,
    ) -> tuple[list[KnowledgeSectionType], list[str]]:
        if has_interaction_pair or is_interaction_question(question):
            return [KnowledgeSectionType.INTERACTION], ["상호작용", "병용 주의"]
        section_types: list[KnowledgeSectionType] = []
        expansion_terms: list[str] = []
        if any(keyword in question for keyword in ("효능", "효과", "기능", "왜 먹")):
            section_types.append(KnowledgeSectionType.FUNCTION)
            expansion_terms.extend(["건강기능식품", "기능성", "효능", "섭취 목적"])
        if any(
            keyword in question
            for keyword in (
                "하루",
                "얼마",
                "섭취량",
                "복용량",
                "용량",
                "복용법",
                "사용법",
                "복용하",
                "어떻게 먹",
            )
        ):
            section_types.append(KnowledgeSectionType.DAILY_INTAKE)
            expansion_terms.extend(["일일섭취량", "섭취 기준"])
        if any(keyword in question for keyword in ("주의", "부작용", "조심", "위험")):
            section_types.append(KnowledgeSectionType.CAUTION)
            expansion_terms.extend(["섭취 시 주의사항", "부작용"])
        return section_types, list(dict.fromkeys(expansion_terms))
