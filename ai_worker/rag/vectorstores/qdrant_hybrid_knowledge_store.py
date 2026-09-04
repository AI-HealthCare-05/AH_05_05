from qdrant_client.http import models

from ai_worker.rag.rerankers.knowledge_search_result_refiner import (
    KnowledgeSearchResultRefiner,
)
from ai_worker.rag.vectorstores.qdrant_knowledge_store import (
    QdrantKnowledgeStore,
)
from ai_worker.schemas.knowledge import (
    KnowledgeChunk,
    KnowledgeSearchMode,
    KnowledgeSearchQuery,
    RetrievedKnowledgeChunk,
)


class QdrantHybridKnowledgeStore(QdrantKnowledgeStore):
    """Named dense/BM25 vector를 사용하는 실험용 불변 저장소."""

    _DENSE_VECTOR_NAME = "dense"
    _BM25_VECTOR_NAME = "bm25"
    _BM25_MODEL = "qdrant/bm25"
    _BM25_OPTIONS = {"tokenizer": "multilingual"}

    def __init__(
        self,
        *,
        search_mode: KnowledgeSearchMode,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._search_mode = search_mode

    @property
    def search_mode(self) -> KnowledgeSearchMode:
        return self._search_mode

    async def create_release_collection(self) -> None:
        if await self._client.collection_exists(self._collection_name):
            raise ValueError(
                "release 컬렉션이 이미 존재합니다: "
                f"{self._collection_name}"
            )

        await self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config={
                self._DENSE_VECTOR_NAME: models.VectorParams(
                    size=self._vector_size,
                    distance=models.Distance.COSINE,
                )
            },
            sparse_vectors_config={
                self._BM25_VECTOR_NAME: models.SparseVectorParams(
                    modifier=models.Modifier.IDF,
                )
            },
        )
        self._collection_validated = True

    async def upsert_chunks(
        self,
        chunks: list[KnowledgeChunk],
        vectors: list[list[float]],
    ) -> list[str]:
        if len(chunks) != len(vectors):
            raise ValueError(
                "Knowledge 청크와 임베딩 벡터 개수가 일치하지 않습니다."
            )
        if not chunks:
            return []

        self._validate_vectors(vectors)
        await self._validate_existing_collection()
        point_ids = [self._point_id(chunk.chunk_id) for chunk in chunks]
        points = [
            models.PointStruct(
                id=point_id,
                vector={
                    self._DENSE_VECTOR_NAME: vector,
                    self._BM25_VECTOR_NAME: self._bm25_document(
                        chunk.embedding_text,
                    ),
                },
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
        request = self._query_request(
            query_vector=query_vector,
            query_text=search_query.query,
            candidate_limit=candidate_limit,
        )
        response = await self._client.query_points(
            collection_name=self._collection_name,
            query_filter=self._build_filter(search_query),
            limit=candidate_limit,
            with_payload=True,
            with_vectors=False,
            **request,
        )
        results = self._deserialize_points(response.points)
        return KnowledgeSearchResultRefiner.refine(
            results,
            query=search_query.query,
            limit=search_query.limit,
        )

    def _query_request(
        self,
        *,
        query_vector: list[float],
        query_text: str,
        candidate_limit: int,
    ) -> dict:
        if self._search_mode == KnowledgeSearchMode.DENSE:
            return {
                "query": query_vector,
                "using": self._DENSE_VECTOR_NAME,
            }
        sparse_query = self._bm25_document(query_text)
        if self._search_mode == KnowledgeSearchMode.BM25:
            return {
                "query": sparse_query,
                "using": self._BM25_VECTOR_NAME,
            }
        return {
            "prefetch": [
                models.Prefetch(
                    query=query_vector,
                    using=self._DENSE_VECTOR_NAME,
                    limit=candidate_limit,
                ),
                models.Prefetch(
                    query=sparse_query,
                    using=self._BM25_VECTOR_NAME,
                    limit=candidate_limit,
                ),
            ],
            "query": models.FusionQuery(fusion=models.Fusion.RRF),
        }

    def _deserialize_points(self, points: list) -> list[RetrievedKnowledgeChunk]:
        results: list[RetrievedKnowledgeChunk] = []
        for point in points:
            payload = point.payload or {}
            try:
                score = float(point.score)
                if self._search_mode != KnowledgeSearchMode.DENSE:
                    score = self._bounded_relevance_score(score)
                results.append(
                    RetrievedKnowledgeChunk(
                        point_id=str(point.id),
                        similarity_score=score,
                        search_mode=self._search_mode,
                        chunk_id=payload["chunk_id"],
                        content=payload["content"],
                        embedding_text=payload["embedding_text"],
                        token_count=payload["token_count"],
                        metadata=payload["metadata"],
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return results

    async def _validate_existing_collection(self) -> None:
        if self._collection_validated:
            return
        async with self._collection_validation_lock:
            if self._collection_validated:
                return
            if not await self._client.collection_exists(
                self._collection_name,
            ):
                raise ValueError(
                    "release 컬렉션을 찾을 수 없습니다: "
                    f"{self._collection_name}"
                )
            collection = await self._client.get_collection(
                self._collection_name,
            )
            vector_params = collection.config.params.vectors
            sparse_params = collection.config.params.sparse_vectors
            dense = (
                vector_params.get(self._DENSE_VECTOR_NAME)
                if isinstance(vector_params, dict)
                else None
            )
            sparse = (
                sparse_params.get(self._BM25_VECTOR_NAME)
                if isinstance(sparse_params, dict)
                else None
            )
            if not isinstance(dense, models.VectorParams):
                raise ValueError("dense named vector가 없습니다.")
            if dense.size != self._vector_size:
                raise ValueError(
                    "기존 컬렉션의 dense 벡터 차원이 설정값과 일치하지 않습니다."
                )
            if dense.distance != models.Distance.COSINE:
                raise ValueError("dense named vector의 거리 방식이 COSINE이 아닙니다.")
            if not isinstance(sparse, models.SparseVectorParams):
                raise ValueError("bm25 sparse vector가 없습니다.")
            if sparse.modifier != models.Modifier.IDF:
                raise ValueError("bm25 sparse vector에 IDF modifier가 필요합니다.")
            self._collection_validated = True

    @classmethod
    def _bm25_document(cls, text: str) -> models.Document:
        return models.Document(
            text=text,
            model=cls._BM25_MODEL,
            options=cls._BM25_OPTIONS,
        )

    @staticmethod
    def _bounded_relevance_score(score: float) -> float:
        if score <= 0.0:
            return 0.0
        return score / (1.0 + score)
