import argparse
import json
from pathlib import Path

from ai_worker.services.knowledge_recovery_manifest_service import (
    KnowledgeRecoveryManifestService,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="부분 승인 청크와 OCR 대기 문서의 복원 매니페스트를 생성합니다.",
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
        "--corpus-quality-audit",
        type=Path,
        default=Path(
            "data/knowledge/processed/full-v4-o200k-partial-dry-run/"
            "reports/corpus-quality-audit.json",
        ),
    )
    parser.add_argument(
        "--release-chunks-dir",
        type=Path,
        default=Path(
            "data/knowledge/processed/full-v4-o200k-partial-dry-run/"
            "release/chunks",
        ),
    )
    parser.add_argument(
        "--ocr-queue",
        type=Path,
        default=Path(
            "data/knowledge/processed/full-v4-o200k-partial-dry-run/"
            "reports/ocr-required.jsonl",
        ),
    )
    parser.add_argument(
        "--partial-output",
        type=Path,
        default=Path("data/knowledge/manifests/partial_chunk_recovery_manifest.jsonl"),
    )
    parser.add_argument(
        "--ocr-output",
        type=Path,
        default=Path("data/knowledge/manifests/knowledge_ocr_manifest.jsonl"),
    )
    parser.add_argument(
        "--skip-source-hash-validation",
        action="store_true",
        help="테스트·메타데이터 점검용으로만 원본 PDF SHA-256 검증을 생략합니다.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = args.repo_root.resolve()
    service = KnowledgeRecoveryManifestService()
    result = service.build(
        documents_path=repo_root / args.documents,
        sources_path=repo_root / args.sources,
        corpus_quality_audit_path=repo_root / args.corpus_quality_audit,
        release_chunks_dir=repo_root / args.release_chunks_dir,
        ocr_queue_path=repo_root / args.ocr_queue,
    )
    if not args.skip_source_hash_validation:
        service.validate_source_files(result=result, repo_root=repo_root)
    service.write(
        result=result,
        partial_manifest_path=repo_root / args.partial_output,
        ocr_manifest_path=repo_root / args.ocr_output,
    )
    print(
        json.dumps(
            {
                "partial_document_count": result.partial_document_count,
                "pending_chunk_count": result.pending_chunk_count,
                "ocr_document_count": result.ocr_document_count,
            },
            ensure_ascii=False,
        ),
    )


if __name__ == "__main__":
    main()
