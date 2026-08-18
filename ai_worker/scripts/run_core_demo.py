import argparse
import asyncio
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)
from qdrant_client import AsyncQdrantClient

from ai_worker.llm.generators.recovery_guide_generator import (
    OpenAIRecoveryGuideGenerator,
)
from ai_worker.providers.json_patient_context_provider import (
    JsonPatientContextProvider,
)
from ai_worker.rag.embeddings.openai_embedding_provider import (
    OpenAIEmbeddingProvider,
)
from ai_worker.rag.indexers.guideline_indexer import (
    GuidelineIndexer,
)
from ai_worker.rag.loaders.pdf_loader import PdfLoader
from ai_worker.rag.query_builders.patient_query_builder import (
    PatientQueryBuilder,
)
from ai_worker.rag.resolvers.guideline_conflict_resolver import (
    RuleBasedGuidelineConflictResolver,
)
from ai_worker.rag.retrievers.guideline_retriever import (
    GuidelineRetriever,
)
from ai_worker.rag.splitters.guideline_splitter import (
    GuidelineSplitter,
)
from ai_worker.rag.vectorstores.qdrant_guideline_store import (
    QdrantGuidelineStore,
)
from ai_worker.safety.output_safety_validator import (
    RuleBasedOutputSafetyValidator,
)
from ai_worker.schemas.guideline import (
    GuidelineMetadata,
)
from ai_worker.use_cases.generate_recovery_guide import (
    GenerateRecoveryGuideUseCase,
)


class DemoSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    OPENAI_API_KEY: SecretStr
    OPENAI_CHAT_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = (
        "text-embedding-3-small"
    )
    OPENAI_EMBEDDING_DIMENSIONS: int = 1536
    QDRANT_COLLECTION: str = (
        "public_guidelines_small_v1"
    )
    RAG_MIN_SIMILARITY_SCORE: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
    )

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "퇴원 환자 회복 가이드 "
            "Core End-to-End 데모"
        )
    )

    parser.add_argument(
        "--patient-json",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--user-id",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--care-episode-id",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--document-id",
        required=True,
    )
    parser.add_argument(
        "--title",
        required=True,
    )
    parser.add_argument(
        "--organization",
        default=None,
    )
    parser.add_argument(
        "--dataset-version",
        default=None,
    )
    parser.add_argument(
        "--publication-year",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--language",
        default="en",
    )
    parser.add_argument(
        "--condition",
        required=True,
    )
    parser.add_argument(
        "--topic",
        required=True,
    )
    parser.add_argument(
        "--care-phase",
        default="POST_DISCHARGE",
    )
    parser.add_argument(
        "--source-url",
        default=None,
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=200,
    )

    return parser.parse_args()


async def run_demo(
    args: argparse.Namespace,
) -> None:
    settings = DemoSettings()

    qdrant_client = AsyncQdrantClient(
        location=":memory:"
    )

    try:
        embedding_provider = (
            OpenAIEmbeddingProvider(
                model=(
                    settings
                    .OPENAI_EMBEDDING_MODEL
                ),
                dimensions=(
                    settings
                    .OPENAI_EMBEDDING_DIMENSIONS
                ),
                api_key=(
                    settings.OPENAI_API_KEY
                ),
            )
        )

        vector_store = QdrantGuidelineStore(
            client=qdrant_client,
            collection_name=(
                settings.QDRANT_COLLECTION
            ),
            vector_size=(
                settings
                .OPENAI_EMBEDDING_DIMENSIONS
            ),
        )

        indexer = GuidelineIndexer(
            loader=PdfLoader(),
            splitter=GuidelineSplitter(
                chunk_size=args.chunk_size,
                chunk_overlap=(
                    args.chunk_overlap
                ),
            ),
            embedding_provider=(
                embedding_provider
            ),
            vector_store=vector_store,
        )

        metadata = GuidelineMetadata(
            dataset_key="PUBLIC_GUIDELINE",
            dataset_version=(
                args.dataset_version
            ),
            document_id=args.document_id,
            title=args.title,
            organization=args.organization,
            publication_year=(
                args.publication_year
            ),
            language=args.language,
            document_type="GUIDELINE",
            condition=(
                args.condition.strip().upper()
            ),
            care_phase=(
                args.care_phase.strip().upper()
            ),
            topic=args.topic.strip().upper(),
            source_url=args.source_url,
        )

        point_ids = await indexer.index_pdf(
            pdf_path=args.pdf,
            metadata=metadata,
        )

        print(
            f"Qdrant 인덱싱 완료: "
            f"{len(point_ids)}개 Chunk"
        )

        retriever = GuidelineRetriever(
            embedding_provider=(
                embedding_provider
            ),
            vector_store=vector_store,
            min_similarity_score=(
                settings.RAG_MIN_SIMILARITY_SCORE
            ),
        )

        use_case = GenerateRecoveryGuideUseCase(
            patient_context_provider=(
                JsonPatientContextProvider(
                    args.patient_json
                )
            ),
            query_builder=PatientQueryBuilder(),
            retriever=retriever,
            conflict_resolver=(
                RuleBasedGuidelineConflictResolver()
            ),
            guide_generator=(
                OpenAIRecoveryGuideGenerator(
                    model=(
                        settings
                        .OPENAI_CHAT_MODEL
                    ),
                    api_key=(
                        settings.OPENAI_API_KEY
                    ),
                )
            ),
            safety_validator=(
                RuleBasedOutputSafetyValidator()
            ),
        )

        result = await use_case.execute(
            user_id=args.user_id,
            care_episode_id=(
                args.care_episode_id
            ),
            condition=args.condition,
            topic=args.topic,
            care_phase=args.care_phase,
            limit=args.limit,
        )

        print("\n최종 회복 가이드")
        print(result.model_dump_json(indent=2))
    finally:
        await qdrant_client.close()


def main() -> None:
    args = parse_args()
    asyncio.run(run_demo(args))


if __name__ == "__main__":
    main()
