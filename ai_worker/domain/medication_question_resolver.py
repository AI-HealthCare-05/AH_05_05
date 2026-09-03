import re
import time
import unicodedata
from typing import Protocol

from ai_worker.schemas.medication_search import (
    MedicationExpressionCorrection,
    MedicationExpressionResolutionStatus,
    MedicationQuestionResolution,
    MedicationQuestionScope,
)


class MedicationExpressionCatalog(Protocol):
    async def list_expressions(self) -> list[str]: ...


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
        self._cached_catalog: dict[str, str] | None = None
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

        catalog = (await self._base_catalog()).copy()
        catalog.update(
            self._normalized_catalog(additional_names or []),
        )
        surfaces = self._candidate_surfaces(normalized_question)

        if self._contains_exact_expression(
            question=normalized_question,
            surfaces=surfaces,
            catalog=catalog,
        ):
            return self._result(
                question=normalized_question,
                scope=MedicationQuestionScope.IN_SCOPE,
                status=MedicationExpressionResolutionStatus.UNCHANGED,
            )

        ranked = self._rank_candidates(surfaces=surfaces, catalog=catalog)
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

    async def _base_catalog(self) -> dict[str, str]:
        now = time.monotonic()
        if self._cached_catalog is not None and now < self._cache_expires_at:
            return self._cached_catalog
        expressions = await self._catalog.list_expressions()
        self._cached_catalog = self._normalized_catalog(expressions)
        self._cache_expires_at = now + self._cache_ttl_seconds
        return self._cached_catalog

    @staticmethod
    def _normalize_question(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
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
    def _candidate_surfaces(cls, question: str) -> list[str]:
        surfaces: list[str] = []
        for match in cls._TOKEN.finditer(question):
            surface = match.group()
            previous = ""
            while previous != surface:
                previous = surface
                surface = cls._TRAILING_PARTICLE.sub("", surface)
            if len(cls._normalize_expression(surface)) >= 1 and surface not in cls._NON_ENTITY_TOKENS:
                surfaces.append(surface)
        return list(dict.fromkeys(surfaces))

    @classmethod
    def _contains_exact_expression(
        cls,
        *,
        question: str,
        surfaces: list[str],
        catalog: dict[str, str],
    ) -> bool:
        surface_keys = {cls._normalize_expression(surface) for surface in surfaces}
        if surface_keys.intersection(catalog):
            return True
        return any(
            " " in display_name
            and re.search(
                r"(?<![가-힣ㄱ-ㅎㅏ-ㅣA-Za-z0-9])"
                + r"\s*".join(re.escape(part) for part in display_name.split())
                + r"(?![가-힣ㄱ-ㅎㅏ-ㅣA-Za-z0-9])",
                question,
                flags=re.IGNORECASE,
            )
            is not None
            for display_name in catalog.values()
        )

    @classmethod
    def _rank_candidates(
        cls,
        *,
        surfaces: list[str],
        catalog: dict[str, str],
    ) -> list[tuple[int, str, str]]:
        ranked: list[tuple[int, str, str]] = []
        for surface in surfaces:
            normalized_surface = cls._normalize_expression(surface)
            if len(normalized_surface) < 3:
                continue
            for normalized_candidate, display_name in catalog.items():
                length_gap = abs(len(normalized_surface) - len(normalized_candidate))
                if length_gap > 3:
                    continue
                distance = cls._edit_distance(
                    normalized_surface,
                    normalized_candidate,
                    limit=3,
                )
                if distance > 3:
                    continue
                similarity = 1 - distance / max(
                    len(normalized_surface),
                    len(normalized_candidate),
                )
                if similarity < 0.6:
                    continue
                ranked.append((distance, surface, display_name))
        return sorted(
            set(ranked),
            key=lambda item: (
                item[0],
                abs(len(cls._normalize_expression(item[1])) - len(cls._normalize_expression(item[2]))),
                item[2].casefold(),
            ),
        )

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
