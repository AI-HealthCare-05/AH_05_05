import argparse
import json
from pathlib import Path

from ai_worker.rag.loaders.knowledge_document_loader_router import (
    KnowledgeDocumentLoaderRouter,
)
from ai_worker.rag.loaders.knowledge_ocr_artifact_loader import KnowledgeOcrArtifactLoader
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
        action="append",
        default=None,
        help="대표 문서 품질 보고서입니다. 여러 번 지정할 수 있습니다.",
    )
    parser.add_argument(
        "--pilot-manifest",
        type=Path,
        action="append",
        default=None,
        help=("대표 문서에서 승인한 텍스트 복원·섹션·청크 검수 정보를 전체 Manifest에 상속합니다."),
    )
    parser.add_argument(
        "--baseline-quality-report",
        type=Path,
        default=None,
        help="기존 릴리스와의 복원량을 비교할 preprocessing-quality.json 경로입니다.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/knowledge/processed/full"),
    )
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument(
        "--tokenizer-encoding",
        choices=("cl100k_base", "o200k_base"),
        default="cl100k_base",
        help=("청크 토큰 수 계산에 사용할 tiktoken encoding입니다."),
    )
    parser.add_argument(
        "--interaction-annotations",
        type=Path,
        default=Path("data/knowledge/manifests/interaction_annotations.yaml"),
    )
    parser.add_argument(
        "--ocr-artifact-root",
        type=Path,
        default=None,
        help="완료된 OCR artifact가 있을 때 OCR_REQUIRED 문서를 함께 전처리합니다.",
    )
    return parser.parse_args()


def build_splitter(
    *,
    tokenizer_encoding: str,
    interaction_annotations: KnowledgeInteractionAnnotationRegistry | None,
) -> KnowledgeSplitter:
    return KnowledgeSplitter(
        interaction_annotations=interaction_annotations,
        tokenizer_encoding=tokenizer_encoding,
    )


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    pilot_quality_reports = args.pilot_quality_report or [
        Path("data/knowledge/processed/reports/preprocessing-quality.json"),
    ]
    interaction_annotations = KnowledgeInteractionAnnotationRegistry.from_yaml(repo_root / args.interaction_annotations)
    pdf_loader = KnowledgePdfLoader()
    ocr_artifact_root = repo_root / args.ocr_artifact_root if args.ocr_artifact_root is not None else None
    loader = (
        KnowledgeDocumentLoaderRouter(
            pdf_loader=pdf_loader,
            ocr_loader=KnowledgeOcrArtifactLoader(artifact_root=ocr_artifact_root),
            ocr_artifact_root=ocr_artifact_root,
        )
        if ocr_artifact_root is not None
        else pdf_loader
    )
    pilot_service = KnowledgePilotPreprocessingService(
        repo_root=repo_root,
        loader=loader,
        normalizer=KnowledgeNormalizer(),
        splitter=build_splitter(
            tokenizer_encoding=args.tokenizer_encoding,
            interaction_annotations=interaction_annotations,
        ),
    )
    result = KnowledgeCorpusPreprocessingService(
        pilot_service=pilot_service,
    ).preprocess(
        documents_path=repo_root / args.documents,
        sources_path=repo_root / args.sources,
        pilot_quality_report_paths=[repo_root / path for path in pilot_quality_reports],
        pilot_manifest_paths=(
            [repo_root / path for path in args.pilot_manifest] if args.pilot_manifest is not None else None
        ),
        output_root=repo_root / args.output,
        dataset_version=args.dataset_version,
        baseline_quality_report_path=(
            repo_root / args.baseline_quality_report if args.baseline_quality_report is not None else None
        ),
        ocr_artifact_root=ocr_artifact_root,
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
