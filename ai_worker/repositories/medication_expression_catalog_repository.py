import asyncio
import re
import time

from ai_worker.domain.interfaces import SupplementIngredientCatalog
from ai_worker.schemas.interaction import InteractionEntityKind as SearchEntityKind
from ai_worker.schemas.medication_search import (
    MedicationCatalogEntry,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
)
from app.models.interactions import (
    InteractionEntity,
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
        self._cached_entries: list[MedicationCatalogEntry] | None = None
        self._cached_expressions: list[str] | None = None
        self._cache_expires_at = 0.0

    async def list_expressions(self) -> list[str]:
        now = time.monotonic()
        if self._cached_expressions is not None and now < self._cache_expires_at:
            return self._cached_expressions.copy()

        entries = await self.list_entries()
        self._cached_expressions = sorted(
            {expression for entry in entries for expression in entry.expressions},
            key=str.casefold,
        )
        return self._cached_expressions.copy()

    async def list_entries(self) -> list[MedicationCatalogEntry]:
        now = time.monotonic()
        if self._cached_entries is not None and now < self._cache_expires_at:
            return self._cached_entries.copy()

        results = await asyncio.gather(
            MedicationProductGuide.all().values_list("product_name", flat=True),
            InteractionEntity.all().prefetch_related("aliases"),
            SupplementNutrient.all().values_list(
                "name",
                flat=True,
            ),
            self._list_additional_entries(),
            return_exceptions=True,
        )
        if all(isinstance(result, BaseException) for result in results):
            raise RuntimeError("질문 해석 카탈로그 공급원을 모두 조회하지 못했습니다.")
        product_names = self._list_or_empty(results[0])
        interaction_entities = self._list_or_empty(results[1])
        supplement_names = self._list_or_empty(results[2])
        additional_entries = self._list_or_empty(results[3])
        entries: list[MedicationCatalogEntry] = []
        entries.extend(
            MedicationCatalogEntry(
                canonical_name=str(product_name).strip(),
                aliases=self._product_expressions(str(product_name))[1:],
                entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                kind=SearchEntityKind.DRUG,
                source=MedicationQueryEntitySource.RDBMS,
            )
            for product_name in product_names
            if str(product_name).strip()
        )
        for entity in interaction_entities:
            kind = SearchEntityKind(str(entity.entity_kind))
            entity_type = (
                MedicationQueryEntityType.FOOD_CATEGORY
                if kind == SearchEntityKind.FOOD
                else MedicationQueryEntityType.INGREDIENT_NAME
            )
            entries.append(
                MedicationCatalogEntry(
                    canonical_name=entity.canonical_name,
                    entity_type=entity_type,
                    kind=kind,
                    source=MedicationQueryEntitySource.RDBMS,
                )
            )
            for alias in entity.aliases:
                entries.append(
                    MedicationCatalogEntry(
                        canonical_name=entity.canonical_name,
                        aliases=[alias.alias],
                        entity_type=(
                            MedicationQueryEntityType.BRAND_ALIAS
                            if alias.alias_type.value == "PRODUCT_NAME"
                            else entity_type
                        ),
                        kind=kind,
                        source=MedicationQueryEntitySource.RDBMS,
                    )
                )
        entries.extend(
            MedicationCatalogEntry(
                canonical_name=str(name).strip(),
                entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                kind=SearchEntityKind.SUPPLEMENT,
                source=MedicationQueryEntitySource.RDBMS,
            )
            for name in supplement_names
            if str(name).strip()
        )
        entries.extend(additional_entries)
        self._cached_entries = self._deduplicate_entries(entries)
        self._cache_expires_at = now + self._cache_ttl_seconds
        return self._cached_entries.copy()

    @staticmethod
    def _list_or_empty(value: object) -> list[object]:
        return value if isinstance(value, list) else []

    async def _list_additional_entries(self) -> list[MedicationCatalogEntry]:
        if self._supplement_catalog is None:
            return []
        list_entries = getattr(self._supplement_catalog, "list_entries", None)
        if callable(list_entries):
            return await list_entries()
        return [
            MedicationCatalogEntry(
                canonical_name=name,
                entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                kind=SearchEntityKind.SUPPLEMENT,
                source=MedicationQueryEntitySource.CATALOG,
            )
            for name in await self._supplement_catalog.list_names()
        ]

    @staticmethod
    def _deduplicate_entries(
        entries: list[MedicationCatalogEntry],
    ) -> list[MedicationCatalogEntry]:
        deduplicated: dict[tuple[object, ...], MedicationCatalogEntry] = {}
        for entry in entries:
            key = (
                entry.canonical_name.casefold(),
                tuple(alias.casefold() for alias in entry.aliases),
                entry.entity_type,
                entry.kind,
                entry.source,
            )
            deduplicated.setdefault(key, entry)
        return sorted(
            deduplicated.values(),
            key=lambda entry: (
                entry.canonical_name.casefold(),
                entry.entity_type.value,
                entry.source.value,
            ),
        )

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
