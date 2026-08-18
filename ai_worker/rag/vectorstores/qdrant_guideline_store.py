from uuid import NAMESPACE_URL, uuid5

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from ai_worker.schemas.guideline import (
    GuidelineDocument,
    GuidelineMetadata,
    GuidelineSearchQuery,
    RetrievedGuidelineChunk,
)


class QdrantGuidelineStore:
    def __init__(
        self,
        client: AsyncQdrantClient,
        collection_name: str,
        vector_size: int,
    ) -> None:
        normalized_collection_name = collection_name.strip()

        if not normalized_collection_name:
            raise ValueError("컬렉션 이름은 비어 있을 수 없습니다.")

        if vector_size <= 0:
            raise ValueError("벡터 차원은 0보다 커야 합니다.")

        self._client = client
        self._collection_name = normalized_collection_name
        self._vector_size = vector_size

    async def ensure_collection(self) -> None:
        collection_exists = await self._client.collection_exists(self._collection_name)

        if collection_exists:
            await self._validate_existing_collection()
            return

        await self._client.create_collection(
            collection_name=self._collection_name,
            vectors_config=models.VectorParams(
                size=self._vector_size,
                distance=models.Distance.COSINE,
            ),
        )

    async def upsert_chunks(
        self,
        chunks: list[GuidelineDocument],
        vectors: list[list[float]],
    ) -> list[str]:
        if len(chunks) != len(vectors):
            raise ValueError("가이드라인 청크와 임베딩 벡터 개수가 일치하지 않습니다.")

        if not chunks:
            return []

        self._validate_vectors(vectors)
        await self.ensure_collection()

        point_ids = [self._build_point_id(chunk) for chunk in chunks]

        points = [
            models.PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "content": chunk.content,
                    "metadata": (chunk.metadata.model_dump(mode="json")),
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

    async def delete_by_document_id(
            self,
            document_id: str,
    ) -> None:
        normalized_document_id = document_id.strip()

        if not normalized_document_id:
            raise ValueError(
                "문서 ID는 비어 있을 수 없습니다."
            )

        collection_exists = (
            await self._client.collection_exists(
                self._collection_name
            )
        )

        if not collection_exists:
            return

        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="metadata.document_id",
                            match=models.MatchValue(
                                value=normalized_document_id
                            ),
                        )
                    ]
                )
            ),
            wait=True,
        )

    async def search(
        self,
        query_vector: list[float],
        search_query: GuidelineSearchQuery,
    ) -> list[RetrievedGuidelineChunk]:
        self._validate_vectors([query_vector])
        await self.ensure_collection()

        response = await self._client.query_points(
            collection_name=self._collection_name,
            query=query_vector,
            query_filter=self._build_filter(search_query),
            limit=search_query.limit,
            with_payload=True,
            with_vectors=False,
        )

        results: list[RetrievedGuidelineChunk] = []

        for point in response.points:
            payload = point.payload or {}
            content = payload.get("content")
            metadata = payload.get("metadata")

            if not isinstance(content, str):
                continue

            if not isinstance(metadata, dict):
                continue

            results.append(
                RetrievedGuidelineChunk(
                    vector_chunk_id=str(point.id),
                    content=content,
                    similarity_score=point.score,
                    metadata=(GuidelineMetadata.model_validate(metadata)),
                )
            )

        return results

    async def _validate_existing_collection(
        self,
    ) -> None:
        collection = await self._client.get_collection(self._collection_name)
        vector_params = collection.config.params.vectors

        if not isinstance(
            vector_params,
            models.VectorParams,
        ):
            raise ValueError("단일 벡터 컬렉션만 사용할 수 있습니다.")

        if vector_params.size != self._vector_size:
            raise ValueError("기존 컬렉션의 벡터 차원이 설정값과 일치하지 않습니다.")

        if vector_params.distance != models.Distance.COSINE:
            raise ValueError("기존 컬렉션의 거리 방식이 COSINE이 아닙니다.")

    def _validate_vectors(
        self,
        vectors: list[list[float]],
    ) -> None:
        has_invalid_dimension = any(len(vector) != self._vector_size for vector in vectors)

        if has_invalid_dimension:
            raise ValueError("임베딩 벡터 차원이 설정값과 일치하지 않습니다.")

    @staticmethod
    def _build_filter(
        search_query: GuidelineSearchQuery,
    ) -> models.Filter:
        conditions: list[models.Condition] = [
            models.FieldCondition(
                key="metadata.condition",
                match=models.MatchValue(value=search_query.condition),
            )
        ]

        if search_query.care_phase is not None:
            conditions.append(
                models.FieldCondition(
                    key="metadata.care_phase",
                    match=models.MatchValue(value=(search_query.care_phase)),
                )
            )

        if search_query.topic is not None:
            conditions.append(
                models.FieldCondition(
                    key="metadata.topic",
                    match=models.MatchValue(value=search_query.topic),
                )
            )

        return models.Filter(must=conditions)

    @staticmethod
    def _build_point_id(
        chunk: GuidelineDocument,
    ) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                chunk.model_dump_json(),
            )
        )
