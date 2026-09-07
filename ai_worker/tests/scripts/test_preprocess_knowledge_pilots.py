from pathlib import Path

import pytest

from scripts import preprocess_knowledge_pilots as module


def test_parse_args_accepts_o200k_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "preprocess_knowledge_pilots",
            "--dataset-version",
            "additional-research-pilot-v11-o200k",
            "--tokenizer-encoding",
            "o200k_base",
            "--output",
            "data/knowledge/processed/additional_research_pilot",
        ],
    )

    args = module.parse_args()

    assert args.tokenizer_encoding == "o200k_base"
    assert args.output == Path("data/knowledge/processed/additional_research_pilot")


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
    )

    assert splitter.tokenizer_encoding == "o200k_base"
