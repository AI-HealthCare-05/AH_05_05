import argparse
import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from pydantic import SecretStr
from qdrant_client import AsyncQdrantClient

from ai_worker.core.config import Config
from ai_worker.domain.errors import AIConfigurationError
from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from ai_worker.rag.indexers.knowledge_indexer import (
    KnowledgeIndexer,
    KnowledgeIndexResult,
    KnowledgeMetadataQualityReport,
)
from ai_worker.rag.loaders.knowledge_chunk_loader import (
    KnowledgeChunkLoader,
)
from ai_worker.rag.metadata.entity_name_policy import (
    is_generic_knowledge_entity_category,
)
from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.rag.vectorstores.qdrant_knowledge_store import (
    QdrantKnowledgeStore,
)
from ai_worker.schemas.interaction import InteractionEntityKind, InteractionPairType
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunk,
    KnowledgeVectorDistance,
)
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgePilotPreprocessingResult,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="전처리된 약·영양제 청크를 새 Qdrant release에 적재합니다.")
    parser.add_argument(
        "--chunks-dir",
        type=Path,
        default=Path("data/knowledge/processed/chunks"),
    )
    parser.add_argument(
        "--quality-report",
        type=Path,
        default=Path("data/knowledge/processed/reports/preprocessing-quality.json"),
    )
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--embedding-batch-size", type=int, default=64)
    parser.add_argument("--upsert-batch-size", type=int, default=64)
    parser.add_argument(
        "--distance",
        type=KnowledgeVectorDistance,
        choices=list(KnowledgeVectorDistance),
        default=KnowledgeVectorDistance.COSINE,
        help=("Qdrant dense 거리 방식. DOT은 문서·질의 임베딩을 L2 정규화한 뒤 사용합니다."),
    )
    parser.add_argument(
        "--interaction-annotations",
        type=Path,
        default=None,
        help=("v2 상호작용 메타데이터 release에서 모든 검수 주석이 청크에 적용됐는지 확인할 YAML 경로"),
    )
    parser.add_argument(
        "--allow-demo-restricted",
        action="store_true",
        help=("DEMO_RESTRICTED 청크를 외부 OpenAI 임베딩 API로 전송하는 것을 명시적으로 허용합니다."),
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help=("Qdrant 생성·OpenAI 임베딩 전송 없이 release metadata 계약만 검증합니다."),
    )
    parser.add_argument(
        "--baseline-chunks-dir",
        type=Path,
        default=None,
        help=("기존 release 청크와 content·embedding text 재사용 가능성을 비교할 경로입니다."),
    )
    parser.add_argument(
        "--baseline-dataset-version",
        default=None,
        help=("--baseline-chunks-dir의 dataset_version입니다."),
    )
    parser.add_argument(
        "--reuse-vectors-from-collection",
        default=None,
        help=(
            "--baseline-chunks-dir과 동일한 release의 Qdrant 컬렉션입니다. "
            "embedding_text가 완전히 같은 청크의 벡터만 재사용합니다."
        ),
    )
    args = parser.parse_args(argv)
    if args.embedding_batch_size <= 0:
        parser.error("--embedding-batch-size는 1 이상이어야 합니다.")
    if args.upsert_batch_size <= 0:
        parser.error("--upsert-batch-size는 1 이상이어야 합니다.")
    if not args.dataset_version.strip():
        parser.error("--dataset-version은 비어 있을 수 없습니다.")
    if not args.collection.strip():
        parser.error("--collection은 비어 있을 수 없습니다.")
    if args.baseline_chunks_dir is not None and not (
        args.baseline_dataset_version and args.baseline_dataset_version.strip()
    ):
        parser.error("--baseline-chunks-dir에는 --baseline-dataset-version이 필요합니다.")
    if args.reuse_vectors_from_collection is not None and args.baseline_chunks_dir is None:
        parser.error("--reuse-vectors-from-collection에는 --baseline-chunks-dir이 필요합니다.")
    return args


@dataclass(frozen=True)
class KnowledgeSourceBackedMetadataStats:
    """새 release가 질문 해석용 typed metadata를 빠짐없이 포함하는지 요약한다."""

    interaction_chunk_count: int
    drug_food_chunk_count: int
    food_alias_entry_count: int


@dataclass(frozen=True)
class KnowledgeReleasePreflightResult:
    """외부 전송 전 확인 가능한 release 승인 자료."""

    dataset_version: str
    collection_name: str
    chunk_count: int
    document_count: int
    demo_restricted_chunk_count: int
    metadata_quality: KnowledgeMetadataQualityReport
    source_backed_metadata: KnowledgeSourceBackedMetadataStats
    embedding_reuse: "KnowledgeEmbeddingReuseStats | None" = None


@dataclass(frozen=True)
class KnowledgeEmbeddingReuseStats:
    """기존 벡터를 안전하게 재사용할 수 있는지를 embedding text 기준으로 판정한다."""

    baseline_chunk_count: int
    candidate_chunk_count: int
    content_hash_match_count: int
    exact_embedding_text_reuse_count: int
    reembedding_required_count: int


type KnowledgeReleaseCommandResult = KnowledgeIndexResult | KnowledgeReleasePreflightResult


def create_qdrant_client(settings: Config) -> AsyncQdrantClient:
    return AsyncQdrantClient(
        url=settings.QDRANT_URL,
        timeout=settings.QDRANT_TIMEOUT_SECONDS,
    )


def require_api_key(settings: Config) -> SecretStr:
    api_key = settings.OPENAI_API_KEY
    if api_key is None or not api_key.get_secret_value().strip():
        raise AIConfigurationError("Knowledge release 인덱싱에는 OPENAI_API_KEY가 필요합니다.")
    return api_key


def load_release_chunks(args: argparse.Namespace) -> list[KnowledgeChunk]:
    return KnowledgeChunkLoader().load(
        args.chunks_dir,
        expected_dataset_version=args.dataset_version,
    )


def assess_embedding_reuse(
    *,
    candidate_chunks: list[KnowledgeChunk],
    baseline_chunks: list[KnowledgeChunk],
) -> KnowledgeEmbeddingReuseStats:
    """본문 hash가 같아도 임베딩 입력이 바뀌면 재임베딩하도록 보수적으로 계산한다."""
    baseline_content_hashes = {chunk.metadata.content_hash for chunk in baseline_chunks}
    baseline_embedding_hashes = {
        hashlib.sha256(chunk.embedding_text.encode("utf-8")).hexdigest() for chunk in baseline_chunks
    }
    content_hash_match_count = sum(chunk.metadata.content_hash in baseline_content_hashes for chunk in candidate_chunks)
    exact_embedding_text_reuse_count = sum(
        hashlib.sha256(chunk.embedding_text.encode("utf-8")).hexdigest() in baseline_embedding_hashes
        for chunk in candidate_chunks
    )
    return KnowledgeEmbeddingReuseStats(
        baseline_chunk_count=len(baseline_chunks),
        candidate_chunk_count=len(candidate_chunks),
        content_hash_match_count=content_hash_match_count,
        exact_embedding_text_reuse_count=exact_embedding_text_reuse_count,
        reembedding_required_count=(len(candidate_chunks) - exact_embedding_text_reuse_count),
    )


async def load_reusable_vectors_from_collection(
    *,
    client: AsyncQdrantClient,
    collection_name: str,
    baseline_chunks: list[KnowledgeChunk],
    batch_size: int = 128,
) -> dict[str, list[float]]:
    """검증된 baseline의 동일 embedding_text에만 원본 Qdrant 벡터를 연결한다."""
    if batch_size <= 0:
        raise ValueError("벡터 재사용 조회 배치 크기는 1 이상이어야 합니다.")

    expected_texts = {chunk.embedding_text for chunk in baseline_chunks}
    if not expected_texts:
        raise ValueError("벡터 재사용 기준 청크가 없습니다.")

    reused_vectors: dict[str, list[float]] = {}
    offset = None
    while True:
        points, next_offset = await client.scroll(
            collection_name=collection_name,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )
        for point in points:
            payload = point.payload or {}
            embedding_text = payload.get("embedding_text")
            if not isinstance(embedding_text, str) or embedding_text not in expected_texts:
                continue
            vector = point.vector
            if not isinstance(vector, list) or not all(isinstance(value, (int, float)) for value in vector):
                raise ValueError("벡터 재사용 원본은 단일 Dense 벡터 구조여야 합니다.")
            normalized_vector = [float(value) for value in vector]
            previous_vector = reused_vectors.get(embedding_text)
            if previous_vector is not None and previous_vector != normalized_vector:
                raise ValueError("같은 embedding_text에 서로 다른 원본 벡터가 있습니다.")
            reused_vectors[embedding_text] = normalized_vector
        if next_offset is None:
            break
        offset = next_offset

    missing_texts = expected_texts - reused_vectors.keys()
    if missing_texts:
        raise ValueError(
            f"벡터 재사용 원본 컬렉션에 baseline embedding_text가 없습니다: missing_count={len(missing_texts)}"
        )
    return reused_vectors


def ensure_preprocessing_approved(
    chunks: list[KnowledgeChunk],
    *,
    quality_report_path: Path,
    expected_dataset_version: str,
) -> None:
    path = Path(quality_report_path)
    if not path.is_file():
        raise ValueError("전처리 품질 보고서가 없습니다. 대표 문서 자동 검사와 수동 승인을 먼저 완료하세요.")

    report = KnowledgePilotPreprocessingResult.model_validate_json(path.read_text(encoding="utf-8"))
    if report.dataset_version != expected_dataset_version:
        raise ValueError("전처리 품질 보고서와 인덱싱 대상의 dataset_version이 일치하지 않습니다.")

    actual_chunk_count = len(chunks)
    if report.chunk_count != actual_chunk_count:
        raise ValueError(
            "전처리 품질 보고서의 청크 수와 인덱싱 대상의 "
            f"청크 수가 일치하지 않습니다: report={report.chunk_count}, "
            f"actual={actual_chunk_count}"
        )

    actual_document_count = len({chunk.metadata.document_id for chunk in chunks})
    if report.processed_document_count != actual_document_count:
        raise ValueError(
            "전처리 품질 보고서의 문서 수와 인덱싱 대상의 "
            "문서 수가 일치하지 않습니다: "
            f"report={report.processed_document_count}, "
            f"actual={actual_document_count}"
        )

    ready_sources = set(report.ready_for_bulk_source_ids)
    chunk_sources = {chunk.metadata.source_id for chunk in chunks}
    unapproved_sources = sorted(chunk_sources - ready_sources)
    if unapproved_sources:
        raise ValueError(
            "자동 품질 검사와 수동 승인이 완료되지 않은 출처가 포함되어 있습니다: " + ", ".join(unapproved_sources)
        )


def ensure_external_embedding_allowed(
    chunks: list[KnowledgeChunk],
    *,
    allow_demo_restricted: bool,
) -> None:
    restricted_count = sum(chunk.metadata.access_scope == KnowledgeAccessScope.DEMO_RESTRICTED for chunk in chunks)
    if restricted_count and not allow_demo_restricted:
        raise ValueError(
            "DEMO_RESTRICTED 청크가 "
            f"{restricted_count}개 포함되어 있습니다. 외부 OpenAI "
            "임베딩 API 전송을 승인한 경우에만 "
            "--allow-demo-restricted를 지정하세요."
        )


def ensure_interaction_annotations_applied(
    chunks: list[KnowledgeChunk],
    *,
    annotation_path: Path | None,
) -> None:
    if annotation_path is None:
        return

    registry = KnowledgeInteractionAnnotationRegistry.from_yaml(Path(annotation_path))
    required_by_document = registry.required_pair_keys_by_document()
    if not required_by_document:
        raise ValueError("상호작용 주석 계약에 검증할 조합이 없습니다.")

    observed_by_document: dict[str, set[str]] = {}
    for chunk in chunks:
        observed_by_document.setdefault(
            chunk.metadata.document_id,
            set(),
        ).update(chunk.metadata.interaction_pair_keys)

    missing_by_document = {
        document_id: sorted(set(required_pair_keys) - observed_by_document.get(document_id, set()))
        for document_id, required_pair_keys in required_by_document.items()
        if set(required_pair_keys) - observed_by_document.get(document_id, set())
    }
    if missing_by_document:
        details = "; ".join(
            f"{document_id}={','.join(pair_keys)}" for document_id, pair_keys in sorted(missing_by_document.items())
        )
        raise ValueError("검수된 상호작용 주석이 전처리 청크에 모두 적용되지 않았습니다: " + details)


def ensure_source_backed_interaction_metadata(
    chunks: list[KnowledgeChunk],
) -> KnowledgeSourceBackedMetadataStats:
    """DRUG_FOOD 청크에 음식 정식명·별칭·pair key가 함께 있는지 차단한다."""
    interaction_chunk_count = 0
    drug_food_chunk_count = 0
    food_alias_entry_count = 0

    for chunk in chunks:
        metadata = chunk.metadata
        _ensure_no_generic_catalog_entities(chunk)
        if metadata.interaction_type is not None:
            interaction_chunk_count += 1
        if metadata.interaction_type != InteractionPairType.DRUG_FOOD.value:
            continue

        drug_food_chunk_count += 1
        if not metadata.food_names:
            raise ValueError(
                f"DRUG_FOOD 청크에는 food_names가 필요합니다: chunk_id={chunk.chunk_id}",
            )
        if not metadata.interaction_pair_keys:
            raise ValueError(
                f"DRUG_FOOD 청크에는 interaction_pair_keys가 필요합니다: chunk_id={chunk.chunk_id}",
            )

        food_entries = [entry for entry in metadata.entity_catalog_entries if entry.kind == InteractionEntityKind.FOOD]
        if not food_entries:
            raise ValueError(
                f"DRUG_FOOD 청크에는 FOOD typed catalog entry가 필요합니다: chunk_id={chunk.chunk_id}",
            )
        catalog_food_names = {entry.canonical_name for entry in food_entries}
        missing_food_names = sorted(set(metadata.food_names) - catalog_food_names)
        if missing_food_names:
            raise ValueError(
                "DRUG_FOOD food_names가 FOOD typed catalog entry와 일치하지 않습니다: "
                f"chunk_id={chunk.chunk_id}, missing={','.join(missing_food_names)}",
            )
        invalid_aliases = [entry.canonical_name for entry in food_entries if entry.canonical_name not in entry.aliases]
        if invalid_aliases:
            raise ValueError(
                "FOOD typed catalog entry의 aliases에는 정식명이 포함되어야 합니다: "
                f"chunk_id={chunk.chunk_id}, names={','.join(invalid_aliases)}",
            )
        food_alias_entry_count += len(food_entries)

    return KnowledgeSourceBackedMetadataStats(
        interaction_chunk_count=interaction_chunk_count,
        drug_food_chunk_count=drug_food_chunk_count,
        food_alias_entry_count=food_alias_entry_count,
    )


def _ensure_no_generic_catalog_entities(chunk: KnowledgeChunk) -> None:
    """식별 불가능한 범주명이 typed catalog에 유입되는 것을 사전에 막는다."""
    metadata = chunk.metadata
    observed_names = [
        *getattr(metadata, "drug_names", []),
        *getattr(metadata, "ingredient_names", []),
        *getattr(metadata, "food_names", []),
    ]
    for entry in getattr(metadata, "entity_catalog_entries", []):
        observed_names.extend(
            [
                entry.canonical_name,
                *entry.aliases,
            ],
        )

    generic_names = sorted(
        {name for name in observed_names if is_generic_knowledge_entity_category(name)},
    )
    if generic_names:
        raise ValueError(
            "정식 제품·성분·음식명을 식별할 수 없는 일반 범주명은 "
            "catalog metadata에 포함할 수 없습니다: "
            f"chunk_id={chunk.chunk_id}, names={','.join(generic_names)}",
        )


def build_indexer(
    *,
    settings: Config,
    args: argparse.Namespace,
    qdrant_client: AsyncQdrantClient,
) -> KnowledgeIndexer:
    embedding_provider = OpenAIEmbeddingProvider(
        model=settings.OPENAI_EMBEDDING_MODEL,
        dimensions=settings.OPENAI_EMBEDDING_DIMENSIONS,
        api_key=require_api_key(settings),
        timeout_seconds=settings.OPENAI_TIMEOUT_SECONDS,
        max_retries=settings.OPENAI_MAX_RETRIES,
        normalize_vectors=(args.distance == KnowledgeVectorDistance.DOT),
    )
    vector_store = QdrantKnowledgeStore(
        client=qdrant_client,
        collection_name=args.collection,
        vector_size=settings.OPENAI_EMBEDDING_DIMENSIONS,
        distance=args.distance,
    )
    return KnowledgeIndexer(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        embedding_batch_size=args.embedding_batch_size,
        upsert_batch_size=args.upsert_batch_size,
    )


async def run_cli(
    *,
    args: argparse.Namespace,
    settings: Config | None = None,
) -> KnowledgeReleaseCommandResult:
    resolved_settings = settings or Config()
    chunks = load_release_chunks(args)
    ensure_preprocessing_approved(
        chunks,
        quality_report_path=args.quality_report,
        expected_dataset_version=args.dataset_version,
    )
    ensure_interaction_annotations_applied(
        chunks,
        annotation_path=getattr(
            args,
            "interaction_annotations",
            None,
        ),
    )
    source_backed_metadata = ensure_source_backed_interaction_metadata(chunks)
    baseline_chunks_dir = getattr(args, "baseline_chunks_dir", None)
    baseline_chunks: list[KnowledgeChunk] | None = None
    embedding_reuse = (
        assess_embedding_reuse(
            candidate_chunks=chunks,
            baseline_chunks=(
                baseline_chunks := KnowledgeChunkLoader().load(
                    baseline_chunks_dir,
                    expected_dataset_version=args.baseline_dataset_version,
                )
            ),
        )
        if baseline_chunks_dir is not None
        else None
    )
    if getattr(args, "validate_only", False):
        return KnowledgeReleasePreflightResult(
            dataset_version=args.dataset_version,
            collection_name=args.collection,
            chunk_count=len(chunks),
            document_count=len({chunk.metadata.document_id for chunk in chunks}),
            demo_restricted_chunk_count=sum(
                chunk.metadata.access_scope == KnowledgeAccessScope.DEMO_RESTRICTED for chunk in chunks
            ),
            metadata_quality=KnowledgeIndexer.assess_metadata_quality(chunks),
            source_backed_metadata=source_backed_metadata,
            embedding_reuse=embedding_reuse,
        )

    qdrant_client = create_qdrant_client(resolved_settings)
    try:
        reusable_vectors_by_embedding_text: dict[str, list[float]] = {}
        reuse_collection = getattr(args, "reuse_vectors_from_collection", None)
        if reuse_collection is not None:
            if baseline_chunks is None:
                raise ValueError("벡터 재사용에는 baseline 청크가 필요합니다.")
            reusable_vectors_by_embedding_text = await load_reusable_vectors_from_collection(
                client=qdrant_client,
                collection_name=reuse_collection,
                baseline_chunks=baseline_chunks,
            )
        chunks_requiring_external_embeddings = [
            chunk for chunk in chunks if chunk.embedding_text not in reusable_vectors_by_embedding_text
        ]
        ensure_external_embedding_allowed(
            chunks_requiring_external_embeddings,
            allow_demo_restricted=args.allow_demo_restricted,
        )
        indexer = build_indexer(
            settings=resolved_settings,
            args=args,
            qdrant_client=qdrant_client,
        )
        return await indexer.index_release(
            chunks,
            reusable_vectors_by_embedding_text=reusable_vectors_by_embedding_text,
        )
    finally:
        await qdrant_client.close()


def main() -> None:
    result = asyncio.run(run_cli(args=parse_args()))
    if isinstance(result, KnowledgeReleasePreflightResult):
        print(
            json.dumps(
                {
                    "status": "VALIDATED",
                    **asdict(result),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    metadata_quality = result.metadata_quality
    print(
        json.dumps(
            {
                "dataset_version": result.dataset_version,
                "collection_name": result.collection_name,
                "indexed_chunk_count": result.indexed_chunk_count,
                "reused_embedding_count": result.reused_embedding_count,
                "new_embedding_count": result.new_embedding_count,
                "metadata_quality": (
                    {
                        "total_chunk_count": metadata_quality.total_chunk_count,
                        "interaction_chunk_count": metadata_quality.interaction_chunk_count,
                        "pair_key_chunk_count": metadata_quality.pair_key_chunk_count,
                        "known_evidence_count": metadata_quality.known_evidence_count,
                        "known_study_population_count": (metadata_quality.known_study_population_count),
                    }
                    if metadata_quality is not None
                    else None
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
