import re
from collections import defaultdict

from tortoise.expressions import Q

from ai_worker.schemas.medication_chat import (
    MedicationGuideFact,
    MedicationGuideLookup,
)
from app.models.interactions import MedicationProductGuide

# 공공자료 적재 과정에서 숫자 사이의 쉼표가 `|`로 바뀐 값이 있다(`4|000mg`).
# `|`는 조항 구분자로도 쓰이므로 세 자리 묶음일 때만 쉼표로 되돌린다.
# ai_worker의 모든 소비자가 이 저장소를 지나므로 읽는 지점에서 한 번만 정리한다.
_NUMERIC_SEPARATOR = re.compile(r"(?<=\d)\|(?=\d{3}(?:\D|$))")


def _restore_numeric_separator(value: str) -> str:
    return _NUMERIC_SEPARATOR.sub(",", value)


class DbMedicationProductGuideRepository:
    _INGREDIENT_SUFFIX = re.compile(r"\(([^()]+)\)\s*$")
    _DOSAGE_FORMS = (
        "정",
        "캡슐",
        "산",
        "과립",
        "시럽",
        "현탁액",
        "액",
    )

    async def find_by_name(
        self,
        product_name: str,
    ) -> MedicationGuideLookup:
        normalized_name = product_name.strip()
        if not normalized_name:
            return MedicationGuideLookup()

        exact_matches = await MedicationProductGuide.filter(
            product_name=normalized_name,
        ).order_by("id")
        if len(exact_matches) == 1:
            return MedicationGuideLookup(
                guide=self._to_fact(exact_matches[0]),
            )
        if len(exact_matches) > 1:
            return self._ambiguous(normalized_name, exact_matches)

        if "밀리그램" in normalized_name or "밀리그람" in normalized_name:
            spelling_variants = {
                normalized_name.replace("밀리그램", "밀리그람"),
                normalized_name.replace("밀리그람", "밀리그램"),
            }
            prefix_query = Q()
            for spelling in spelling_variants:
                prefix_query |= Q(product_name__istartswith=spelling)
            equivalent_matches = await (
                MedicationProductGuide.filter(prefix_query).order_by("product_name", "id").limit(6)
            )
            normalized_query = self._normalize_unit_spelling(normalized_name)
            equivalent = sorted(
                (
                    match
                    for match in equivalent_matches
                    if self._normalize_unit_spelling(match.product_name).startswith(normalized_query)
                ),
                key=lambda match: (match.product_name, match.id),
            )
            if len(equivalent) == 1:
                return MedicationGuideLookup(guide=self._to_fact(equivalent[0]))
            if len(equivalent) > 1:
                return self._ambiguous(normalized_name, equivalent)

        partial_matches = (
            await MedicationProductGuide.filter(
                product_name__icontains=normalized_name,
            )
            .order_by("product_name", "id")
            .limit(6)
        )
        if len(partial_matches) == 1:
            return MedicationGuideLookup(
                guide=self._to_fact(partial_matches[0]),
            )
        if len(partial_matches) > 1:
            return self._ambiguous(normalized_name, partial_matches)
        return MedicationGuideLookup()

    async def find_caution_guides_by_ingredient_names(
        self,
        ingredient_names: list[str],
    ) -> dict[str, list[MedicationGuideFact]]:
        """일반 성분 질문에 쓸 제형별 공식 제품 주의사항을 모은다."""

        normalized_names = list(dict.fromkeys(name.strip() for name in ingredient_names if name.strip()))
        matches_by_id: dict[int, MedicationProductGuide] = {}
        for ingredient_name in normalized_names:
            matches = await (
                MedicationProductGuide.filter(
                    product_name__icontains=ingredient_name,
                )
                .order_by("product_name", "id")
                .limit(12)
            )
            matches_by_id.update({guide.id: guide for guide in matches})

        guides_by_ingredient: dict[str, list[MedicationGuideFact]] = {
            ingredient_name: [] for ingredient_name in normalized_names
        }
        seen_cautions_by_ingredient: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
        for match in sorted(matches_by_id.values(), key=lambda guide: (guide.product_name, guide.id)):
            normalized_product_name = self._normalize_name(match.product_name)
            matching_ingredients = [
                ingredient_name
                for ingredient_name in normalized_names
                if self._normalize_name(ingredient_name) in normalized_product_name
            ]
            if not matching_ingredients:
                continue
            ingredient_name = max(matching_ingredients, key=lambda name: len(self._normalize_name(name)))
            fact = self._to_fact(match)
            caution_values = (
                fact.pre_use_warning.strip(),
                fact.precautions.strip(),
                fact.adverse_reactions.strip(),
            )
            if caution_values in seen_cautions_by_ingredient[ingredient_name]:
                continue
            seen_cautions_by_ingredient[ingredient_name].add(caution_values)
            if any(caution_values):
                guides_by_ingredient[ingredient_name].append(fact)

        return {ingredient_name: guides for ingredient_name, guides in guides_by_ingredient.items() if guides}

    @classmethod
    def _ambiguous(
        cls,
        query: str,
        matches: list[MedicationProductGuide],
    ) -> MedicationGuideLookup:
        return MedicationGuideLookup(
            representative_guide=(
                cls._family_reference(
                    query,
                    matches,
                )
            ),
            is_ambiguous=True,
            candidate_names=list(dict.fromkeys(match.product_name for match in matches)),
        )

    @classmethod
    def _family_reference(
        cls,
        query: str,
        matches: list[MedicationProductGuide],
    ) -> MedicationGuideFact | None:
        normalized_query = cls._normalize_name(query)
        ingredient_groups: dict[str, list[MedicationProductGuide]] = defaultdict(list)
        for match in matches:
            normalized_product = cls._normalize_name(match.product_name)
            if not normalized_product.startswith(normalized_query):
                continue
            ingredient_match = cls._INGREDIENT_SUFFIX.search(match.product_name)
            if ingredient_match is None:
                continue
            ingredient = cls._normalize_name(ingredient_match.group(1))
            ingredient_groups[ingredient].append(match)

        ranked_groups = sorted(
            ingredient_groups.values(),
            key=lambda group: (-len(group), group[0].product_name),
        )
        if not ranked_groups or len(ranked_groups[0]) < 2:
            return None
        if len(ranked_groups) > 1 and len(ranked_groups[0]) == len(ranked_groups[1]):
            return None

        representative = min(
            ranked_groups[0],
            key=lambda guide: cls._representative_rank(
                normalized_query,
                guide.product_name,
            ),
        )
        return cls._to_fact(representative)

    @classmethod
    def _representative_rank(
        cls,
        normalized_query: str,
        product_name: str,
    ) -> tuple[int, int, str]:
        normalized_product = cls._normalize_name(product_name)
        suffix = normalized_product[len(normalized_query) :]
        form_rank = next(
            (index for index, dosage_form in enumerate(cls._DOSAGE_FORMS) if suffix.startswith(dosage_form)),
            len(cls._DOSAGE_FORMS),
        )
        return form_rank, len(normalized_product), normalized_product

    @staticmethod
    def _normalize_name(value: str) -> str:
        return "".join(value.casefold().split())

    @classmethod
    def _normalize_unit_spelling(cls, value: str) -> str:
        return cls._normalize_name(value).replace("밀리그람", "밀리그램")

    @staticmethod
    def _to_fact(
        guide: MedicationProductGuide,
    ) -> MedicationGuideFact:
        restore = _restore_numeric_separator
        return MedicationGuideFact(
            medication_guide_id=guide.id,
            item_seq=guide.item_seq,
            product_name=guide.product_name,
            manufacturer_name=guide.manufacturer_name,
            efficacy=restore(guide.efficacy),
            usage_instructions=restore(guide.usage_instructions),
            pre_use_warning=restore(guide.pre_use_warning),
            precautions=restore(guide.precautions),
            drug_food_interactions=restore(guide.drug_food_interactions),
            adverse_reactions=restore(guide.adverse_reactions),
            storage_instructions=restore(guide.storage_instructions),
        )
