import asyncio
import re
import time
from itertools import chain

from ai_worker.domain.interfaces import SupplementIngredientCatalog
from app.models.interactions import (
    InteractionEntity,
    InteractionEntityAlias,
    MedicationProductGuide,
)
from app.models.supplement_nutrients import SupplementNutrient


class DbMedicationExpressionCatalog:
    """질문 해석에 사용할 제품명·성분명·별칭을 DB에서 제공한다."""

    _INGREDIENT_SUFFIX = re.compile(r"\([^()]+\)\s*$")
    _DOSAGE_FORM_BOUNDARY = re.compile(
        r"(?:구강붕해정|연질캡슐|경질캡슐|현탁액|서방정|장용정|"
        r"시럽|과립|캡슐|정|산|액)(?=\d|$)",
    )

    def __init__(
        self,
        *,
        cache_ttl_seconds: float = 300.0,
        supplement_catalog: SupplementIngredientCatalog | None = None,
    ) -> None:
        self._cache_ttl_seconds = cache_ttl_seconds
        self._supplement_catalog = supplement_catalog
        self._cached_expressions: list[str] | None = None
        self._cache_expires_at = 0.0

    async def list_expressions(self) -> list[str]:
        now = time.monotonic()
        if self._cached_expressions is not None and now < self._cache_expires_at:
            return self._cached_expressions.copy()

        product_names, entity_names, aliases, supplement_names, additional_names = await asyncio.gather(
            MedicationProductGuide.all().values_list(
                "product_name",
                flat=True,
            ),
            InteractionEntity.all().values_list(
                "canonical_name",
                flat=True,
            ),
            InteractionEntityAlias.all().values_list(
                "alias",
                flat=True,
            ),
            SupplementNutrient.all().values_list(
                "name",
                flat=True,
            ),
            self._list_additional_names(),
        )
        product_expressions = [
            expression for product_name in product_names for expression in self._product_expressions(str(product_name))
        ]
        expressions = sorted(
            {
                str(value).strip()
                for value in chain(
                    product_expressions,
                    entity_names,
                    aliases,
                    supplement_names,
                    additional_names,
                )
                if str(value).strip()
            },
            key=str.casefold,
        )
        self._cached_expressions = expressions
        self._cache_expires_at = now + self._cache_ttl_seconds
        return expressions.copy()

    async def _list_additional_names(self) -> list[str]:
        if self._supplement_catalog is None:
            return []
        return await self._supplement_catalog.list_names()

    @classmethod
    def _product_expressions(cls, product_name: str) -> list[str]:
        full_name = product_name.strip()
        if not full_name:
            return []
        name_without_ingredient = cls._INGREDIENT_SUFFIX.sub("", full_name).strip()
        dosage_form = cls._DOSAGE_FORM_BOUNDARY.search(name_without_ingredient)
        if dosage_form is None:
            return list(dict.fromkeys([full_name, name_without_ingredient]))
        family_name = name_without_ingredient[: dosage_form.start()].rstrip(" -")
        if len(family_name) < 2:
            return list(dict.fromkeys([full_name, name_without_ingredient]))
        return list(
            dict.fromkeys(
                [full_name, name_without_ingredient, family_name],
            )
        )
