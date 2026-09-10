from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from ai_worker.domain.interfaces import EmbeddingProvider
from ai_worker.schemas.interaction import InteractionPairType
from ai_worker.schemas.knowledge import (
    KnowledgeChunk,
    KnowledgeEvidenceLevel,
    KnowledgeStudyPopulation,
)


class KnowledgeVectorStore(Protocol):
    @property
    def collection_name(self) -> str: ...

    async def create_release_collection(self) -> None: ...

    async def upsert_chunks(
        self,
        chunks: list[KnowledgeChunk],
        vectors: list[list[float]],
    ) -> list[str]: ...

    async def count_points(self) -> int: ...


@dataclass(frozen=True)
class KnowledgeMetadataQualityReport:
    total_chunk_count: int
    interaction_chunk_count: int
    pair_key_chunk_count: int
    known_evidence_count: int
    known_study_population_count: int


@dataclass(frozen=True)
class KnowledgeIndexResult:
    dataset_version: str
    collection_name: str
    indexed_chunk_count: int
    metadata_quality: KnowledgeMetadataQualityReport | None = None
    reused_embedding_count: int = 0
    new_embedding_count: int = 0


class KnowledgeIndexer:
    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: KnowledgeVectorStore,
        embedding_batch_size: int = 64,
        upsert_batch_size: int = 64,
    ) -> None:
        if embedding_batch_size <= 0:
            raise ValueError("임베딩 배치 크기는 1 이상이어야 합니다.")
        if upsert_batch_size <= 0:
            raise ValueError("upsert 배치 크기는 1 이상이어야 합니다.")

        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._embedding_batch_size = embedding_batch_size
        self._upsert_batch_size = upsert_batch_size

    async def index_release(
        self,
        chunks: list[KnowledgeChunk],
        *,
        reusable_vectors_by_embedding_text: Mapping[str, list[float]] | None = None,
    ) -> KnowledgeIndexResult:
        if not chunks:
            raise ValueError("인덱싱할 Knowledge 청크가 없습니다.")

        dataset_versions = {chunk.metadata.dataset_version for chunk in chunks}
        if len(dataset_versions) != 1:
            raise ValueError("하나의 release에는 하나의 dataset_version만 허용됩니다.")
        if any(not chunk.metadata.index_eligible for chunk in chunks):
            raise ValueError("인덱싱 대상이 아닌 Knowledge 청크가 포함되었습니다.")
        self._validate_interaction_metadata(chunks)

        resolved_vectors, reused_embedding_count = await self._prepare_vectors(
            chunks,
            reusable_vectors_by_embedding_text=reusable_vectors_by_embedding_text,
        )
        await self._vector_store.create_release_collection()

        for start in range(0, len(chunks), self._upsert_batch_size):
            end = start + self._upsert_batch_size
            await self._vector_store.upsert_chunks(
                chunks[start:end],
                resolved_vectors[start:end],
            )

        stored_count = await self._vector_store.count_points()
        if stored_count != len(chunks):
            raise ValueError(
                "Knowledge release 저장 건수가 입력 청크 수와 일치하지 "
                f"않습니다: expected={len(chunks)}, actual={stored_count}"
            )

        return KnowledgeIndexResult(
            dataset_version=next(iter(dataset_versions)),
            collection_name=self._vector_store.collection_name,
            indexed_chunk_count=stored_count,
            metadata_quality=self.assess_metadata_quality(chunks),
            reused_embedding_count=reused_embedding_count,
            new_embedding_count=(len(chunks) - reused_embedding_count),
        )

    async def _prepare_vectors(
        self,
        chunks: list[KnowledgeChunk],
        *,
        reusable_vectors_by_embedding_text: Mapping[str, list[float]] | None,
    ) -> tuple[list[list[float]], int]:
        reused_vectors = reusable_vectors_by_embedding_text or {}
        vectors: list[list[float] | None] = [None] * len(chunks)
        missing_indexes: list[int] = []
        for index, chunk in enumerate(chunks):
            reusable_vector = reused_vectors.get(chunk.embedding_text)
            if reusable_vector is None:
                missing_indexes.append(index)
                continue
            vectors[index] = reusable_vector

        for start in range(0, len(missing_indexes), self._embedding_batch_size):
            batch_indexes = missing_indexes[start : start + self._embedding_batch_size]
            batch = [chunks[index] for index in batch_indexes]
            batch_vectors = await self._embedding_provider.embed_documents([chunk.embedding_text for chunk in batch])
            if len(batch_vectors) != len(batch):
                raise ValueError("임베딩 배치의 문서 수와 벡터 수가 일치하지 않습니다.")
            for index, vector in zip(batch_indexes, batch_vectors, strict=True):
                vectors[index] = vector

        resolved_vectors = [vector for vector in vectors if vector is not None]
        if len(resolved_vectors) != len(chunks):
            raise RuntimeError("모든 Knowledge 청크의 임베딩 벡터를 준비하지 못했습니다.")
        return resolved_vectors, (len(chunks) - len(missing_indexes))

    @staticmethod
    def assess_metadata_quality(
        chunks: list[KnowledgeChunk],
    ) -> KnowledgeMetadataQualityReport:
        return KnowledgeMetadataQualityReport(
            total_chunk_count=len(chunks),
            interaction_chunk_count=sum(chunk.metadata.interaction_type is not None for chunk in chunks),
            pair_key_chunk_count=sum(bool(chunk.metadata.interaction_pair_keys) for chunk in chunks),
            known_evidence_count=sum(
                chunk.metadata.evidence_level != KnowledgeEvidenceLevel.UNKNOWN for chunk in chunks
            ),
            known_study_population_count=sum(
                chunk.metadata.study_population != KnowledgeStudyPopulation.UNKNOWN for chunk in chunks
            ),
        )

    @staticmethod
    def _validate_interaction_metadata(chunks: list[KnowledgeChunk]) -> None:
        for chunk in chunks:
            metadata = chunk.metadata
            if not metadata.interaction_pair_keys:
                continue
            try:
                interaction_type = InteractionPairType(metadata.interaction_type)
            except (TypeError, ValueError):
                raise ValueError(
                    f"상호작용 메타데이터에는 유효한 유형과 유형별 대상이 필요합니다: chunk_id={chunk.chunk_id}"
                ) from None

            drug_count = len(set(metadata.drug_names))
            ingredient_count = len(set(metadata.ingredient_names))
            food_count = len(set(metadata.food_names))
            valid_entity_counts = {
                InteractionPairType.DRUG_DRUG: drug_count >= 2,
                InteractionPairType.DRUG_SUPPLEMENT: drug_count >= 1 and ingredient_count >= 1,
                InteractionPairType.SUPPLEMENT_SUPPLEMENT: ingredient_count >= 2,
                InteractionPairType.DRUG_FOOD: drug_count >= 1 and food_count >= 1,
            }
            if not valid_entity_counts[interaction_type]:
                raise ValueError(
                    f"상호작용 메타데이터에는 유효한 유형과 유형별 대상이 필요합니다: chunk_id={chunk.chunk_id}"
                )
