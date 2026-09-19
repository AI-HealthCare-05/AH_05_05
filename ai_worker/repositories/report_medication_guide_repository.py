import asyncio
import re
import unicodedata
from difflib import SequenceMatcher, get_close_matches
from typing import Protocol

from ai_worker.domain.medication_question_resolver import RuleBasedMedicationQuestionResolver
from ai_worker.repositories.medication_expression_catalog_repository import DbMedicationExpressionCatalog
from ai_worker.repositories.medication_product_guide_repository import DbMedicationProductGuideRepository
from ai_worker.schemas.medication_chat import MedicationGuideFact, MedicationGuideLookup
from ai_worker.schemas.medication_search import MedicationCatalogEntry


class MedicationCandidateSelector(Protocol):
    async def select(self, *, query: str, candidates: list[MedicationGuideFact]) -> int | None: ...


class ReportMedicationGuideRepository(DbMedicationProductGuideRepository):
    """보정은 보고서 조회에만 사용하고, 미확정 후보를 제품 근거로 승격하지 않는다."""

    # Ranking scores are string similarities, not probabilities of drug identity.
    # Brand-only scores avoid inflating matches with common strength/form suffixes.
    _DIRECT_TYPO_SCORE = 0.88
    _ASSISTED_TYPO_SCORE = 0.75
    _MIN_RUNNER_UP_MARGIN = 0.12
    _FULLWIDTH_ASCII = str.maketrans({chr(code): chr(code - 0xFEE0) for code in range(0xFF01, 0xFF5F)})
    _UNIT_ALIASES = {
        "밀리그램": "mg",
        "밀리그람": "mg",
        "mg": "mg",
        "마이크로그램": "mcg",
        "마이크로그람": "mcg",
        "mcg": "mcg",
        "μg": "mcg",
        "µg": "mcg",
        "그램": "g",
        "그람": "g",
        "g": "g",
        "밀리리터": "ml",
        "ml": "ml",
    }
    _STRENGTH = re.compile(
        r"(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)(?P<unit>밀리그램|밀리그람|마이크로그램|마이크로그람|그램|그람|mg|mcg|μg|µg|g|ml|밀리리터)"
    )
    # The shared chat catalog deliberately has a smaller vocabulary. Reports
    # must parse the dosage forms present in product-guide registrations too.
    _REPORT_DOSAGE_FORM_BOUNDARY = re.compile(
        r"(?:카타플라스마|점안액|점이액|점비액|구강붕해정|연질캡슐|경질캡슐|현탁액|서방정|장용정|"
        r"플라스타|스프레이|시럽|과립|캡슐|패취|패치|연고|크림|겔|젤|산|정|액)(?=\d|$)"
    )
    _IDENTITY_QUALIFIER = re.compile(
        r"(?:대|중|소|대형|중형|소형|1회용|일회용|다회용|수출용|"
        r"소아용|성인용|유아용|어린이용|대환|소환|향|[가-힣]+(?:향|맛))"
    )
    _ANNOTATION_STRENGTH = re.compile(
        r"\d+(?:[.,]\d+)?\s*(?:%|밀리그램|밀리그람|마이크로그램|마이크로그람|그램|그람|mg|mcg|μg|µg|g|ml|밀리리터)"
    )

    def __init__(self, *, candidate_selector: MedicationCandidateSelector | None = None) -> None:
        # Identity dominance must include products added since the last report.
        # The separate resolver index may cache suggestions, never auto-binding.
        self._catalog = DbMedicationExpressionCatalog(product_names_only=True, cache_ttl_seconds=0)
        self._resolver = RuleBasedMedicationQuestionResolver(catalog=self._catalog)
        self._resolution_lock = asyncio.Lock()
        self._candidate_selector = candidate_selector
        self._selector_slots = asyncio.Semaphore(3)

    async def find_by_name(self, product_name: str) -> MedicationGuideLookup:
        query = product_name.strip()
        if len(self._normalize_name(query)) < 2 or len(query) > 256:
            return MedicationGuideLookup()
        direct = await super().find_by_name(query)
        if direct.guide is not None and query == direct.guide.product_name.strip():
            return direct

        # Use one fresh product snapshot for the identity ranking in this lookup.
        async with self._resolution_lock:
            entries = await self._catalog.list_entries()

        catalog_match = await self._find_catalog_product(query, entries)
        if catalog_match is not None:
            return catalog_match

        ranked = self._rank_products(query, entries)
        selected = await self._select_dominant(query, ranked)
        if selected is not None:
            return selected

        async with self._resolution_lock:
            resolution = await self._resolver.resolve(question=query)
        candidates = list(direct.candidate_names)
        if direct.guide is not None:
            candidates.append(direct.guide.product_name)
        candidates.extend(name for score, name in ranked[:5] if score >= self._ASSISTED_TYPO_SCORE)
        suggested = set(resolution.candidate_names)
        if resolution.resolved_question != query:
            suggested.add(resolution.resolved_question)
        # Hangul syllable distance can miss two vowel typos (타이래늘).
        # Compare decomposed characters only for suggestions, NEVER identity binding.
        if not candidates and not suggested and len(self._normalize_name(query)) >= 4:
            keys = {self._suggestion_key(name): name for entry in entries for name in entry.expressions}
            suggested.update(
                keys[key]
                for key in get_close_matches(
                    self._suggestion_key(query),
                    keys,
                    n=5,
                    cutoff=0.75,
                )
            )
        candidates.extend(
            entry.canonical_name
            for entry in entries
            if any(expression in suggested for expression in entry.expressions)
        )
        find_by_name = super().find_by_name
        lookups = await asyncio.gather(*(find_by_name(suggestion) for suggestion in sorted(suggested)[:5]))
        for lookup in lookups:
            candidates.extend(lookup.candidate_names)
            if lookup.guide is not None:
                candidates.append(lookup.guide.product_name)
        candidates = self._safe_candidate_names(query, candidates, entries)
        return MedicationGuideLookup(
            is_ambiguous=bool(candidates),
            candidate_names=candidates,
            original_name=query if candidates else None,
        )

    async def _find_catalog_product(
        self, query: str, entries: list[MedicationCatalogEntry]
    ) -> MedicationGuideLookup | None:
        names = {
            entry.canonical_name
            for entry in entries
            if any(
                self._matches_product_name(query, alias)
                for alias in [entry.canonical_name, *self._product_aliases(entry.canonical_name)]
            )
        }
        if len(names) > 1:
            return MedicationGuideLookup(is_ambiguous=True, candidate_names=sorted(names), original_name=query)
        if names:
            # Equivalent spelling is identity, not a fuzzy correction. Keep the
            # exact product lookup's duplicate-ID guard and the registered name.
            return await super().find_by_name(next(iter(names)))
        return await self._find_truncated_unit_product(query, entries)

    async def _find_truncated_unit_product(
        self, query: str, entries: list[MedicationCatalogEntry]
    ) -> MedicationGuideLookup | None:
        # OCR may persist a printed ellipsis. Never complete a brand, a numeric
        # strength, a decimal, or a formulation from a merely similar product.
        match = re.fullmatch(r"(.+)(?:\.{3}|…)", self._normalize_name(query))
        if match is None:
            return None
        prefix = match[1]
        names = {
            entry.canonical_name
            for entry in entries
            if self._split_annotations(entry.canonical_name)[0].startswith(prefix)
        }
        if len(names) != 1:
            return None
        name = next(iter(names))
        product, _ = self._split_annotations(name)
        _, query_annotations = self._split_annotations(query)
        _, candidate_annotations = self._split_annotations(name)
        if not self._annotations_compatible(query_annotations, candidate_annotations):
            return None
        cut_inside_final_unit = any(
            strength.end() == len(product) and strength.start("unit") <= len(prefix) <= strength.end()
            for strength in self._STRENGTH.finditer(product)
        )
        if not cut_inside_final_unit or self._product_parts(name) is None:
            return None
        lookup = await super().find_by_name(name)
        if lookup.guide is None or lookup.is_ambiguous:
            return None
        return lookup.model_copy(update={"original_name": query, "is_inferred": True})

    @classmethod
    def _rank_products(cls, query: str, entries: list[MedicationCatalogEntry]) -> list[tuple[float, str]]:
        query_parts = cls._product_parts(query, allow_unknown_form=True)
        if query_parts is None or not 2 <= len(query_parts[0]) <= 64:
            return []
        query_brand = cls._suggestion_key(query_parts[0])
        ranked = []
        for name in {entry.canonical_name for entry in entries}:
            parts = cls._product_parts(name)
            if parts is None or len(parts[0]) > 64 or not cls._safe_product_correction(query, name):
                continue
            score = SequenceMatcher(None, query_brand, cls._suggestion_key(parts[0]), autojunk=False).ratio()
            ranked.append((score, name))
        return sorted(ranked, key=lambda item: (-item[0], item[1]))

    async def _select_dominant(self, query: str, ranked: list[tuple[float, str]]) -> MedicationGuideLookup | None:
        if not ranked:
            return None
        score, name = ranked[0]
        runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
        if score < self._ASSISTED_TYPO_SCORE or score - runner_up < self._MIN_RUNNER_UP_MARGIN:
            return None
        query_parts = self._product_parts(query, allow_unknown_form=True)
        product_parts = self._product_parts(name)
        assert query_parts is not None and product_parts is not None
        requires_form_check = self._product_parts(query) is None
        requires_identity_check = (
            requires_form_check or len(query_parts[0]) < 4 or not self._STRENGTH.search(query_parts[1])
        )
        if (requires_identity_check and self._has_close_brand_alternative(query_parts[0], ranked[1:])) or (
            requires_form_check and score < self._DIRECT_TYPO_SCORE
        ):
            return None
        if (
            RuleBasedMedicationQuestionResolver._edit_distance(
                self._suggestion_key(query_parts[0]), self._suggestion_key(product_parts[0]), limit=2
            )
            > 2
        ):
            return None
        lookup = await super().find_by_name(name)
        if (
            lookup.guide is None
            or lookup.is_ambiguous
            or not self._matches_product_name(name, lookup.guide.product_name)
        ):
            return None
        if score < self._DIRECT_TYPO_SCORE or requires_identity_check:
            if self._candidate_selector is None:
                return None
            try:
                # Queueing is inside the budget too; many registered drugs must
                # not turn a five-second optional check into an unbounded wait.
                async with asyncio.timeout(5.0):
                    find_by_name = super().find_by_name
                    alternatives = await asyncio.gather(*(find_by_name(other) for _, other in ranked[1:5]))
                    candidates = [
                        lookup.guide,
                        *[
                            alternative.guide
                            for alternative in alternatives
                            if alternative.guide is not None
                            and not alternative.is_ambiguous
                            and self._safe_product_correction(query, alternative.guide.product_name)
                        ],
                    ]
                    async with self._selector_slots:
                        selected_id = await self._candidate_selector.select(query=query, candidates=candidates)
            except Exception:
                return None
            if type(selected_id) is not int or selected_id != lookup.guide.medication_guide_id:
                return None
        return lookup.model_copy(update={"original_name": query, "is_inferred": score < 1.0 or requires_form_check})

    @classmethod
    def _has_close_brand_alternative(cls, brand: str, alternatives: list[tuple[float, str]]) -> bool:
        # Sparse identity must not be settled by a similarity margin or an LLM
        # when another compatible product is also within the typo edit budget.
        query_key = cls._suggestion_key(brand)
        return any(
            parts is not None
            and RuleBasedMedicationQuestionResolver._edit_distance(query_key, cls._suggestion_key(parts[0]), limit=2)
            <= 2
            for _, name in alternatives
            for parts in [cls._product_parts(name)]
        )

    @classmethod
    def _matches_product_name(cls, query: str, product_name: str) -> bool:
        normalized_query = unicodedata.normalize("NFC", query).translate(cls._FULLWIDTH_ASCII)
        normalized_product = unicodedata.normalize("NFC", product_name).translate(cls._FULLWIDTH_ASCII)
        # A DB row may retain several independently named alternatives in one
        # field. Compare each complete alias, never a fragment of a compound
        # query (which could make a changed dose look equivalent).
        if cls._normalize_name(normalized_query) == cls._normalize_name(normalized_product):
            return True
        query_aliases = cls._product_aliases(normalized_query)
        candidate_aliases = cls._product_aliases(normalized_product)
        if len(query_aliases) > 1:
            if len(candidate_aliases) != len(query_aliases):
                return False
            unmatched = list(candidate_aliases)
            for query_alias in query_aliases:
                match_index = next(
                    (
                        index
                        for index, candidate_alias in enumerate(unmatched)
                        if cls._matches_product_name(query_alias, candidate_alias)
                    ),
                    None,
                )
                if match_index is None:
                    return False
                unmatched.pop(match_index)
            return not unmatched
        if len(candidate_aliases) > 1:
            return any(cls._matches_product_name(normalized_query, alias) for alias in candidate_aliases)
        query_name, query_annotations = cls._split_annotations(normalized_query)
        candidate_name, candidate_annotations = cls._split_annotations(normalized_product)
        if not query_name or not candidate_name:
            return False
        return cls._unit_spelling_key(query_name) == cls._unit_spelling_key(
            candidate_name
        ) and cls._annotations_compatible(query_annotations, candidate_annotations)

    @classmethod
    def _annotations_compatible(
        cls, query_annotations: tuple[str, ...], candidate_annotations: tuple[str, ...]
    ) -> bool:
        """Compare identity metadata while allowing an omitted ingredient suffix.

        Ingredients are explanatory metadata and have historically been
        optional in report lookups. Qualifiers and unclassified metadata are
        identity-bearing: an absent or different qualifier must not bind a
        singleton product by a partial DB query or fuzzy fallback.
        """

        query_identity = tuple(
            (cls._annotation_kind(annotation), cls._normalize_name(annotation))
            for annotation in query_annotations
            if cls._annotation_kind(annotation) != "ingredient"
        )
        candidate_identity = tuple(
            (cls._annotation_kind(annotation), cls._normalize_name(annotation))
            for annotation in candidate_annotations
            if cls._annotation_kind(annotation) != "ingredient"
        )
        if query_identity != candidate_identity:
            return False

        candidate_ingredients = {
            cls._normalize_name(annotation)
            for annotation in candidate_annotations
            if cls._annotation_kind(annotation) == "ingredient"
        }
        return all(
            cls._normalize_name(annotation) in candidate_ingredients
            for annotation in query_annotations
            if cls._annotation_kind(annotation) == "ingredient"
        )

    @classmethod
    def _annotation_kind(cls, annotation: str) -> str:
        normalized = cls._normalize_name(annotation)
        if cls._IDENTITY_QUALIFIER.fullmatch(normalized):
            return "qualifier"
        # Labels, nested alternatives, and strength-bearing metadata are not
        # safe to treat as optional ingredients.
        if (
            any(delimiter in annotation for delimiter in (":", "|", "/"))
            or cls._STRENGTH.search(annotation)
            or cls._ANNOTATION_STRENGTH.search(annotation)
        ):
            return "identity"
        return "ingredient"

    @classmethod
    def _unit_spelling_key(cls, value: str) -> str:
        # Only unit spellings are equivalent; never convert doses or forms.
        def replace(match: re.Match[str]) -> str:
            whole, _, fraction = match["amount"].replace(",", "").partition(".")
            whole = whole.lstrip("0") or "0"
            fraction = fraction.rstrip("0")
            amount = whole + (f".{fraction}" if fraction else "")
            return amount + cls._UNIT_ALIASES[match["unit"]]

        return cls._STRENGTH.sub(replace, value)

    @classmethod
    def _safe_product_correction(cls, original: str, corrected: str) -> bool:
        original_key, original_annotations = cls._split_annotations(original)
        corrected_key, corrected_annotations = cls._split_annotations(corrected)
        if cls._matches_product_name(original, corrected):
            return True
        original_parts = cls._product_parts(original, allow_unknown_form=True)
        corrected_parts = cls._product_parts(corrected)
        return bool(
            original_parts
            and corrected_parts
            and (
                original_parts[1] == corrected_parts[1]
                or (
                    cls._product_parts(original) is None
                    and original_parts[1][1:] == corrected_parts[1][1:]
                    and RuleBasedMedicationQuestionResolver._edit_distance(
                        cls._suggestion_key(original_parts[1][0]),
                        cls._suggestion_key(corrected_parts[1][0]),
                        limit=1,
                    )
                    == 1
                )
            )
            and cls._annotations_compatible(original_annotations, corrected_annotations)
            # Do not add/drop a whole product variant suffix such as Q/ER.
            and not original_parts[0].startswith(corrected_parts[0])
            and not corrected_parts[0].startswith(original_parts[0])
            and re.findall(r"\d+(?:\.\d+)?", cls._unit_spelling_key(original_key))
            == re.findall(r"\d+(?:\.\d+)?", cls._unit_spelling_key(corrected_key))
        )

    @classmethod
    def _safe_candidate_names(
        cls,
        query: str,
        candidates: list[str],
        entries: list[MedicationCatalogEntry],
    ) -> list[str]:
        """제품 구조가 충분한 입력에서는 후보에도 같은 안전 경계를 적용한다."""

        unique_candidates = list(dict.fromkeys(name for name in candidates if name.strip()))
        _, query_annotations = cls._split_annotations(query)
        if any(cls._annotation_kind(annotation) != "ingredient" for annotation in query_annotations):
            return [candidate for candidate in unique_candidates if cls._safe_product_correction(query, candidate)]
        query_parts = cls._product_parts(query, allow_unknown_form=True)
        if query_parts is None or not cls._has_explicit_product_structure(query_parts[1]):
            return unique_candidates

        query_brand = cls._normalize_ingredient_name(query_parts[0])
        known_ingredients = {
            ingredient for entry in entries for ingredient in cls._ingredient_names(entry.canonical_name)
        }
        query_is_known_ingredient = any(
            cls._ingredient_matches(query_brand, ingredient) for ingredient in known_ingredients
        )
        return [
            candidate
            for candidate in unique_candidates
            if cls._safe_product_correction(query, candidate)
            and (
                not query_is_known_ingredient
                or any(
                    cls._ingredient_matches(query_brand, ingredient) for ingredient in cls._ingredient_names(candidate)
                )
            )
        ]

    @classmethod
    def _has_explicit_product_structure(cls, suffix: str) -> bool:
        return bool(cls._STRENGTH.search(suffix) or len(re.findall(r"\d+(?:\.\d+)?", suffix)) > 1)

    @classmethod
    def _ingredient_names(cls, product_name: str) -> tuple[str, ...]:
        _, annotations = cls._split_annotations(product_name)
        return tuple(
            normalized
            for annotation in annotations
            if cls._annotation_kind(annotation) == "ingredient"
            for normalized in [cls._normalize_ingredient_name(annotation)]
            if len(normalized) >= 3
        )

    @classmethod
    def _normalize_ingredient_name(cls, value: str) -> str:
        return re.sub(r"[^가-힣a-z0-9]", "", cls._normalize_name(value))

    @staticmethod
    def _ingredient_matches(query_brand: str, ingredient: str) -> bool:
        return len(query_brand) >= 3 and ingredient.startswith(query_brand)

    @classmethod
    def _product_parts(cls, name: str, *, allow_unknown_form: bool = False) -> tuple[str, str, tuple[str, ...]] | None:
        product, annotations = cls._split_annotations(name)
        form = cls._REPORT_DOSAGE_FORM_BOUNDARY.search(product)
        form_start = form.start() if form is not None else None
        if form_start is None and allow_unknown_form:
            strength = cls._STRENGTH.search(product)
            if strength is not None and strength.start() > 0:
                index = strength.start() - 1
                if re.fullmatch(r"[가-힣]", product[index]):
                    form_start = index
        if form_start is None:
            return None
        # Normalize equivalent unit spellings only, never convert amounts or forms.
        suffix = cls._unit_spelling_key(product[form_start:])
        return product[:form_start], suffix, annotations

    @classmethod
    def _split_annotations(cls, name: str) -> tuple[str, tuple[str, ...]]:
        product = cls._normalize_name(unicodedata.normalize("NFC", name).translate(cls._FULLWIDTH_ASCII))
        annotations: list[str] = []
        while product:
            export_start = cls._trailing_balanced_block_start(product)
            if export_start is not None and product[-1] in "}]":
                export_metadata = product[export_start + 1 : -1]
                if export_metadata.startswith("수출명:"):
                    product = product[:export_start]
                    continue

            if not product.endswith(")"):
                break
            annotation_start = cls._trailing_balanced_block_start(product)
            if annotation_start is None:
                break  # Malformed metadata is not silently discarded.
            annotation = product[annotation_start + 1 : -1]
            if annotation.startswith("수출명:"):
                product = product[:annotation_start]
                continue
            annotations.insert(0, annotation)
            product = product[:annotation_start]
        return product, tuple(annotations)

    @classmethod
    def _product_aliases(cls, name: str) -> list[str]:
        """Return independently named, top-level pipe alternatives.

        Product ingredients, export names, and flavor text may contain pipes
        inside balanced blocks. Number prefixes are stripped only for a
        complete sequential list (``1. ... | 2. ...``); malformed lists stay
        literal so they cannot accidentally become an identity alias.
        """

        parts = cls._split_top_level_pipe(name)
        if len(parts) <= 1:
            return [name.strip()]
        numbered = [re.fullmatch(r"(\d+)\.\s*(.+)", part.strip()) for part in parts]
        if any(numbered):
            if not all(numbered) or [int(match.group(1)) for match in numbered if match] != list(
                range(1, len(parts) + 1)
            ):
                return [name.strip()]
            parts = [match.group(2).strip() for match in numbered if match]
        if any(not part for part in parts):
            return [name.strip()]
        return list(dict.fromkeys(parts))

    @staticmethod
    def _split_top_level_pipe(value: str) -> list[str]:
        pairs = {")": "(", "]": "[", "}": "{"}
        openers = set(pairs.values())
        stack: list[str] = []
        parts: list[str] = []
        start = 0
        for index, char in enumerate(value):
            if char in openers:
                stack.append(char)
            elif char in pairs:
                if not stack or stack.pop() != pairs[char]:
                    return [value.strip()]
            elif char == "|" and not stack:
                parts.append(value[start:index].strip())
                start = index + 1
        if stack:
            return [value.strip()]
        parts.append(value[start:].strip())
        return parts

    @staticmethod
    def _trailing_balanced_block_start(value: str) -> int | None:
        if not value or value[-1] not in ")]}":
            return None
        pairs = {")": "(", "]": "[", "}": "{"}
        openers = set(pairs.values())
        stack: list[str] = []
        for index in range(len(value) - 1, -1, -1):
            char = value[index]
            if char in pairs:
                stack.append(char)
            elif char in openers:
                if not stack or pairs[stack[-1]] != char:
                    return None
                stack.pop()
                if not stack:
                    return index
        return None

    @classmethod
    def _suggestion_key(cls, value: str) -> str:
        return unicodedata.normalize("NFD", cls._normalize_name(value))
