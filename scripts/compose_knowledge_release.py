import argparse
import json
from pathlib import Path

from ai_worker.services.knowledge_release_composition_service import (
    KnowledgeReleaseCompositionInput,
    KnowledgeReleaseCompositionService,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "품질 승인된 여러 Knowledge release를 중복 검사 후 새 dataset version의 불변 release로 조합합니다."
        )
    )
    parser.add_argument(
        "--input",
        action="append",
        nargs=2,
        metavar=("CHUNKS_DIR", "QUALITY_REPORT"),
        required=True,
        help="조합할 청크 디렉터리와 preprocessing-quality.json 경로",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    args = parser.parse_args(argv)
    if not args.dataset_version.strip():
        parser.error("--dataset-version은 비어 있을 수 없습니다.")
    return args


def main() -> None:
    args = parse_args()
    inputs = [
        KnowledgeReleaseCompositionInput(
            chunks_dir=Path(chunks_dir),
            quality_report_path=Path(quality_report),
        )
        for chunks_dir, quality_report in args.input
    ]
    result = KnowledgeReleaseCompositionService().compose(
        inputs=inputs,
        output_root=args.output,
        dataset_version=args.dataset_version,
    )
    print(
        json.dumps(
            {
                "dataset_version": result.dataset_version,
                "processed_document_count": result.processed_document_count,
                "chunk_count": result.chunk_count,
                "ready_for_bulk_source_ids": result.ready_for_bulk_source_ids,
                "quality_report_path": str(args.output / "reports" / "preprocessing-quality.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
