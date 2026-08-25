import json
from argparse import Namespace
from pathlib import Path

from ai_worker.services.interaction_staging_service import (
    InteractionStagingResult,
)
from scripts import build_interaction_staging as module


class FakeStagingService:
    def __init__(self) -> None:
        self.received: dict[str, object] = {}

    def build(self, **kwargs) -> InteractionStagingResult:
        self.received = kwargs
        return InteractionStagingResult(
            dataset_version=str(kwargs["dataset_version"]),
            input_row_count=10,
            accepted_row_count=8,
            candidate_count=7,
            duplicate_merged_count=1,
            skipped_reason_counts={"INACTIVE_STATUS": 2},
        )


def test_parse_args_uses_safe_defaults() -> None:
    args = module.parse_args(
        ["--dataset-version", "interaction-pilot-v1"]
    )

    assert args.input == Path(
        "data/knowledge/raw/public/mfds/drug_records/DUR병용금기.csv"
    )
    assert args.output == Path("data/knowledge/processed")
    assert args.source_id == "mfds_drug_records"
    assert args.document_id == "mfds-dur-contraindication"


def test_run_cli_builds_staging_and_prints_result(
    capsys,
    tmp_path: Path,
) -> None:
    args = Namespace(
        input=tmp_path / "DUR병용금기.csv",
        output=tmp_path / "processed",
        dataset_version="interaction-pilot-v1",
        source_id="mfds_drug_records",
        document_id="mfds-dur-contraindication",
    )
    service = FakeStagingService()

    result = module.run_cli(args=args, service=service)

    assert result.candidate_count == 7
    assert service.received == {
        "input_path": args.input,
        "output_root": args.output,
        "dataset_version": "interaction-pilot-v1",
    }
    output = json.loads(capsys.readouterr().out)
    assert output["ready_for_rdb_import"] is False

