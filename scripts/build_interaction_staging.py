import argparse
import json
from pathlib import Path
from typing import Protocol

from ai_worker.services.interaction_staging_service import (
    InteractionStagingResult,
    InteractionStagingService,
    validate_interaction_dataset_version,
)


class InteractionStagingBuilder(Protocol):
    def build(
        self,
        *,
        input_path: Path,
        output_root: Path,
        dataset_version: str,
    ) -> InteractionStagingResult: ...


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=("식약처 DUR 병용금기 CSV를 검수 대기 RDBMS 후보 JSONL로 변환합니다."))
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/knowledge/raw/public/mfds/drug_records/DUR병용금기.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/knowledge/processed"),
    )
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument(
        "--source-id",
        default="mfds_drug_records",
    )
    parser.add_argument(
        "--document-id",
        default="mfds-dur-contraindication",
    )
    args = parser.parse_args(argv)
    for field_name in (
        "source_id",
        "document_id",
    ):
        if not getattr(args, field_name).strip():
            parser.error(f"--{field_name.replace('_', '-')}은 비어 있을 수 없습니다.")
    try:
        args.dataset_version = validate_interaction_dataset_version(args.dataset_version)
    except ValueError as error:
        parser.error(str(error))
    return args


def run_cli(
    *,
    args: argparse.Namespace,
    service: InteractionStagingBuilder | None = None,
) -> InteractionStagingResult:
    builder = service or InteractionStagingService(
        source_id=args.source_id,
        document_id=args.document_id,
    )
    result = builder.build(
        input_path=args.input,
        output_root=args.output,
        dataset_version=args.dataset_version,
    )
    print(
        json.dumps(
            result.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
    )
    return result


def main() -> None:
    run_cli(args=parse_args())


if __name__ == "__main__":
    main()
