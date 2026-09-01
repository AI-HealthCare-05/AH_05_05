import asyncio
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from ai_worker.rag.rerankers.knowledge_search_result_refiner import (
    KnowledgeSearchResultRefiner,
)
from ai_worker.schemas.knowledge import (
    KnowledgeChunk,
    KnowledgeSearchQuery,
    RetrievedKnowledgeChunk,
)


class QdrantKnowledgeStore:
    _MAX_SEARCH_CANDIDATES = 50

    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        collection_name: str,
        vector_size: int,
    ) -> None:
        normalized_name = collection_name.strip()
        if not normalized_name:
            raise ValueError("컬렉션 이름은 비어 있을 수 없습니다.")
        if vector_size <= 0:
            raise ValueError("벡터 차원은 0보다 커야 합니다.")

        self._client = client
        self._collection_name = normalized_name
        self._vector_size = vector_size
        self._collection_validated = False
        self._collection_validation_lock = asyncio.Lock()

    @property
    def collection_name(self) -> str:
        return self._collection_name

    async def create_release_collection(self) -> None:
        if await self._client.collection_exists(self._collection_name):
            raise ValueError(f"release 컬렉션이 이미 존재합니다: {self._collection_name}")

        await self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=models.VectorParams(
                size=self._vector_size,
                distance=models.Distance.COSINE,
            ),
        )
        self._collection_validated = True

    async def upsert_chunks(
        self,
        chunks: list[KnowledgeChunk],
        vectors: list[list[float]],
    ) -> list[str]:
        if len(chunks) != len(vectors):
            raise ValueError("Knowledge 청크와 임베딩 벡터 개수가 일치하지 않습니다.")
        if not chunks:
            return []

        self._validate_vectors(vectors)
        await self._validate_existing_collection()
        point_ids = [self._point_id(chunk.chunk_id) for chunk in chunks]
        points = [
            models.PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "chunk_id": chunk.chunk_id,
                    "content": chunk.content,
                    "embedding_text": chunk.embedding_text,
                    "token_count": chunk.token_count,
                    "metadata": chunk.metadata.model_dump(mode="json"),
                },
            )
            for point_id, chunk, vector in zip(
                point_ids,
                chunks,
                vectors,
                strict=True,
            )
        ]

        await self._client.upsert(
            collection_name=self._collection_name,
            points=points,
            wait=True,
        )
        return point_ids

    async def count_points(self) -> int:
        await self._validate_existing_collection()
        result = await self._client.count(
            collection_name=self._collection_name,
            exact=True,
        )
        return result.count

    async def search(
        self,
        *,
        query_vector: list[float],
        search_query: KnowledgeSearchQuery,
    ) -> list[RetrievedKnowledgeChunk]:
        self._validate_vectors([query_vector])
        await self._validate_existing_collection()
        candidate_limit = min(
            self._MAX_SEARCH_CANDIDATES,
            search_query.limit * 4,
        )
        response = await self._client.query_points(
            collection_name=self._collection_name,
            query=query_vector,
            query_filter=self._build_filter(search_query),
            limit=candidate_limit,
            with_payload=True,
            with_vectors=False,
        )

        results: list[RetrievedKnowledgeChunk] = []
        for point in response.points:
            payload = point.payload or {}
            try:
                results.append(
                    RetrievedKnowledgeChunk(
                        point_id=str(point.id),
                        similarity_score=point.score,
                        chunk_id=payload["chunk_id"],
                        content=payload["content"],
                        embedding_text=payload["embedding_text"],
                        token_count=payload["token_count"],
                        metadata=payload["metadata"],
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return KnowledgeSearchResultRefiner.refine(
            results,
            query=search_query.query,
            limit=search_query.limit,
        )

    async def _validate_existing_collection(self) -> None:
        if self._collection_validated:
            return
        async with self._collection_validation_lock:
            if self._collection_validated:
                return
            if not await self._client.collection_exists(self._collection_name):
                raise ValueError(f"release 컬렉션을 찾을 수 없습니다: {self._collection_name}")

            collection = await self._client.get_collection(self._collection_name)
            vector_params = collection.config.params.vectors
            if not isinstance(vector_params, models.VectorParams):
                raise ValueError("단일 벡터 컬렉션만 사용할 수 있습니다.")
            if vector_params.size != self._vector_size:
                raise ValueError("기존 컬렉션의 벡터 차원이 설정값과 일치하지 않습니다.")
            if vector_params.distance != models.Distance.COSINE:
                raise ValueError("기존 컬렉션의 거리 방식이 COSINE이 아닙니다.")
            # 릴리스 컬렉션은 불변으로 운영하므로 프로세스 생명주기 동안
            # 성공한 스키마 검증을 재사용해 검색별 관리 RPC를 제거한다.
            self._collection_validated = True

    def _validate_vectors(self, vectors: list[list[float]]) -> None:
        if any(len(vector) != self._vector_size for vector in vectors):
            raise ValueError("임베딩 벡터 차원이 설정값과 일치하지 않습니다.")

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, chunk_id))

    @staticmethod
    def _build_filter(search_query: KnowledgeSearchQuery) -> models.Filter:
        conditions: list[models.Condition] = [
            models.FieldCondition(
                key="metadata.dataset_version",
                match=models.MatchValue(value=search_query.dataset_version),
            )
        ]

        entity_conditions: list[models.Condition] = []
        QdrantKnowledgeStore._append_any_filter(
            entity_conditions,
            "metadata.drug_names",
            search_query.drug_names,
        )
        QdrantKnowledgeStore._append_any_filter(
            entity_conditions,
            "metadata.ingredient_names",
            search_query.ingredient_names,
        )
        QdrantKnowledgeStore._append_any_filter(
            entity_conditions,
            "metadata.interaction_pair_keys",
            search_query.interaction_pair_keys,
        )
        QdrantKnowledgeStore._append_any_filter(
            conditions,
            "metadata.document_type",
            [value.value for value in search_query.document_types],
        )
        QdrantKnowledgeStore._append_any_filter(
            conditions,
            "metadata.special_populations",
            search_query.special_populations,
        )
        QdrantKnowledgeStore._append_any_filter(
            conditions,
            "metadata.section_type",
            [value.value for value in search_query.section_types],
        )
        if search_query.interaction_type is not None:
            conditions.append(
                models.FieldCondition(
                    key="metadata.interaction_type",
                    match=models.MatchValue(value=search_query.interaction_type),
                )
            )

        if entity_conditions:
            conditions.append(models.Filter(should=entity_conditions))

        return models.Filter(must=conditions)

    @staticmethod
    def _append_any_filter(
        conditions: list[models.Condition],
        key: str,
        values: list[str],
    ) -> None:
        if not values:
            return
        conditions.append(
            models.FieldCondition(
                key=key,
                match=models.MatchAny(any=values),
            )
        )
