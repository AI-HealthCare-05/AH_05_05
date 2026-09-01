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
    ) -> KnowledgeIndexResult:
        if not chunks:
            raise ValueError("인덱싱할 Knowledge 청크가 없습니다.")

        dataset_versions = {chunk.metadata.dataset_version for chunk in chunks}
        if len(dataset_versions) != 1:
            raise ValueError("하나의 release에는 하나의 dataset_version만 허용됩니다.")
        if any(not chunk.metadata.index_eligible for chunk in chunks):
            raise ValueError("인덱싱 대상이 아닌 Knowledge 청크가 포함되었습니다.")
        self._validate_interaction_metadata(chunks)

        await self._vector_store.create_release_collection()
        vectors: list[list[float]] = []
        for start in range(0, len(chunks), self._embedding_batch_size):
            batch = chunks[start : start + self._embedding_batch_size]
            batch_vectors = await self._embedding_provider.embed_documents([chunk.embedding_text for chunk in batch])
            if len(batch_vectors) != len(batch):
                raise ValueError("임베딩 배치의 문서 수와 벡터 수가 일치하지 않습니다.")
            vectors.extend(batch_vectors)

        for start in range(0, len(chunks), self._upsert_batch_size):
            end = start + self._upsert_batch_size
            await self._vector_store.upsert_chunks(
                chunks[start:end],
                vectors[start:end],
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
        )

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
                    "상호작용 메타데이터에는 유효한 유형과 유형별 대상이 "
                    f"필요합니다: chunk_id={chunk.chunk_id}"
                ) from None

            drug_count = len(set(metadata.drug_names))
            ingredient_count = len(set(metadata.ingredient_names))
            valid_entity_counts = {
                InteractionPairType.DRUG_DRUG: drug_count >= 2,
                InteractionPairType.DRUG_SUPPLEMENT: drug_count >= 1 and ingredient_count >= 1,
                InteractionPairType.SUPPLEMENT_SUPPLEMENT: ingredient_count >= 2,
                # Knowledge metadata does not store food_names. The food entity
                # is represented by the validated pair key and source content.
                InteractionPairType.DRUG_FOOD: drug_count >= 1,
            }
            if not valid_entity_counts[interaction_type]:
                raise ValueError(
                    "상호작용 메타데이터에는 유효한 유형과 유형별 대상이 "
                    f"필요합니다: chunk_id={chunk.chunk_id}"
                )
