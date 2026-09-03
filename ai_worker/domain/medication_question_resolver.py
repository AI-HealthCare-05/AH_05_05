import re
import time
import unicodedata
from typing import NamedTuple, Protocol

from ai_worker.domain.medication_expression_vocabulary import (
    SUPPORTED_SUPPLEMENT_NAMES,
)
from ai_worker.schemas.medication_search import (
    MedicationExpressionCorrection,
    MedicationExpressionResolutionStatus,
    MedicationQuestionResolution,
    MedicationQuestionScope,
)


class MedicationExpressionCatalog(Protocol):
    async def list_expressions(self) -> list[str]: ...


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
    ) -> MedicationQuestionResolution:
        normalized_question = self._normalize_question(question)
        if self._GREETING_ONLY.fullmatch(normalized_question):
            return self._result(
                question=normalized_question,
                scope=MedicationQuestionScope.GREETING,
                status=MedicationExpressionResolutionStatus.UNCHANGED,
            )

        catalog_index = await self._base_catalog_index()
        additional_catalog = self._normalized_catalog(additional_names or [])
        if additional_catalog:
            catalog_index = self._extend_catalog_index(
                catalog_index,
                additional_catalog,
            )
        catalog = catalog_index.catalog

        tokens = self._question_tokens(normalized_question)
        spacing_resolution = self._spacing_resolution(
            question=normalized_question,
            catalog=catalog,
            tokens=tokens,
        )
        if spacing_resolution is not None:
            return spacing_resolution

        surfaces = self._candidate_surfaces(tokens)

        if self._contains_exact_expression(
            question=normalized_question,
            surfaces=surfaces,
            tokens=tokens,
            catalog=catalog,
        ):
            return self._result(
                question=normalized_question,
                scope=MedicationQuestionScope.IN_SCOPE,
                status=MedicationExpressionResolutionStatus.UNCHANGED,
            )

        prefix_candidates = self._ambiguous_prefix_candidates(
            surfaces=surfaces,
            catalog=catalog,
        )
        if prefix_candidates:
            return MedicationQuestionResolution(
                original_question=normalized_question,
                resolved_question=normalized_question,
                scope=MedicationQuestionScope.IN_SCOPE,
                status=(MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED),
                candidate_names=prefix_candidates,
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
                return MedicationQuestionResolution(
                    original_question=normalized_question,
                    resolved_question=resolved_question,
                    scope=MedicationQuestionScope.IN_SCOPE,
                    status=(MedicationExpressionResolutionStatus.AUTO_CORRECTED),
                    corrections=[
                        MedicationExpressionCorrection(
                            original=original,
                            replacement=replacement,
                        )
                    ],
                )

            clarification_candidates = sorted(
                {candidate for distance, _, candidate in ranked if distance <= best_distance + 1},
                key=str.casefold,
            )[:5]
            if maximum_distance is not None and clarification_candidates:
                return MedicationQuestionResolution(
                    original_question=normalized_question,
                    resolved_question=normalized_question,
                    scope=MedicationQuestionScope.IN_SCOPE,
                    status=(MedicationExpressionResolutionStatus.CLARIFICATION_REQUIRED),
                    candidate_names=clarification_candidates,
                )

        if self._is_domain_related(normalized_question):
            return self._result(
                question=normalized_question,
                scope=MedicationQuestionScope.IN_SCOPE,
                status=MedicationExpressionResolutionStatus.UNRESOLVED,
            )
        return self._result(
            question=normalized_question,
            scope=MedicationQuestionScope.OUT_OF_SCOPE,
            status=MedicationExpressionResolutionStatus.UNRESOLVED,
        )

    async def _base_catalog_index(self) -> _CatalogIndex:
        now = time.monotonic()
        if self._cached_catalog_index is not None and now < self._cache_expires_at:
            return self._cached_catalog_index
        expressions = [
            *(await self._catalog.list_expressions()),
            *SUPPORTED_SUPPLEMENT_NAMES,
        ]
        self._cached_catalog_index = self._build_catalog_index(self._normalized_catalog(expressions))
        self._cache_expires_at = now + self._cache_ttl_seconds
        return self._cached_catalog_index

    @classmethod
    def _build_catalog_index(
        cls,
        catalog: dict[str, str],
    ) -> _CatalogIndex:
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
            candidates_by_length=candidates_by_length,
            candidates_by_bigram=candidates_by_bigram,
        )

    @classmethod
    def _extend_catalog_index(
        cls,
        base: _CatalogIndex,
        additional_catalog: dict[str, str],
    ) -> _CatalogIndex:
        catalog = base.catalog.copy()
        catalog.update(additional_catalog)
        new_candidates = additional_catalog.keys() - base.catalog.keys()
        if not new_candidates:
            return _CatalogIndex(
                catalog=catalog,
                candidates_by_length=base.candidates_by_length,
                candidates_by_bigram=base.candidates_by_bigram,
            )

        candidates_by_length = base.candidates_by_length.copy()
        candidates_by_bigram = base.candidates_by_bigram.copy()
        copied_lengths: set[int] = set()
        copied_bigrams: set[str] = set()
        for normalized_candidate in new_candidates:
            candidate_length = len(normalized_candidate)
            if candidate_length not in copied_lengths:
                candidates_by_length[candidate_length] = set(candidates_by_length.get(candidate_length, ()))
                copied_lengths.add(candidate_length)
            candidates_by_length[candidate_length].add(normalized_candidate)

            for bigram in cls._bigrams(normalized_candidate):
                if bigram not in copied_bigrams:
                    candidates_by_bigram[bigram] = set(candidates_by_bigram.get(bigram, ()))
                    copied_bigrams.add(bigram)
                candidates_by_bigram[bigram].add(normalized_candidate)
        return _CatalogIndex(
            catalog=catalog,
            candidates_by_length=candidates_by_length,
            candidates_by_bigram=candidates_by_bigram,
        )

    @staticmethod
    def _normalize_question(value: str) -> str:
        normalized = unicodedata.normalize("NFC", value)
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _normalize_expression(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold()
        return re.sub(r"[\s\W_]+", "", normalized)

    @classmethod
    def _normalized_catalog(cls, expressions: list[str]) -> dict[str, str]:
        catalog: dict[str, str] = {}
        for expression in expressions:
            display_name = cls._normalize_question(expression)
            normalized = cls._normalize_expression(display_name)
            if not normalized:
                continue
            current = catalog.get(normalized)
            if current is None or display_name.casefold() < current.casefold():
                catalog[normalized] = display_name
        return catalog

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
        replacement = catalog.get(cls._normalize_expression(original))
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
        surface_keys = {cls._normalize_expression(surface) for surface in surfaces}
        if surface_keys.intersection(catalog):
            return True
        window_keys = {
            cls._normalize_expression(question[window[0].start : window[-1].end])
            for window in cls._token_windows(tokens)
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
    ) -> MedicationQuestionResolution:
        return MedicationQuestionResolution(
            original_question=question,
            resolved_question=question,
            scope=scope,
            status=status,
        )
