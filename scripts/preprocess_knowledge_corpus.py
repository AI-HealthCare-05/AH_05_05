import argparse
import json
from pathlib import Path

import yaml

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
from ai_worker.schemas.knowledge_manifest import (
    KnowledgeOcrDocumentSelectionDecision,
    KnowledgeOcrDocumentSelectionManifest,
)
from ai_worker.services.knowledge_corpus_preprocessing_service import (
    KnowledgeCorpusPreprocessingService,
)
from ai_worker.services.knowledge_pilot_preprocessing_service import (
    KnowledgePilotPreprocessingService,
)

DEFAULT_PILOT_MANIFEST_PATHS = (
    Path("data/knowledge/manifests/pilot_manifest.json"),
    Path("data/knowledge/manifests/additional_research_bulk_manifest.json"),
)


def resolve_pilot_manifest_paths(
    pilot_manifest_paths: list[Path] | None,
) -> list[Path]:
    """Use every verified pilot manifest unless an explicit list is requested."""
    if pilot_manifest_paths is not None:
        return pilot_manifest_paths
    return list(DEFAULT_PILOT_MANIFEST_PATHS)


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
    parser.add_argument(
        "--ocr-document-selection",
        type=Path,
        default=Path("data/knowledge/manifests/ocr_document_selection.yaml"),
        help=("OCR_REQUIRED 문서 중 챗봇 근거로 허용할 문서를 정한 allowlist 매니페스트입니다."),
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=0,
        help=("N개 문서마다 진행 상황을 출력합니다. 0이면 출력하지 않습니다."),
    )
    parser.add_argument(
        "--document-start",
        type=int,
        default=0,
        help=("전체 승인 Manifest에서 처리할 시작 인덱스(0부터)입니다."),
    )
    parser.add_argument(
        "--document-end",
        type=int,
        default=None,
        help=("전체 승인 Manifest에서 처리할 끝 인덱스(끝 제외)입니다."),
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help=("문서별 상세 보고서 대신 release 집계만 출력합니다."),
    )
    args = parser.parse_args()
    if args.progress_every < 0:
        parser.error("--progress-every는 0 이상이어야 합니다.")
    if args.document_start < 0:
        parser.error("--document-start는 0 이상이어야 합니다.")
    if args.document_end is not None and args.document_end <= args.document_start:
        parser.error("--document-end는 --document-start보다 커야 합니다.")
    return args


def build_splitter(
    *,
    tokenizer_encoding: str,
    interaction_annotations: KnowledgeInteractionAnnotationRegistry | None,
) -> KnowledgeSplitter:
    return KnowledgeSplitter(
        interaction_annotations=interaction_annotations,
        tokenizer_encoding=tokenizer_encoding,
    )


def load_selected_ocr_document_ids(selection_path: Path) -> set[str]:
    manifest = KnowledgeOcrDocumentSelectionManifest.model_validate(
        yaml.safe_load(Path(selection_path).read_text(encoding="utf-8")),
    )
    return {
        selection.document_id
        for selection in manifest.selections
        if selection.decision == KnowledgeOcrDocumentSelectionDecision.INCLUDE
    }


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    pilot_quality_reports = args.pilot_quality_report or [
        Path("data/knowledge/processed/reports/preprocessing-quality.json"),
    ]
    pilot_manifest_paths = resolve_pilot_manifest_paths(args.pilot_manifest)
    interaction_annotations = KnowledgeInteractionAnnotationRegistry.from_yaml(repo_root / args.interaction_annotations)
    pdf_loader = KnowledgePdfLoader()
    ocr_artifact_root = repo_root / args.ocr_artifact_root if args.ocr_artifact_root is not None else None
    ocr_document_selection_path = repo_root / args.ocr_document_selection
    selected_ocr_document_ids = load_selected_ocr_document_ids(ocr_document_selection_path)
    loader = (
        KnowledgeDocumentLoaderRouter(
            pdf_loader=pdf_loader,
            ocr_loader=KnowledgeOcrArtifactLoader(artifact_root=ocr_artifact_root),
            ocr_artifact_root=ocr_artifact_root,
            ocr_document_ids=selected_ocr_document_ids,
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
    progress_callback = None
    if args.progress_every:

        def progress_callback(
            current: int,
            total: int,
            document_id: str,
        ) -> None:
            if current == 1 or current == total or current % args.progress_every == 0:
                print(
                    json.dumps(
                        {
                            "progress": current,
                            "total": total,
                            "document_id": document_id,
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )

    result = KnowledgeCorpusPreprocessingService(
        pilot_service=pilot_service,
    ).preprocess(
        documents_path=repo_root / args.documents,
        sources_path=repo_root / args.sources,
        pilot_quality_report_paths=[repo_root / path for path in pilot_quality_reports],
        pilot_manifest_paths=[repo_root / path for path in pilot_manifest_paths],
        output_root=repo_root / args.output,
        dataset_version=args.dataset_version,
        baseline_quality_report_path=(
            repo_root / args.baseline_quality_report if args.baseline_quality_report is not None else None
        ),
        ocr_artifact_root=ocr_artifact_root,
        ocr_document_selection_path=ocr_document_selection_path,
        progress_callback=progress_callback,
        document_start=args.document_start,
        document_end=args.document_end,
    )
    payload = (
        {
            "dataset_version": result.dataset_version,
            "processed_document_count": result.processed_document_count,
            "chunk_count": result.chunk_count,
            "skipped_document_count": len(result.skipped_documents),
            "ready_for_bulk_source_ids": result.ready_for_bulk_source_ids,
            "quality_report_path": str(args.output / "reports" / "preprocessing-quality.json"),
        }
        if args.summary_only
        else result.model_dump(mode="json")
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
