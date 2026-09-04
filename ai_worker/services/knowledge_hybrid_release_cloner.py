from dataclasses import dataclass
from typing import Protocol

from qdrant_client import AsyncQdrantClient

from ai_worker.schemas.knowledge import KnowledgeChunk


class KnowledgeReleaseStore(Protocol):
    @property
    def collection_name(self) -> str: ...

    async def count_points(self) -> int: ...


class HybridKnowledgeReleaseStore(KnowledgeReleaseStore, Protocol):
    async def create_release_collection(self) -> None: ...

    async def upsert_chunks(
        self,
        chunks: list[KnowledgeChunk],
        vectors: list[list[float]],
    ) -> list[str]: ...


@dataclass(frozen=True)
class KnowledgeHybridCloneResult:
    source_collection: str
    target_collection: str
    source_count: int
    target_count: int
    batch_count: int


class KnowledgeHybridReleaseCloner:
    """기존 Dense 릴리스를 BM25 named vector가 있는 새 릴리스로 복제한다."""

    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        source_store: KnowledgeReleaseStore,
        target_store: HybridKnowledgeReleaseStore,
        batch_size: int = 100,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("batch_size는 0보다 커야 합니다.")
        self._client = client
        self._source_store = source_store
        self._target_store = target_store
        self._batch_size = batch_size

    async def clone(self) -> KnowledgeHybridCloneResult:
        source_name = self._source_store.collection_name
        target_name = self._target_store.collection_name
        if source_name == target_name:
            raise ValueError("원본과 대상 컬렉션 이름은 서로 달라야 합니다.")

        source_count = await self._source_store.count_points()
        await self._target_store.create_release_collection()

        offset = None
        batch_count = 0
        while True:
            points, next_offset = await self._client.scroll(
                collection_name=source_name,
                limit=self._batch_size,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            if points:
                chunks: list[KnowledgeChunk] = []
                vectors: list[list[float]] = []
                for point in points:
                    chunk, vector = self._deserialize_source_point(point)
                    chunks.append(chunk)
                    vectors.append(vector)
                await self._target_store.upsert_chunks(chunks, vectors)
                batch_count += 1
            if next_offset is None:
                break
            offset = next_offset

        target_count = await self._target_store.count_points()
        if source_count != target_count:
            raise RuntimeError(f"복제 후 포인트 수가 일치하지 않습니다: source={source_count}, target={target_count}")
        return KnowledgeHybridCloneResult(
            source_collection=source_name,
            target_collection=target_name,
            source_count=source_count,
            target_count=target_count,
            batch_count=batch_count,
        )

    @staticmethod
    def _deserialize_source_point(point) -> tuple[KnowledgeChunk, list[float]]:
        payload = point.payload or {}
        vector = point.vector
        if not isinstance(vector, list) or not all(isinstance(value, (int, float)) for value in vector):
            raise ValueError("원본 컬렉션은 단일 Dense 벡터 구조여야 합니다.")
        try:
            chunk = KnowledgeChunk(
                chunk_id=payload["chunk_id"],
                content=payload["content"],
                embedding_text=payload["embedding_text"],
                token_count=payload["token_count"],
                metadata=payload["metadata"],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("원본 포인트 payload가 KnowledgeChunk 계약과 다릅니다.") from exc
        return chunk, [float(value) for value in vector]
