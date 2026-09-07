from pathlib import Path

import pytest

from scripts import preprocess_knowledge_corpus as module


def test_parse_args_defaults_to_cl100k_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "preprocess_knowledge_corpus",
            "--dataset-version",
            "knowledge-full-v2",
        ],
    )

    args = module.parse_args()

    assert args.tokenizer_encoding == "cl100k_base"


def test_parse_args_accepts_o200k_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "preprocess_knowledge_corpus",
            "--dataset-version",
            "knowledge-full-v2-o200k",
            "--tokenizer-encoding",
            "o200k_base",
            "--output",
            "data/knowledge/processed/full-v2-o200k",
        ],
    )

    args = module.parse_args()

    assert args.tokenizer_encoding == "o200k_base"
    assert args.output == Path("data/knowledge/processed/full-v2-o200k")


def test_parse_args_accepts_multiple_representative_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "preprocess_knowledge_corpus",
            "--dataset-version",
            "knowledge-full-v4",
            "--pilot-quality-report",
            "base-quality.json",
            "--pilot-quality-report",
            "additional-quality.json",
            "--pilot-manifest",
            "base-manifest.json",
            "--pilot-manifest",
            "additional-manifest.json",
            "--baseline-quality-report",
            "baseline.json",
        ],
    )

    args = module.parse_args()

    assert args.pilot_quality_report == [
        Path("base-quality.json"),
        Path("additional-quality.json"),
    ]
    assert args.pilot_manifest == [
        Path("base-manifest.json"),
        Path("additional-manifest.json"),
    ]
    assert args.baseline_quality_report == Path("baseline.json")


def test_build_splitter_records_requested_tokenizer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeTokenCounter:
        def __init__(self, encoding_name: str) -> None:
            self.encoding_name = encoding_name

        def count(self, text: str) -> int:
            return len(text)

    monkeypatch.setattr(
        "ai_worker.rag.splitters.knowledge_splitter.TiktokenTokenCounter",
        FakeTokenCounter,
    )

    splitter = module.build_splitter(
        tokenizer_encoding="o200k_base",
        interaction_annotations=None,
    )

    assert splitter.tokenizer_encoding == "o200k_base"
