import asyncio
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from ai_worker.rag.rerankers.knowledge_search_result_refiner import (
    KnowledgeSearchResultRefiner,
)
from ai_worker.schemas.knowledge import (
    KnowledgeChunk,
    KnowledgeSearchQuery,
    KnowledgeVectorDistance,
    RetrievedKnowledgeChunk,
)


@dataclass(frozen=True)
class QdrantKnowledgeSearchTrace:
    """동일 Qdrant 조회의 원시 후보와 refiner 결과를 감사 경로에 제공한다."""

    raw_results: list[RetrievedKnowledgeChunk]
    refined_results: list[RetrievedKnowledgeChunk]


class QdrantKnowledgeStore:
    _MAX_SEARCH_CANDIDATES = 50

    def __init__(
        self,
        *,
        client: AsyncQdrantClient,
        collection_name: str,
        vector_size: int,
        distance: KnowledgeVectorDistance = KnowledgeVectorDistance.COSINE,
    ) -> None:
        normalized_name = collection_name.strip()
        if not normalized_name:
            raise ValueError("컬렉션 이름은 비어 있을 수 없습니다.")
        if vector_size <= 0:
            raise ValueError("벡터 차원은 0보다 커야 합니다.")

        self._client = client
        self._collection_name = normalized_name
        self._vector_size = vector_size
        self._distance = KnowledgeVectorDistance(distance)
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
                distance=self._qdrant_distance,
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
        trace = await self.search_with_trace(
            query_vector=query_vector,
            search_query=search_query,
        )
        return trace.refined_results

    async def search_with_trace(
        self,
        *,
        query_vector: list[float],
        search_query: KnowledgeSearchQuery,
    ) -> QdrantKnowledgeSearchTrace:
        """운영 `search`와 동일한 query/filter로 raw·refined 후보를 함께 관측한다."""
        self._validate_vectors([query_vector])
        await self._validate_existing_collection()
        candidate_limit = (
            search_query.limit
            if search_query.exhaustive
            else min(
                self._MAX_SEARCH_CANDIDATES,
                search_query.limit * 4,
            )
        )
        response = await self._client.query_points(
            collection_name=self._collection_name,
            query=query_vector,
            query_filter=self._build_filter(search_query),
            limit=candidate_limit,
            offset=search_query.offset,
            with_payload=True,
            with_vectors=False,
        )

        raw_results: list[RetrievedKnowledgeChunk] = []
        for point in response.points:
            result = self._chunk_from_payload(
                point_id=str(point.id),
                similarity_score=point.score,
                payload=point.payload or {},
            )
            if result is not None:
                raw_results.append(result)
        if search_query.exhaustive and response.points and not raw_results:
            raise RuntimeError(
                "exhaustive Knowledge search received a nonempty page with no valid payloads."
            )
        refined_results = (
            raw_results
            if search_query.exhaustive
            else KnowledgeSearchResultRefiner.refine(
                raw_results,
                query=search_query.query,
                limit=search_query.limit,
            )
        )
        return QdrantKnowledgeSearchTrace(
            raw_results=raw_results,
            refined_results=refined_results,
        )

    async def find_chunks_by_document_id(
        self,
        *,
        document_id: str,
    ) -> list[RetrievedKnowledgeChunk]:
        """Audit에서 gold 문서의 실제 payload와 dataset을 확인한다."""
        normalized_document_id = document_id.strip()
        if not normalized_document_id:
            raise ValueError("문서 ID는 비어 있을 수 없습니다.")
        await self._validate_existing_collection()

        chunks: list[RetrievedKnowledgeChunk] = []
        offset = None
        while True:
            points, offset = await self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="metadata.document_id",
                            match=models.MatchValue(value=normalized_document_id),
                        )
                    ]
                ),
                limit=self._MAX_SEARCH_CANDIDATES,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in points:
                result = self._chunk_from_payload(
                    point_id=str(point.id),
                    similarity_score=0.0,
                    payload=point.payload or {},
                )
                if result is not None:
                    chunks.append(result)
            if offset is None:
                return chunks

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
            if vector_params.distance != self._qdrant_distance:
                raise ValueError("기존 컬렉션의 거리 방식이 설정값과 일치하지 않습니다.")
            # 릴리스 컬렉션은 불변으로 운영하므로 프로세스 생명주기 동안
            # 성공한 스키마 검증을 재사용해 검색별 관리 RPC를 제거한다.
            self._collection_validated = True

    def _validate_vectors(self, vectors: list[list[float]]) -> None:
        if any(len(vector) != self._vector_size for vector in vectors):
            raise ValueError("임베딩 벡터 차원이 설정값과 일치하지 않습니다.")

    @property
    def _qdrant_distance(self) -> models.Distance:
        if self._distance == KnowledgeVectorDistance.DOT:
            return models.Distance.DOT
        return models.Distance.COSINE

    @staticmethod
    def _point_id(chunk_id: str) -> str:
        return str(uuid5(NAMESPACE_URL, chunk_id))

    @staticmethod
    def _chunk_from_payload(
        *,
        point_id: str,
        similarity_score: float,
        payload: dict,
    ) -> RetrievedKnowledgeChunk | None:
        try:
            return RetrievedKnowledgeChunk(
                point_id=point_id,
                similarity_score=similarity_score,
                chunk_id=payload["chunk_id"],
                content=payload["content"],
                embedding_text=payload["embedding_text"],
                token_count=payload["token_count"],
                metadata=payload["metadata"],
            )
        except (KeyError, TypeError, ValueError):
            return None

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
