import json
from argparse import Namespace
from pathlib import Path

import pytest

from ai_worker.services.medication_safety_staging_service import (
    MedicationSafetyStagingResult,
)
from scripts import build_medication_safety_staging as module


class FakeMedicationSafetyStagingService:
    def __init__(self) -> None:
        self.received: dict[str, object] = {}

    def build(self, **kwargs) -> MedicationSafetyStagingResult:
        self.received = kwargs
        return MedicationSafetyStagingResult(
            generation_id="a" * 64,
            dataset_version=str(kwargs["dataset_version"]),
            input_row_count=100,
            accepted_row_count=90,
            candidate_count=88,
            duplicate_merged_count=2,
            source_type_counts={"DUR임부금기.csv": 100},
            skipped_reason_counts={"MISSING_REQUIRED_VALUE": 10},
            candidate_sha256="b" * 64,
            candidates_path=Path(
                "staging/medication-safety-v1/" + "a" * 64 + "/medication_safety_rule_candidates.jsonl"
            ),
            quality_report_path=Path(
                "staging/medication-safety-v1/" + "a" * 64 + "/medication-safety-staging-quality.json"
            ),
            current_marker_path=Path("staging/medication-safety-v1/current.json"),
        )


def test_parse_args_uses_all_seven_default_sources() -> None:
    args = module.parse_args(["--dataset-version", "medication-safety-v1"])

    assert [path.name for path in args.input] == [
        "DUR임부금기.csv",
        "DUR특정연령대금기.csv",
        "DUR노인주의.csv",
        "DUR용량주의.csv",
        "DUR투여기간주의.csv",
        "1일최대투여량.csv",
        "DUR첨가제주의.csv",
    ]
    assert args.output == Path("data/knowledge/processed")


def test_parse_args_rejects_dataset_version_path_escape() -> None:
    with pytest.raises(SystemExit):
        module.parse_args(["--dataset-version", "../../outside"])


def test_run_cli_passes_inputs_and_prints_quality_result(
    capsys,
    tmp_path: Path,
) -> None:
    args = Namespace(
        input=[tmp_path / "DUR임부금기.csv"],
        output=tmp_path / "processed",
        dataset_version="medication-safety-v1",
        source_id="mfds_drug_records",
    )
    service = FakeMedicationSafetyStagingService()

    result = module.run_cli(args=args, service=service)

    assert result.candidate_count == 88
    assert service.received == {
        "input_paths": args.input,
        "output_root": args.output,
        "dataset_version": args.dataset_version,
    }
    output = json.loads(capsys.readouterr().out)
    assert output["ready_for_rdb_import"] is False
    assert output["candidate_sha256"] == "b" * 64
