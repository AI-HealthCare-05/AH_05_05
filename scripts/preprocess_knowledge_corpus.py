import argparse
import json
from pathlib import Path

from ai_worker.rag.loaders.knowledge_pdf_loader import KnowledgePdfLoader
from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.rag.normalizers.knowledge_normalizer import KnowledgeNormalizer
from ai_worker.rag.splitters.knowledge_splitter import KnowledgeSplitter
from ai_worker.services.knowledge_corpus_preprocessing_service import (
    KnowledgeCorpusPreprocessingService,
)
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgePilotPreprocessingService,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("품질 승인된 PUBLIC·DEMO_RESTRICTED PDF 전체를 release 청크로 전처리합니다."),
    )
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--documents",
        type=Path,
        default=Path("data/knowledge/manifests/documents.jsonl"),
    )
    parser.add_argument(
        "--sources",
        type=Path,
        default=Path("data/knowledge/manifests/sources.yaml"),
    )
    parser.add_argument(
        "--pilot-quality-report",
        type=Path,
        default=Path("data/knowledge/processed/reports/preprocessing-quality.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/knowledge/processed/full"),
    )
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument(
        "--interaction-annotations",
        type=Path,
        default=Path("data/knowledge/manifests/interaction_annotations.yaml"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    interaction_annotations = KnowledgeInteractionAnnotationRegistry.from_yaml(repo_root / args.interaction_annotations)
    pilot_service = KnowledgePilotPreprocessingService(
        repo_root=repo_root,
        loader=KnowledgePdfLoader(),
        normalizer=KnowledgeNormalizer(),
        splitter=KnowledgeSplitter(
            interaction_annotations=interaction_annotations,
        ),
    )
    result = KnowledgeCorpusPreprocessingService(
        pilot_service=pilot_service,
    ).preprocess(
        documents_path=repo_root / args.documents,
        sources_path=repo_root / args.sources,
        pilot_quality_report_path=repo_root / args.pilot_quality_report,
        output_root=repo_root / args.output,
        dataset_version=args.dataset_version,
    )
    print(
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
