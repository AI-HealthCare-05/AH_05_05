import argparse
import json
from pathlib import Path
from typing import Protocol

from ai_worker.services.medication_safety_staging_service import (
    MedicationSafetyStagingResult,
    MedicationSafetyStagingService,
    validate_medication_safety_dataset_version,
)

_SOURCE_ROOT = Path("data/knowledge/raw/public/mfds/drug_records")
_DEFAULT_INPUTS = [
    _SOURCE_ROOT / "DUR임부금기.csv",
    _SOURCE_ROOT / "DUR특정연령대금기.csv",
    _SOURCE_ROOT / "DUR노인주의.csv",
    _SOURCE_ROOT / "DUR용량주의.csv",
    _SOURCE_ROOT / "DUR투여기간주의.csv",
    _SOURCE_ROOT / "1일최대투여량.csv",
    _SOURCE_ROOT / "DUR첨가제주의.csv",
]


class MedicationSafetyStagingBuilder(Protocol):
    def build(
        self,
        *,
        input_paths: list[Path],
        output_root: Path,
        dataset_version: str,
    ) -> MedicationSafetyStagingResult: ...


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=("식약처 7종 구조화 의약품 CSV를 검수 대기 단일 약물 안전 규칙 JSONL로 변환합니다.")
    )
    parser.add_argument(
        "--input",
        type=Path,
        action="append",
        default=None,
        help="반복 지정할 수 있습니다. 생략하면 지원하는 7종 기본 CSV를 모두 사용합니다.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/knowledge/processed"),
    )
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--source-id", default="mfds_drug_records")
    args = parser.parse_args(argv)
    args.input = args.input or list(_DEFAULT_INPUTS)
    if not args.source_id.strip():
        parser.error("--source-id는 비어 있을 수 없습니다.")
    try:
        args.dataset_version = validate_medication_safety_dataset_version(args.dataset_version)
    except ValueError as error:
        parser.error(str(error))
    return args


def run_cli(
    *,
    args: argparse.Namespace,
    service: MedicationSafetyStagingBuilder | None = None,
) -> MedicationSafetyStagingResult:
    builder = service or MedicationSafetyStagingService(source_id=args.source_id)
    result = builder.build(
        input_paths=args.input,
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
