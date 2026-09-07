import pytest

from scripts.compose_knowledge_release import parse_args


def test_parse_args_accepts_multiple_release_inputs() -> None:
    args = parse_args(
        [
            "--input",
            "base/chunks",
            "base/reports/preprocessing-quality.json",
            "--input",
            "additional/chunks",
            "additional/reports/preprocessing-quality.json",
            "--output",
            "combined",
            "--dataset-version",
            "knowledge-full-v3-o200k",
        ]
    )

    assert args.input == [
        ["base/chunks", "base/reports/preprocessing-quality.json"],
        ["additional/chunks", "additional/reports/preprocessing-quality.json"],
    ]
    assert args.dataset_version == "knowledge-full-v3-o200k"


def test_parse_args_rejects_blank_dataset_version() -> None:
    with pytest.raises(SystemExit):
        parse_args(
            [
                "--input",
                "base/chunks",
                "base/reports/preprocessing-quality.json",
                "--output",
                "combined",
                "--dataset-version",
                " ",
            ]
        )
