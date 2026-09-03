import asyncio
import time

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from ai_worker.domain.interfaces import SupplementIngredientCatalog
from app.models.supplement_nutrients import SupplementNutrient


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
            self._cached_names = await self._load_names()
            self._cache_expires_at = now + self._cache_ttl_seconds
            return self._cached_names.copy()

    async def _load_names(self) -> list[str]:
        names: set[str] = set()
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
                    include=["metadata.ingredient_names"],
                ),
                with_vectors=False,
            )
            for record in records:
                metadata = (record.payload or {}).get("metadata") or {}
                raw_names = metadata.get("ingredient_names") or []
                if isinstance(raw_names, str):
                    raw_names = [raw_names]
                names.update(str(name).strip() for name in raw_names if str(name).strip())
            if offset is None:
                break
        return sorted(names, key=str.casefold)


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
        return sorted(
            {name.strip() for result in results if isinstance(result, list) for name in result if name.strip()},
            key=str.casefold,
        )
