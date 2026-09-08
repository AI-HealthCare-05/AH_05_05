import asyncio
import time

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from ai_worker.domain.interfaces import SupplementIngredientCatalog
from ai_worker.schemas.interaction import InteractionEntityKind
from ai_worker.schemas.knowledge import KnowledgeEntityCatalogEntry
from ai_worker.schemas.medication_search import (
    MedicationCatalogEntry,
    MedicationQueryEntitySource,
    MedicationQueryEntityType,
)
from app.models.supplement_nutrients import SupplementNutrient


class CatalogSourcesUnavailableError(RuntimeError):
    """모든 카탈로그 공급원이 실패해 질문 해석을 신뢰할 수 없을 때 발생한다."""


class DbSupplementIngredientCatalog:
    """RDBMS에 등록된 건강기능식품 이름을 질문 해석 어휘로 제공한다."""

    def __init__(self, *, cache_ttl_seconds: float = 300.0) -> None:
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cached_names: list[str] | None = None
        self._cache_expires_at = 0.0
        self._cache_lock = asyncio.Lock()

    async def list_names(self) -> list[str]:
        now = time.monotonic()
        if self._cached_names is not None and now < self._cache_expires_at:
            return self._cached_names.copy()
        async with self._cache_lock:
            now = time.monotonic()
            if self._cached_names is not None and now < self._cache_expires_at:
                return self._cached_names.copy()
            names = await SupplementNutrient.all().values_list(
                "name",
                flat=True,
            )
            self._cached_names = self._normalize_names(names)
            self._cache_expires_at = now + self._cache_ttl_seconds
            return self._cached_names.copy()

    async def list_entries(self) -> list[MedicationCatalogEntry]:
        return [
            MedicationCatalogEntry(
                canonical_name=name,
                entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                kind=InteractionEntityKind.SUPPLEMENT,
                source=MedicationQueryEntitySource.RDBMS,
            )
            for name in await self.list_names()
        ]

    @staticmethod
    def _normalize_names(names: list[object]) -> list[str]:
        return sorted(
            {str(name).strip() for name in names if str(name).strip()},
            key=str.casefold,
        )


class QdrantSupplementIngredientCatalog:
    """활성 Knowledge 릴리스의 성분 메타데이터를 질문 해석 어휘로 제공한다."""

    _SCROLL_PAGE_SIZE = 1_000

    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        collection_name: str,
        dataset_version: str,
        cache_ttl_seconds: float = 300.0,
    ) -> None:
        self._client = client
        self._collection_name = collection_name
        self._dataset_version = dataset_version
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cached_entries: list[MedicationCatalogEntry] | None = None
        self._cached_names: list[str] | None = None
        self._cache_expires_at = 0.0
        self._cache_lock = asyncio.Lock()

    async def list_names(self) -> list[str]:
        now = time.monotonic()
        if self._cached_names is not None and now < self._cache_expires_at:
            return self._cached_names.copy()
        entries = await self.list_entries()
        self._cached_names = sorted(
            {entry.canonical_name for entry in entries if entry.kind == InteractionEntityKind.SUPPLEMENT},
            key=str.casefold,
        )
        return self._cached_names.copy()

    async def list_entries(self) -> list[MedicationCatalogEntry]:
        now = time.monotonic()
        if self._cached_entries is not None and now < self._cache_expires_at:
            return self._cached_entries.copy()
        async with self._cache_lock:
            now = time.monotonic()
            if self._cached_entries is not None and now < self._cache_expires_at:
                return self._cached_entries.copy()
            self._cached_entries = await self._load_entries()
            self._cache_expires_at = now + self._cache_ttl_seconds
            return self._cached_entries.copy()

    async def _load_entries(self) -> list[MedicationCatalogEntry]:
        entries: list[MedicationCatalogEntry] = []
        offset: int | str | object | None = None
        while True:
            records, offset = await self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="metadata.dataset_version",
                            match=models.MatchValue(
                                value=self._dataset_version,
                            ),
                        )
                    ]
                ),
                limit=self._SCROLL_PAGE_SIZE,
                offset=offset,
                with_payload=models.PayloadSelectorInclude(
                    include=[
                        "metadata.product_names",
                        "metadata.drug_names",
                        "metadata.ingredient_names",
                        "metadata.food_names",
                        "metadata.entity_catalog_entries",
                    ],
                ),
                with_vectors=False,
            )
            for record in records:
                metadata = (record.payload or {}).get("metadata") or {}
                typed_entries = self._typed_metadata_entries(metadata)
                if typed_entries:
                    entries.extend(typed_entries)
                    continue
                entries.extend(
                    self._metadata_entries(
                        metadata=metadata,
                        field_name="product_names",
                        entity_type=MedicationQueryEntityType.PRODUCT_NAME,
                        kind=InteractionEntityKind.DRUG,
                    )
                )
                entries.extend(
                    self._metadata_entries(
                        metadata=metadata,
                        field_name="drug_names",
                        entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                        kind=InteractionEntityKind.DRUG,
                    )
                )
                entries.extend(
                    self._metadata_entries(
                        metadata=metadata,
                        field_name="ingredient_names",
                        entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                        kind=InteractionEntityKind.SUPPLEMENT,
                    )
                )
                entries.extend(
                    self._metadata_entries(
                        metadata=metadata,
                        field_name="food_names",
                        entity_type=MedicationQueryEntityType.FOOD_CATEGORY,
                        kind=InteractionEntityKind.FOOD,
                    )
                )
            if offset is None:
                break
        deduplicated: dict[tuple[str, str, str], MedicationCatalogEntry] = {}
        for entry in entries:
            deduplicated.setdefault(
                (
                    entry.canonical_name.casefold(),
                    entry.entity_type.value,
                    entry.kind.value if entry.kind is not None else "",
                ),
                entry,
            )
        return sorted(
            deduplicated.values(),
            key=lambda entry: (
                entry.canonical_name.casefold(),
                entry.entity_type.value,
            ),
        )

    @staticmethod
    def _typed_metadata_entries(
        metadata: dict[object, object],
    ) -> list[MedicationCatalogEntry]:
        raw_entries = metadata.get("entity_catalog_entries") or []
        if not isinstance(raw_entries, list):
            return []

        entries: list[MedicationCatalogEntry] = []
        for raw_entry in raw_entries:
            try:
                entry = KnowledgeEntityCatalogEntry.model_validate(raw_entry)
            except (TypeError, ValueError):
                # 일부 손상된 payload는 해당 행만 제외하고, 나머지 검수된
                # 메타데이터로 질문 해석을 계속한다.
                continue
            entries.append(
                MedicationCatalogEntry(
                    canonical_name=entry.canonical_name,
                    aliases=entry.aliases,
                    entity_type=MedicationQueryEntityType(entry.entity_type.value),
                    kind=entry.kind,
                    source=MedicationQueryEntitySource.QDRANT,
                )
            )
        return entries

    @staticmethod
    def _metadata_entries(
        *,
        metadata: dict[object, object],
        field_name: str,
        entity_type: MedicationQueryEntityType,
        kind: InteractionEntityKind,
    ) -> list[MedicationCatalogEntry]:
        raw_names = metadata.get(field_name) or []
        if isinstance(raw_names, str):
            raw_names = [raw_names]
        if not isinstance(raw_names, list):
            return []
        return [
            MedicationCatalogEntry(
                canonical_name=str(name).strip(),
                entity_type=entity_type,
                kind=kind,
                source=MedicationQueryEntitySource.QDRANT,
            )
            for name in raw_names
            if str(name).strip()
        ]


class CompositeSupplementIngredientCatalog:
    """여러 어휘 공급원을 합치고 일부 장애 시 성공한 공급원만 사용한다."""

    def __init__(
        self,
        *,
        sources: list[SupplementIngredientCatalog],
    ) -> None:
        self._sources = sources

    async def list_names(self) -> list[str]:
        results = await asyncio.gather(
            *(source.list_names() for source in self._sources),
            return_exceptions=True,
        )
        self._require_successful_source(results)
        return sorted(
            {name.strip() for result in results if isinstance(result, list) for name in result if name.strip()},
            key=str.casefold,
        )

    async def list_entries(self) -> list[MedicationCatalogEntry]:
        results = await asyncio.gather(
            *(self._source_entries(source) for source in self._sources),
            return_exceptions=True,
        )
        self._require_successful_source(results)
        entries = [entry for result in results if isinstance(result, list) for entry in result]
        deduplicated: dict[tuple[str, str], MedicationCatalogEntry] = {}
        for entry in entries:
            deduplicated.setdefault(
                (entry.canonical_name.casefold(), entry.source.value),
                entry,
            )
        return sorted(
            deduplicated.values(),
            key=lambda entry: (
                entry.canonical_name.casefold(),
                entry.source.value,
            ),
        )

    @staticmethod
    def _require_successful_source(results: list[object]) -> None:
        if results and not all(isinstance(result, BaseException) for result in results):
            return
        raise CatalogSourcesUnavailableError(
            "질문 해석에 필요한 카탈로그 공급원을 모두 조회하지 못했습니다.",
        )

    @staticmethod
    async def _source_entries(
        source: SupplementIngredientCatalog,
    ) -> list[MedicationCatalogEntry]:
        list_entries = getattr(source, "list_entries", None)
        if callable(list_entries):
            return await list_entries()
        return [
            MedicationCatalogEntry(
                canonical_name=name,
                entity_type=MedicationQueryEntityType.INGREDIENT_NAME,
                kind=InteractionEntityKind.SUPPLEMENT,
                source=MedicationQueryEntitySource.CATALOG,
            )
            for name in await source.list_names()
        ]
