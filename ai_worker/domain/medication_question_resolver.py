import re
import time
import unicodedata
from collections import Counter
from typing import NamedTuple, Protocol

from ai_worker.domain.interaction_question_detector import is_interaction_question
from ai_worker.rag.metadata.supplement_ingredient_family_registry import (
    find_supplement_ingredient_family,
)
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.medication_search import (
    MedicationCatalogEntry,
    MedicationExpressionCorrection,
    MedicationExpressionNormalizationStrategy,
    MedicationExpressionResolutionStatus,
    MedicationQueryEntity,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
    MedicationQueryResolutionStatus,
    MedicationQuestionConfidence,
    MedicationQuestionResolution,
    MedicationQuestionScope,
    MedicationRelationResolutionStatus,
)


class MedicationExpressionCatalog(Protocol):
    async def list_expressions(self) -> list[str]: ...

    async def list_entries(self) -> list[MedicationCatalogEntry]: ...


class _QuestionToken(NamedTuple):
    start: int
    end: int
    surface: str


class _SpacingCorrection(NamedTuple):
    start: int
    end: int
    original: str
    replacement: str
    token_count: int


class _CatalogIndex(NamedTuple):
    catalog: dict[str, str]
    entries_by_expression: dict[str, tuple[MedicationCatalogEntry, ...]]
    all_entries: tuple[MedicationCatalogEntry, ...]
    candidates_by_length: dict[int, set[str]]
    candidates_by_bigram: dict[str, set[str]]


class RuleBasedMedicationQuestionResolver:
    """보유 어휘를 기준으로 질문 범위와 사용자 표현을 안전하게 해석한다."""

    _TOKEN = re.compile(
        r"[가-힣ㄱ-ㅎㅏ-ㅣᄀ-ᇿA-Za-z0-9]"
        r"[가-힣ㄱ-ㅎㅏ-ㅣᄀ-ᇿA-Za-z0-9.+-]*",
    )
    _TRAILING_PARTICLE = re.compile(
        r"(?:으로|에서|부터|까지|처럼|보다|에게|한테|하고|이며|이나|"
        r"이랑|랑|은|는|이|가|을|를|과|와|도|의|로)$",
    )
    _DOMAIN_CUE = re.compile(
        r"약|의약품|복약|복용|처방|영양제|건강기능식품|성분|함량|"
        r"부작용|상호작용|병용|금기|주의사항|섭취량|용법|용량|"
        r"임부|임신|수유|소아|노인",
    )
    _PRODUCT_FORM_CUE = re.compile(
        r"[가-힣A-Za-z0-9]+(?:정|캡슐|시럽|현탁액|연고|크림|패치|패취|주사)",
    )
    _FUZZY_CONTEXT_CUE = re.compile(
        r"효능|효과|기능|왜\s*먹|주의|부작용|복용|섭취|상호작용|"
        r"같이\s*먹|함께\s*먹|병용|용법|용량",
    )
    _GREETING_ONLY = re.compile(
        r"^(?:안녕(?:하세요|하십니까)?|반가워(?:요|습니다)?|하이|hello)[.!?~ ]*$",
        flags=re.IGNORECASE,
    )
    _RELATION_QUESTION_ENDING = re.compile(
        r"(?P<intake>[가-힣]{2,4}도)\s+(?P<ending>[대돼])(?P<punct>[?!]?)$",
    )
    _CANONICAL_RELATION_INTAKE = "먹어도"
    _CANONICAL_RELATION_ENDING = "돼"
    _RELATION_INTAKE_MAX_JAMO_DISTANCE = 2
    _TRAILING_PRODUCT_INGREDIENT = re.compile(r"\((?P<ingredient>[^()]+)\)\s*$")
    _NON_ENTITY_TOKENS = {
        "같이",
        "관련",
        "먹나요",
        "먹어",
        "먹어도",
        "먹을",
        "무엇",
        "어떤",
        "알려줘",
        "알려주세요",
        "영양제",
        "의약품",
        "주의사항",
        "효과",
        "효능",
        "복용",
        "복용법",
        "부작용",
        "상호작용",
        "섭취량",
        "오늘",
        "너무",
        "처음",
        "보는",
    }
    _SOURCE_PRIORITY = {
        MedicationQueryEntitySource.PATIENT_CONTEXT: 0,
        MedicationQueryEntitySource.SESSION_MEMORY: 1,
        MedicationQueryEntitySource.RDBMS: 2,
        MedicationQueryEntitySource.QDRANT: 3,
        MedicationQueryEntitySource.CATALOG: 4,
        MedicationQueryEntitySource.ALIAS: 5,
        MedicationQueryEntitySource.REGEX: 6,
    }
    _CONTEXTUAL_SOURCES = {
        MedicationQueryEntitySource.PATIENT_CONTEXT,
        MedicationQueryEntitySource.SESSION_MEMORY,
    }
    _PRODUCT_ENTITY_TYPES = {
        MedicationQueryEntityType.PRODUCT_NAME,
        MedicationQueryEntityType.BRAND_ALIAS,
    }
    _LATIN_LETTER_PRONUNCIATIONS = {
        "A": "에이",
        "B": "비",
        "C": "씨",
        "D": "디",
        "E": "이",
        "F": "에프",
        "G": "지",
        "H": "에이치",
        "I": "아이",
        "J": "제이",
        "K": "케이",
        "L": "엘",
        "M": "엠",
        "N": "엔",
        "O": "오",
        "P": "피",
        "Q": "큐",
        "R": "알",
        "S": "에스",
        "T": "티",
        "U": "유",
        "V": "브이",
        "W": "더블유",
        "X": "엑스",
        "Y": "와이",
        "Z": "지",
    }
    _LEAD_TO_TRAILING_INDEX = {
        0: 1,
        1: 2,
        2: 4,
        3: 7,
        5: 8,
        6: 16,
        7: 17,
        9: 19,
        10: 20,
        11: 21,
        12: 22,
        13: 23,
        14: 24,
        15: 25,
        16: 26,
        17: 27,
        18: 27,
    }

    def __init__(
        self,
        *,
        catalog: MedicationExpressionCatalog,
        cache_ttl_seconds: float = 300.0,
    ) -> None:
        self._catalog = catalog
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cached_catalog_index: _CatalogIndex | None = None
        self._cache_expires_at = 0.0

    async def resolve(
        self,
        *,
        question: str,
        additional_names: list[str] | None = None,
        additional_entities: list[MedicationCatalogEntry] | None = None,
    ) -> MedicationQuestionResolution:
        normalized_question = self._normalize_question(question)
        if self._GREETING_ONLY.fullmatch(normalized_question):
            return self._with_diagnostics(
                self._result(
                    question=normalized_question,
                    scope=MedicationQuestionScope.GREETING,
                    status=MedicationExpressionResolutionStatus.UNCHANGED,
                ),
                strategy=MedicationExpressionNormalizationStrategy.NONE,
                confidence=MedicationQuestionConfidence.LOW,
            )

        catalog_index = await self._base_catalog_index()
        additional_catalog_entries = [
            *(additional_entities or []),
            *self._legacy_entries(
                additional_names or [],
                source=MedicationQueryEntitySource.PATIENT_CONTEXT,
            ),
        ]
        if additional_catalog_entries:
            catalog_index = self._extend_catalog_index(
                catalog_index,
                additional_catalog_entries,
            )
        catalog = catalog_index.catalog

        tokens = self._question_tokens(normalized_question)
        spacing_resolution = self._spacing_resolution(
            question=normalized_question,
            catalog=catalog,
            tokens=tokens,
        )
        if spacing_resolution is not None:
            return self._with_diagnostics(
                self._with_matched_entities(
                    spacing_resolution,
                    catalog_index=catalog_index,
                ),
                catalog_index=catalog_index,
                strategy=self._spacing_strategy(spacing_resolution.corrections),
                confidence=MedicationQuestionConfidence.HIGH,
                shortlisted_candidate_count=1,
            )

        surfaces = self._candidate_surfaces(tokens)

        exact_resolution = self._exact_expression_resolution(
            question=normalized_question,
            surfaces=surfaces,
            tokens=tokens,
            catalog_index=catalog_index,
        )
        if exact_resolution is not None:
            return exact_resolution

        prefix_candidates = self._ambiguous_prefix_candidates(
            surfaces=self._prefix_candidate_surfaces(
                question=normalized_question,
                tokens=tokens,
                token_surfaces=surfaces,
            ),
            catalog=catalog,
        )
        if prefix_candidates:
            return self._with_diagnostics(
                MedicationQuestionResolution(
                    original_question=normalized_question,
                    resolved_question=normalized_question,
                    scope=MedicationQuestionScope.IN_SCOPE,
                    status=(MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED),
                    candidate_names=prefix_candidates,
                    entity_resolution_available=True,
                ),
                catalog_index=catalog_index,
                strategy=MedicationExpressionNormalizationStrategy.NONE,
                confidence=MedicationQuestionConfidence.MEDIUM,
                shortlisted_candidate_count=len(prefix_candidates),
                tie_count=len(prefix_candidates),
            )

        ranked = self._rank_candidates(
            surfaces=surfaces,
            catalog_index=catalog_index,
        )
        can_resolve_fuzzy = bool(
            self._is_domain_related(normalized_question)
            or self._FUZZY_CONTEXT_CUE.search(normalized_question)
            or self._is_high_confidence_standalone_typo(
                question=normalized_question,
                surfaces=surfaces,
                ranked=ranked,
            )
        )
        if ranked and can_resolve_fuzzy:
            best_distance, original, replacement = ranked[0]
            maximum_distance = self._auto_correct_distance(original)
            tied = [item for item in ranked if item[0] == best_distance]
            if (
                maximum_distance is not None
                and best_distance <= maximum_distance
                and len({item[2] for item in tied}) == 1
            ):
                resolved_question = normalized_question.replace(
                    original,
                    replacement,
                    1,
                )
                return self._with_diagnostics(
                    self._result_with_entities(
                        question=resolved_question,
                        original_question=normalized_question,
                        scope=MedicationQuestionScope.IN_SCOPE,
                        status=(MedicationExpressionResolutionStatus.AUTO_CORRECTED),
                        corrections=[
                            MedicationExpressionCorrection(
                                original=original,
                                replacement=replacement,
                            )
                        ],
                        catalog_index=catalog_index,
                    ),
                    catalog_index=catalog_index,
                    strategy=MedicationExpressionNormalizationStrategy.EDIT_DISTANCE,
                    confidence=MedicationQuestionConfidence.HIGH,
                    shortlisted_candidate_count=len(ranked),
                    tie_count=len({item[2] for item in tied}),
                )

            clarification_candidates = sorted(
                {candidate for distance, _, candidate in ranked if distance <= best_distance + 1},
                key=str.casefold,
            )[:5]
            if maximum_distance is not None and clarification_candidates:
                return self._with_diagnostics(
                    MedicationQuestionResolution(
                        original_question=normalized_question,
                        resolved_question=normalized_question,
                        scope=MedicationQuestionScope.IN_SCOPE,
                        status=(MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED),
                        candidate_names=clarification_candidates,
                        entity_resolution_available=True,
                    ),
                    catalog_index=catalog_index,
                    strategy=MedicationExpressionNormalizationStrategy.EDIT_DISTANCE,
                    confidence=MedicationQuestionConfidence.MEDIUM,
                    shortlisted_candidate_count=len(ranked),
                    tie_count=len(clarification_candidates),
                )

        if self._is_domain_related(normalized_question):
            return self._with_diagnostics(
                self._result(
                    question=normalized_question,
                    scope=MedicationQuestionScope.IN_SCOPE,
                    status=MedicationExpressionResolutionStatus.UNRESOLVED,
                    entity_resolution_available=True,
                ),
                catalog_index=catalog_index,
                strategy=MedicationExpressionNormalizationStrategy.NONE,
                confidence=MedicationQuestionConfidence.LOW,
            )
        return self._with_diagnostics(
            self._result(
                question=normalized_question,
                scope=MedicationQuestionScope.OUT_OF_SCOPE,
                status=MedicationExpressionResolutionStatus.UNRESOLVED,
                entity_resolution_available=True,
            ),
            catalog_index=catalog_index,
            strategy=MedicationExpressionNormalizationStrategy.NONE,
            confidence=MedicationQuestionConfidence.LOW,
        )

    async def _base_catalog_index(self) -> _CatalogIndex:
        now = time.monotonic()
        if self._cached_catalog_index is not None and now < self._cache_expires_at:
            return self._cached_catalog_index
        list_entries = getattr(self._catalog, "list_entries", None)
        if callable(list_entries):
            entries = await list_entries()
        else:
            entries = self._legacy_entries(await self._catalog.list_expressions())
        self._cached_catalog_index = self._build_catalog_index(entries)
        self._cache_expires_at = now + self._cache_ttl_seconds
        return self._cached_catalog_index

    @classmethod
    def _build_catalog_index(
        cls,
        entries: list[MedicationCatalogEntry],
    ) -> _CatalogIndex:
        entries_by_expression: dict[str, list[MedicationCatalogEntry]] = {}
        catalog: dict[str, str] = {}
        for entry in entries:
            for expression in entry.expressions:
                for normalized_expression in cls._expression_keys(expression):
                    catalog.setdefault(normalized_expression, expression)
                    entries_by_expression.setdefault(
                        normalized_expression,
                        [],
                    ).append(entry)

        normalized_entries = {
            key: tuple(
                sorted(
                    values,
                    key=cls._entry_selection_priority,
                )
            )
            for key, values in entries_by_expression.items()
        }
        candidates_by_length: dict[int, set[str]] = {}
        candidates_by_bigram: dict[str, set[str]] = {}
        for normalized_candidate in catalog:
            candidates_by_length.setdefault(
                len(normalized_candidate),
                set(),
            ).add(normalized_candidate)
            for bigram in cls._bigrams(normalized_candidate):
                candidates_by_bigram.setdefault(bigram, set()).add(
                    normalized_candidate,
                )
        return _CatalogIndex(
            catalog=catalog,
            entries_by_expression=normalized_entries,
            all_entries=tuple(entries),
            candidates_by_length=candidates_by_length,
            candidates_by_bigram=candidates_by_bigram,
        )

    @classmethod
    def _entry_selection_priority(
        cls,
        entry: MedicationCatalogEntry,
    ) -> tuple[int, int, str]:
        """동일 표현의 후보를 제품·성분 의미에 따라 일관되게 고른다."""
        if entry.source in cls._CONTEXTUAL_SOURCES:
            category_priority = 0
        elif entry.entity_type in cls._PRODUCT_ENTITY_TYPES:
            category_priority = 1
        elif entry.kind == InteractionEntityKind.SUPPLEMENT:
            category_priority = 2
        else:
            category_priority = 3
        return (
            category_priority,
            cls._SOURCE_PRIORITY[entry.source],
            entry.canonical_name.casefold(),
        )

    @classmethod
    def _extend_catalog_index(
        cls,
        base: _CatalogIndex,
        additional_entries: list[MedicationCatalogEntry],
    ) -> _CatalogIndex:
        return cls._build_catalog_index(
            [*base.all_entries, *additional_entries],
        )

    @staticmethod
    def _normalize_question(value: str) -> str:
        normalized = unicodedata.normalize("NFC", value)
        return re.sub(r"\s+", " ", normalized).strip()

    @classmethod
    def _normalize_expression(cls, value: str) -> str:
        normalized = cls._compose_compatibility_jamo(value).casefold()
        return re.sub(r"[\s\W_]+", "", normalized)

    @classmethod
    def _expression_keys(cls, value: str) -> tuple[str, ...]:
        composed = cls._compose_compatibility_jamo(value)
        keys = [cls._normalize_expression(composed)]
        pronunciation_form = re.sub(
            r"[A-Za-z]",
            lambda match: cls._LATIN_LETTER_PRONUNCIATIONS[match.group().upper()],
            composed,
        )
        keys.append(cls._normalize_expression(pronunciation_form))
        return tuple(key for key in dict.fromkeys(keys) if key)

    @classmethod
    def _compose_compatibility_jamo(cls, value: str) -> str:
        """호환 자모를 완성형 음절로 조합해 catalog 비교 키에만 사용한다."""
        # NFKC는 호환 자모를 현대 자모로 바꾸지만, 앞 음절만 부분 조합할 수
        # 있다. NFD로 다시 풀어 한 번의 동일한 조합 규칙을 적용한다.
        normalized = unicodedata.normalize(
            "NFD",
            unicodedata.normalize("NFKC", value),
        )
        result: list[str] = []
        index = 0
        while index < len(normalized):
            lead = ord(normalized[index]) - 0x1100
            if not (0 <= lead <= 18) or index + 1 >= len(normalized):
                result.append(normalized[index])
                index += 1
                continue
            vowel = ord(normalized[index + 1]) - 0x1161
            if not (0 <= vowel <= 20):
                result.append(normalized[index])
                index += 1
                continue

            index += 2
            trailing = 0
            if index < len(normalized):
                trailing_lead = ord(normalized[index]) - 0x1100
                next_is_vowel = index + 1 < len(normalized) and 0 <= ord(normalized[index + 1]) - 0x1161 <= 20
                if not next_is_vowel:
                    trailing = cls._LEAD_TO_TRAILING_INDEX.get(trailing_lead, 0)
                    if trailing:
                        index += 1
            result.append(chr(0xAC00 + ((lead * 21) + vowel) * 28 + trailing))
        return unicodedata.normalize("NFC", "".join(result))

    @classmethod
    def _legacy_entries(
        cls,
        expressions: list[str],
        *,
        source: MedicationQueryEntitySource = MedicationQueryEntitySource.CATALOG,
    ) -> list[MedicationCatalogEntry]:
        """구형 테스트 더블을 위한 호환 계층이다.

        실제 서비스에서는 `list_entries()`가 DB·Qdrant의 실제 타입을
        제공하므로 이 경로를 사용하지 않는다.
        """
        return [
            MedicationCatalogEntry(
                canonical_name=cls._normalize_question(expression),
                entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                kind=InteractionEntityKind.DRUG,
                source=source,
            )
            for expression in expressions
            if cls._normalize_question(expression)
        ]

    @classmethod
    def _result_with_entities(
        cls,
        *,
        question: str,
        scope: MedicationQuestionScope,
        status: MedicationExpressionResolutionStatus,
        catalog_index: _CatalogIndex,
        original_question: str | None = None,
        corrections: list[MedicationExpressionCorrection] | None = None,
    ) -> MedicationQuestionResolution:
        return MedicationQuestionResolution(
            original_question=original_question or question,
            resolved_question=question,
            scope=scope,
            status=status,
            corrections=corrections or [],
            entity_resolution_available=True,
            entities=cls._matched_entities(
                question=question,
                catalog_index=catalog_index,
            ),
        )

    @classmethod
    def _ingredient_family_resolution(
        cls,
        *,
        question: str,
        surfaces: list[str],
        catalog_index: _CatalogIndex,
    ) -> MedicationQuestionResolution | None:
        for surface in surfaces:
            family = find_supplement_ingredient_family(surface)
            if family is None:
                continue
            return cls._with_diagnostics(
                MedicationQuestionResolution(
                    original_question=question,
                    resolved_question=question,
                    scope=MedicationQuestionScope.IN_SCOPE,
                    status=MedicationExpressionResolutionStatus.UNCHANGED,
                    entity_resolution_available=True,
                    entities=[
                        MedicationQueryEntity(
                            surface=surface,
                            canonical_name=family.canonical_name,
                            entity_type=(MedicationQueryEntityType.INGREDIENT_FAMILY),
                            kind=InteractionEntityKind.SUPPLEMENT,
                            source=MedicationQueryEntitySource.CATALOG,
                        )
                    ],
                ),
                catalog_index=catalog_index,
                strategy=MedicationExpressionNormalizationStrategy.EXACT,
                confidence=MedicationQuestionConfidence.HIGH,
                shortlisted_candidate_count=1,
            )
        return None

    @classmethod
    def _with_matched_entities(
        cls,
        resolution: MedicationQuestionResolution,
        *,
        catalog_index: _CatalogIndex,
    ) -> MedicationQuestionResolution:
        return resolution.model_copy(
            update={
                "entity_resolution_available": True,
                "entities": cls._matched_entities(
                    question=resolution.resolved_question,
                    catalog_index=catalog_index,
                ),
            }
        )

    @classmethod
    def _with_diagnostics(
        cls,
        resolution: MedicationQuestionResolution,
        *,
        catalog_index: _CatalogIndex | None = None,
        strategy: MedicationExpressionNormalizationStrategy,
        confidence: MedicationQuestionConfidence,
        shortlisted_candidate_count: int = 0,
        tie_count: int = 0,
        relation_resolution_status: MedicationRelationResolutionStatus = (
            MedicationRelationResolutionStatus.NOT_APPLICABLE
        ),
    ) -> MedicationQuestionResolution:
        source_counts: Counter[str] = Counter()
        type_counts: Counter[str] = Counter()
        if catalog_index is not None:
            source_counts.update(entry.source.value for entry in catalog_index.all_entries)
            type_counts.update(entry.entity_type.value for entry in catalog_index.all_entries)
        return resolution.model_copy(
            update={
                "normalization_strategy": strategy,
                "confidence_tier": confidence,
                "shortlisted_candidate_count": shortlisted_candidate_count,
                "tie_count": tie_count,
                "relation_resolution_status": relation_resolution_status,
                "catalog_source_counts": dict(sorted(source_counts.items())),
                "catalog_type_counts": dict(sorted(type_counts.items())),
            }
        )

    @classmethod
    def _relation_expression_resolution(
        cls,
        *,
        question: str,
        catalog_index: _CatalogIndex,
    ) -> MedicationQuestionResolution | None:
        """두 source-backed 대상 뒤의 짧은 병용 질문 오타만 보정한다."""

        match = cls._RELATION_QUESTION_ENDING.search(question)
        if match is None:
            return None

        typed_entities = [
            entity
            for entity in cls._matched_entities(
                question=question,
                catalog_index=catalog_index,
            )
            if entity.kind is not None
        ]
        if len({(entity.canonical_name, entity.kind) for entity in typed_entities}) < 2:
            return None

        intake = match.group("intake")
        intake_distance = cls._edit_distance(
            unicodedata.normalize("NFD", intake),
            unicodedata.normalize("NFD", cls._CANONICAL_RELATION_INTAKE),
            limit=cls._RELATION_INTAKE_MAX_JAMO_DISTANCE,
        )
        if intake_distance > cls._RELATION_INTAKE_MAX_JAMO_DISTANCE:
            return None

        ending = match.group("ending")
        if intake == cls._CANONICAL_RELATION_INTAKE and ending == cls._CANONICAL_RELATION_ENDING:
            return None

        replacement = f"{cls._CANONICAL_RELATION_INTAKE} {cls._CANONICAL_RELATION_ENDING}{match.group('punct')}"
        original = match.group(0)
        resolved_question = f"{question[: match.start()]}{replacement}"
        return cls._with_diagnostics(
            cls._result_with_entities(
                question=resolved_question,
                original_question=question,
                scope=MedicationQuestionScope.IN_SCOPE,
                status=MedicationExpressionResolutionStatus.AUTO_CORRECTED,
                corrections=[
                    MedicationExpressionCorrection(
                        original=original,
                        replacement=replacement,
                    )
                ],
                catalog_index=catalog_index,
            ),
            catalog_index=catalog_index,
            strategy=MedicationExpressionNormalizationStrategy.RELATION_CUE,
            confidence=MedicationQuestionConfidence.HIGH,
            shortlisted_candidate_count=2,
            relation_resolution_status=(MedicationRelationResolutionStatus.AUTO_CORRECTED),
        )

    @classmethod
    def _exact_expression_resolution(
        cls,
        *,
        question: str,
        surfaces: list[str],
        tokens: list[_QuestionToken],
        catalog_index: _CatalogIndex,
    ) -> MedicationQuestionResolution | None:
        ingredient_family_resolution = cls._ingredient_family_resolution(
            question=question,
            surfaces=cls._prefix_candidate_surfaces(
                question=question,
                tokens=tokens,
                token_surfaces=surfaces,
            ),
            catalog_index=catalog_index,
        )
        if ingredient_family_resolution is not None:
            return ingredient_family_resolution
        if not cls._contains_exact_expression(
            question=question,
            surfaces=surfaces,
            tokens=tokens,
            catalog=catalog_index.catalog,
        ):
            return None
        if candidates := cls._ambiguous_product_supplement_candidates(
            question=question,
            tokens=tokens,
            catalog_index=catalog_index,
        ):
            return cls._with_diagnostics(
                MedicationQuestionResolution(
                    original_question=question,
                    resolved_question=question,
                    scope=MedicationQuestionScope.IN_SCOPE,
                    status=(MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED),
                    candidate_names=candidates,
                    entity_resolution_available=True,
                ),
                catalog_index=catalog_index,
                strategy=MedicationExpressionNormalizationStrategy.EXACT,
                confidence=MedicationQuestionConfidence.MEDIUM,
                shortlisted_candidate_count=len(candidates),
                tie_count=len(candidates),
            )
        relation_resolution = cls._relation_expression_resolution(
            question=question,
            catalog_index=catalog_index,
        )
        if relation_resolution is not None:
            return relation_resolution
        entities = cls._matched_entities(
            question=question,
            catalog_index=catalog_index,
        )
        return cls._with_diagnostics(
            cls._result_with_entities(
                question=question,
                scope=MedicationQuestionScope.IN_SCOPE,
                status=MedicationExpressionResolutionStatus.UNCHANGED,
                catalog_index=catalog_index,
            ),
            catalog_index=catalog_index,
            strategy=cls._exact_match_strategy(
                question=question,
                catalog_index=catalog_index,
            ),
            confidence=MedicationQuestionConfidence.HIGH,
            shortlisted_candidate_count=len(entities),
            relation_resolution_status=(
                MedicationRelationResolutionStatus.UNCHANGED
                if len(entities) >= 2
                else MedicationRelationResolutionStatus.NOT_APPLICABLE
            ),
        )

    @classmethod
    def _ambiguous_product_supplement_candidates(
        cls,
        *,
        question: str,
        tokens: list[_QuestionToken],
        catalog_index: _CatalogIndex,
    ) -> list[str]:
        """같은 표현이 제품과 영양성분 모두를 뜻할 때만 확인을 요청한다."""
        matches = cls._matching_spans(
            question=question,
            tokens=tokens,
            catalog_index=catalog_index,
        )
        occupied_until = -1
        for start, end, key in sorted(
            matches,
            key=lambda item: (item[0], -(item[1] - item[0]), item[2]),
        ):
            if start < occupied_until:
                continue
            occupied_until = end
            entries = catalog_index.entries_by_expression[key]
            if any(entry.source in cls._CONTEXTUAL_SOURCES for entry in entries):
                continue
            products = [entry for entry in entries if entry.entity_type in cls._PRODUCT_ENTITY_TYPES]
            supplements = [entry for entry in entries if entry.kind == InteractionEntityKind.SUPPLEMENT]
            if not products or not supplements:
                continue
            return list(
                dict.fromkeys(
                    [
                        *(f"{entry.canonical_name} (의약품 제품)" for entry in products),
                        *(f"{entry.canonical_name} (영양성분)" for entry in supplements),
                    ]
                )
            )
        return []

    @classmethod
    def _exact_match_strategy(
        cls,
        *,
        question: str,
        catalog_index: _CatalogIndex,
    ) -> MedicationExpressionNormalizationStrategy:
        tokens = cls._question_tokens(question)
        for start, end, key in cls._matching_spans(
            question=question,
            tokens=tokens,
            catalog_index=catalog_index,
        ):
            surface = question[start:end]
            composed_surface = cls._compose_compatibility_jamo(surface)
            for entry in catalog_index.entries_by_expression[key]:
                for expression in entry.expressions:
                    if cls._normalize_expression(expression) == key:
                        if composed_surface != unicodedata.normalize("NFC", surface):
                            return MedicationExpressionNormalizationStrategy.COMPATIBILITY_JAMO
                        return MedicationExpressionNormalizationStrategy.EXACT
                    pronunciation = re.sub(
                        r"[A-Za-z]",
                        lambda match: cls._LATIN_LETTER_PRONUNCIATIONS[match.group().upper()],
                        expression,
                    )
                    if cls._normalize_expression(pronunciation) == key:
                        return MedicationExpressionNormalizationStrategy.LETTER_PRONUNCIATION
        return MedicationExpressionNormalizationStrategy.EXACT

    @classmethod
    def _spacing_strategy(
        cls,
        corrections: list[MedicationExpressionCorrection],
    ) -> MedicationExpressionNormalizationStrategy:
        for correction in corrections:
            original_key = cls._normalize_expression(correction.original)
            replacement_key = cls._normalize_expression(correction.replacement)
            pronunciation = re.sub(
                r"[A-Za-z]",
                lambda match: cls._LATIN_LETTER_PRONUNCIATIONS[match.group().upper()],
                correction.replacement,
            )
            if original_key != replacement_key and cls._normalize_expression(pronunciation) == original_key:
                return MedicationExpressionNormalizationStrategy.LETTER_PRONUNCIATION
            if cls._compose_compatibility_jamo(correction.original) != unicodedata.normalize(
                "NFC",
                correction.original,
            ):
                return MedicationExpressionNormalizationStrategy.COMPATIBILITY_JAMO
        return MedicationExpressionNormalizationStrategy.SPACING

    @classmethod
    def _matched_entities(
        cls,
        *,
        question: str,
        catalog_index: _CatalogIndex,
    ) -> list[MedicationQueryEntity]:
        tokens = cls._question_tokens(question)
        matches = cls._matching_spans(
            question=question,
            tokens=tokens,
            catalog_index=catalog_index,
        )

        selected_matches: list[tuple[int, int, str]] = []
        occupied_until = -1
        for start, end, key in sorted(matches, key=lambda item: (item[0], -(item[1] - item[0]), item[2])):
            if start < occupied_until:
                continue
            selected_matches.append((start, end, key))
            occupied_until = end

        entities: list[MedicationQueryEntity] = []
        seen: set[tuple[str, str]] = set()
        for start, end, key in selected_matches:
            candidates = catalog_index.entries_by_expression[key]
            canonical_names = {candidate.canonical_name for candidate in candidates}
            candidate_types = list(dict.fromkeys(candidate.entity_type for candidate in candidates))
            selected = cls._select_candidate_for_question(
                question=question,
                candidates=candidates,
            )
            effective_candidate = cls._interaction_ingredient_candidate(
                question=question,
                selected=selected,
                catalog_index=catalog_index,
            )
            if effective_candidate != selected:
                canonical_names = {effective_candidate.canonical_name}
                candidate_types = [effective_candidate.entity_type]
            dedupe_key = (
                effective_candidate.canonical_name.casefold(),
                effective_candidate.kind.value if effective_candidate.kind else "TOPIC",
            )
            if dedupe_key in seen:
                continue
            entities.append(
                MedicationQueryEntity(
                    surface=question[start:end],
                    canonical_name=effective_candidate.canonical_name,
                    search_aliases=list(
                        dict.fromkeys(
                            [*selected.expressions, *effective_candidate.expressions],
                        )
                    ),
                    product_lookup_name=(
                        selected.canonical_name
                        if (
                            selected.entity_type in cls._PRODUCT_ENTITY_TYPES
                            and selected.kind == InteractionEntityKind.DRUG
                        )
                        else None
                    ),
                    entity_type=effective_candidate.entity_type,
                    candidate_types=candidate_types,
                    kind=effective_candidate.kind,
                    source=effective_candidate.source,
                    resolution_status=(
                        MedicationQueryResolutionStatus.AMBIGUOUS
                        if len(canonical_names) > 1 or len(candidate_types) > 1
                        else MedicationQueryResolutionStatus.RESOLVED
                    ),
                )
            )
            seen.add(dedupe_key)
        return entities

    @classmethod
    def _select_candidate_for_question(
        cls,
        *,
        question: str,
        candidates: tuple[MedicationCatalogEntry, ...],
    ) -> MedicationCatalogEntry:
        """상호작용 질문에서 source-backed 음식 분류를 우선한다."""
        if is_interaction_question(question):
            for candidate in candidates:
                if candidate.kind == InteractionEntityKind.FOOD:
                    return candidate
        return candidates[0]

    @classmethod
    def _interaction_ingredient_candidate(
        cls,
        *,
        question: str,
        selected: MedicationCatalogEntry,
        catalog_index: _CatalogIndex,
    ) -> MedicationCatalogEntry:
        """제품명 끝의 검증된 성분명만 상호작용 검색 대상으로 바꾼다."""
        if (
            not is_interaction_question(question)
            or selected.entity_type not in cls._PRODUCT_ENTITY_TYPES
            or selected.kind != InteractionEntityKind.DRUG
        ):
            return selected

        match = cls._TRAILING_PRODUCT_INGREDIENT.search(selected.canonical_name)
        if match is None:
            return selected
        ingredient_key = cls._normalize_expression(match.group("ingredient"))
        if not ingredient_key:
            return selected

        for candidate in catalog_index.all_entries:
            if (
                candidate.entity_type == MedicationQueryEntityType.INGREDIENT_NAME
                and candidate.kind == InteractionEntityKind.DRUG
                and cls._normalize_expression(candidate.canonical_name) == ingredient_key
            ):
                return candidate
        return selected

    @classmethod
    def _matching_spans(
        cls,
        *,
        question: str,
        tokens: list[_QuestionToken],
        catalog_index: _CatalogIndex,
    ) -> list[tuple[int, int, str]]:
        candidates = [(token.start, token.end, token.surface) for token in tokens]
        candidates.extend(
            (
                window[0].start,
                window[-1].end,
                question[window[0].start : window[-1].end],
            )
            for window in cls._token_windows(tokens)
        )
        return [
            (start, end, key)
            for start, end, surface in candidates
            for key in cls._expression_keys(surface)
            if key in catalog_index.entries_by_expression
        ]

    @classmethod
    def _question_tokens(cls, question: str) -> list[_QuestionToken]:
        tokens: list[_QuestionToken] = []
        for match in cls._TOKEN.finditer(question):
            surface = match.group()
            previous = ""
            while previous != surface:
                previous = surface
                surface = cls._TRAILING_PARTICLE.sub("", surface)
            if surface:
                tokens.append(
                    _QuestionToken(
                        start=match.start(),
                        end=match.start() + len(surface),
                        surface=surface,
                    )
                )
        return tokens

    @classmethod
    def _candidate_surfaces(
        cls,
        tokens: list[_QuestionToken],
    ) -> list[str]:
        return list(dict.fromkeys(token.surface for token in tokens if token.surface not in cls._NON_ENTITY_TOKENS))

    @classmethod
    def _prefix_candidate_surfaces(
        cls,
        *,
        question: str,
        tokens: list[_QuestionToken],
        token_surfaces: list[str],
    ) -> list[str]:
        """공유 접두어 판정에서는 가장 구체적인 연속 표현을 먼저 검사한다."""
        phrases = [
            question[window[0].start : window[-1].end]
            for window in cls._token_windows(tokens)
            if all(token.surface not in cls._NON_ENTITY_TOKENS for token in window)
        ]
        longest_first = sorted(
            dict.fromkeys(phrases),
            key=lambda value: (-len(cls._normalize_expression(value)), value.casefold()),
        )
        return list(dict.fromkeys([*longest_first, *token_surfaces]))

    @classmethod
    def _spacing_corrections(
        cls,
        *,
        question: str,
        catalog: dict[str, str],
        tokens: list[_QuestionToken],
    ) -> list[_SpacingCorrection]:
        matches = [
            correction
            for window in cls._token_windows(tokens)
            if (
                correction := cls._spacing_correction_for_window(
                    question=question,
                    catalog=catalog,
                    window=window,
                )
            )
            is not None
        ]

        selected: list[_SpacingCorrection] = []
        occupied_until = -1
        for correction in sorted(
            matches,
            key=lambda item: (item.start, -item.token_count, item.end),
        ):
            if correction.start < occupied_until:
                continue
            selected.append(correction)
            occupied_until = correction.end
        return selected

    @classmethod
    def _spacing_resolution(
        cls,
        *,
        question: str,
        catalog: dict[str, str],
        tokens: list[_QuestionToken],
    ) -> MedicationQuestionResolution | None:
        corrections = cls._spacing_corrections(
            question=question,
            catalog=catalog,
            tokens=tokens,
        )
        if not corrections:
            return None

        resolved_question = question
        for correction in reversed(corrections):
            resolved_question = (
                resolved_question[: correction.start] + correction.replacement + resolved_question[correction.end :]
            )
        return MedicationQuestionResolution(
            original_question=question,
            resolved_question=resolved_question,
            scope=MedicationQuestionScope.IN_SCOPE,
            status=MedicationExpressionResolutionStatus.AUTO_CORRECTED,
            corrections=[
                MedicationExpressionCorrection(
                    original=correction.original,
                    replacement=correction.replacement,
                )
                for correction in corrections
            ],
        )

    @staticmethod
    def _token_windows(
        tokens: list[_QuestionToken],
    ) -> list[list[_QuestionToken]]:
        return [
            tokens[start_index:end_index]
            for start_index in range(len(tokens))
            for end_index in range(start_index + 2, min(start_index + 4, len(tokens)) + 1)
        ]

    @classmethod
    def _spacing_correction_for_window(
        cls,
        *,
        question: str,
        catalog: dict[str, str],
        window: list[_QuestionToken],
    ) -> _SpacingCorrection | None:
        start = window[0].start
        end = window[-1].end
        original = question[start:end]
        if not re.search(r"\s", original):
            return None
        replacement = next(
            (catalog[key] for key in cls._expression_keys(original) if key in catalog),
            None,
        )
        if replacement is None or replacement == original:
            return None
        return _SpacingCorrection(
            start=start,
            end=end,
            original=original,
            replacement=replacement,
            token_count=len(window),
        )

    @classmethod
    def _contains_exact_expression(
        cls,
        *,
        question: str,
        surfaces: list[str],
        tokens: list[_QuestionToken],
        catalog: dict[str, str],
    ) -> bool:
        surface_keys = {key for surface in surfaces for key in cls._expression_keys(surface)}
        if surface_keys.intersection(catalog):
            return True
        window_keys = {
            key
            for window in cls._token_windows(tokens)
            for key in cls._expression_keys(
                question[window[0].start : window[-1].end],
            )
        }
        return bool(window_keys.intersection(catalog))

    @classmethod
    def _rank_candidates(
        cls,
        *,
        surfaces: list[str],
        catalog_index: _CatalogIndex,
    ) -> list[tuple[int, str, str]]:
        ranked: list[tuple[int, str, str]] = []
        for surface in surfaces:
            normalized_surface = cls._normalize_expression(surface)
            maximum_distance = cls._auto_correct_distance(surface)
            if maximum_distance is None:
                continue

            surface_ranked = cls._rank_surface_candidates(
                surface=surface,
                normalized_surface=normalized_surface,
                catalog=catalog_index.catalog,
                candidates_by_length=(catalog_index.candidates_by_length),
                candidates_by_bigram=(catalog_index.candidates_by_bigram),
                limit=maximum_distance,
            )
            if not surface_ranked and maximum_distance < 3:
                surface_ranked = cls._rank_surface_candidates(
                    surface=surface,
                    normalized_surface=normalized_surface,
                    catalog=catalog_index.catalog,
                    candidates_by_length=(catalog_index.candidates_by_length),
                    candidates_by_bigram=(catalog_index.candidates_by_bigram),
                    limit=maximum_distance + 1,
                )
            ranked.extend(surface_ranked)
        return sorted(
            set(ranked),
            key=lambda item: (
                item[0],
                abs(len(cls._normalize_expression(item[1])) - len(cls._normalize_expression(item[2]))),
                item[2].casefold(),
            ),
        )

    @classmethod
    def _rank_surface_candidates(
        cls,
        *,
        surface: str,
        normalized_surface: str,
        catalog: dict[str, str],
        candidates_by_length: dict[int, set[str]],
        candidates_by_bigram: dict[str, set[str]],
        limit: int,
    ) -> list[tuple[int, str, str]]:
        candidate_keys = cls._shortlisted_candidate_keys(
            normalized_surface=normalized_surface,
            candidates_by_length=candidates_by_length,
            candidates_by_bigram=candidates_by_bigram,
            limit=limit,
        )
        ranked: list[tuple[int, str, str]] = []
        for normalized_candidate in candidate_keys:
            distance = cls._edit_distance(
                normalized_surface,
                normalized_candidate,
                limit=limit,
            )
            if distance > limit:
                continue
            similarity = 1 - distance / max(
                len(normalized_surface),
                len(normalized_candidate),
            )
            if similarity < 0.6:
                continue
            ranked.append(
                (
                    distance,
                    surface,
                    catalog[normalized_candidate],
                )
            )
        return ranked

    @classmethod
    def _shortlisted_candidate_keys(
        cls,
        *,
        normalized_surface: str,
        candidates_by_length: dict[int, set[str]],
        candidates_by_bigram: dict[str, set[str]],
        limit: int,
    ) -> set[str]:
        surface_length = len(normalized_surface)
        shared_bigram_candidates: set[str] = set()
        for bigram in cls._bigrams(normalized_surface):
            shared_bigram_candidates.update(
                candidates_by_bigram.get(bigram, ()),
            )

        shortlisted: set[str] = set()
        for candidate_length in range(
            max(1, surface_length - limit),
            surface_length + limit + 1,
        ):
            length_candidates = candidates_by_length.get(
                candidate_length,
                set(),
            )
            guaranteed_shared_bigram_count = max(surface_length, candidate_length) - 1 - 2 * limit
            if guaranteed_shared_bigram_count <= 0:
                shortlisted.update(length_candidates)
            else:
                shortlisted.update(
                    length_candidates.intersection(
                        shared_bigram_candidates,
                    )
                )
        return shortlisted

    @staticmethod
    def _bigrams(value: str) -> set[str]:
        return {value[index : index + 2] for index in range(len(value) - 1)}

    @classmethod
    def _ambiguous_prefix_candidates(
        cls,
        *,
        surfaces: list[str],
        catalog: dict[str, str],
    ) -> list[str]:
        for surface in surfaces:
            normalized_surface = cls._normalize_expression(surface)
            if len(normalized_surface) < 2:
                continue
            candidates = sorted(
                {
                    display_name
                    for normalized_candidate, display_name in catalog.items()
                    if normalized_candidate != normalized_surface
                    and normalized_candidate.startswith(normalized_surface)
                },
                key=str.casefold,
            )
            if len(candidates) >= 2:
                return candidates[:5]
        return []

    @staticmethod
    def _auto_correct_distance(surface: str) -> int | None:
        length = len(RuleBasedMedicationQuestionResolver._normalize_expression(surface))
        if length <= 2:
            return None
        if length <= 5:
            return 1
        return 2

    @classmethod
    def _is_high_confidence_standalone_typo(
        cls,
        *,
        question: str,
        surfaces: list[str],
        ranked: list[tuple[int, str, str]],
    ) -> bool:
        if len(surfaces) != 1 or not ranked:
            return False
        surface = surfaces[0]
        if question.strip(".!?~ ") != surface:
            return False
        distance, _, candidate = ranked[0]
        maximum_distance = cls._auto_correct_distance(surface)
        normalized_surface = cls._normalize_expression(surface)
        normalized_candidate = cls._normalize_expression(candidate)
        return bool(
            maximum_distance is not None
            and distance <= maximum_distance
            and len(normalized_surface) >= 4
            and normalized_surface[0] == normalized_candidate[0]
            and normalized_surface[-1] == normalized_candidate[-1]
        )

    @staticmethod
    def _edit_distance(left: str, right: str, *, limit: int) -> int:
        if abs(len(left) - len(right)) > limit:
            return limit + 1
        previous = list(range(len(right) + 1))
        for left_index, left_character in enumerate(left, start=1):
            current = [left_index]
            row_minimum = left_index
            for right_index, right_character in enumerate(right, start=1):
                current.append(
                    min(
                        current[-1] + 1,
                        previous[right_index] + 1,
                        previous[right_index - 1] + (left_character != right_character),
                    )
                )
                row_minimum = min(row_minimum, current[-1])
            if row_minimum > limit:
                return limit + 1
            previous = current
        return previous[-1]

    @classmethod
    def _is_domain_related(cls, question: str) -> bool:
        return bool(cls._DOMAIN_CUE.search(question) or cls._PRODUCT_FORM_CUE.search(question))

    @staticmethod
    def _result(
        *,
        question: str,
        scope: MedicationQuestionScope,
        status: MedicationExpressionResolutionStatus,
        entity_resolution_available: bool = False,
    ) -> MedicationQuestionResolution:
        return MedicationQuestionResolution(
            original_question=question,
            resolved_question=question,
            scope=scope,
            status=status,
            entity_resolution_available=entity_resolution_available,
        )
