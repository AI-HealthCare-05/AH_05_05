import argparse
import asyncio
import json
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
)
from ai_worker.rag.loaders.knowledge_chunk_loader import (
    KnowledgeChunkLoader,
)
from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.rag.vectorstores.qdrant_knowledge_store import (
    QdrantKnowledgeStore,
)
from ai_worker.schemas.knowledge import (
    KnowledgeAccessScope,
    KnowledgeChunk,
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
    args = parser.parse_args(argv)
    if args.embedding_batch_size <= 0:
        parser.error("--embedding-batch-size는 1 이상이어야 합니다.")
    if args.upsert_batch_size <= 0:
        parser.error("--upsert-batch-size는 1 이상이어야 합니다.")
    if not args.dataset_version.strip():
        parser.error("--dataset-version은 비어 있을 수 없습니다.")
    if not args.collection.strip():
        parser.error("--collection은 비어 있을 수 없습니다.")
    return args


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
    )
    vector_store = QdrantKnowledgeStore(
        client=qdrant_client,
        collection_name=args.collection,
        vector_size=settings.OPENAI_EMBEDDING_DIMENSIONS,
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
) -> KnowledgeIndexResult:
    resolved_settings = settings or Config()
    qdrant_client = create_qdrant_client(resolved_settings)
    try:
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
        ensure_external_embedding_allowed(
            chunks,
            allow_demo_restricted=args.allow_demo_restricted,
        )
        indexer = build_indexer(
            settings=resolved_settings,
            args=args,
            qdrant_client=qdrant_client,
        )
        return await indexer.index_release(chunks)
    finally:
        await qdrant_client.close()


def main() -> None:
    result = asyncio.run(run_cli(args=parse_args()))
    metadata_quality = result.metadata_quality
    print(
        json.dumps(
            {
                "dataset_version": result.dataset_version,
                "collection_name": result.collection_name,
                "indexed_chunk_count": result.indexed_chunk_count,
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
