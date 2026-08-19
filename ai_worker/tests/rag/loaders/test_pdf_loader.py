from pathlib import Path

import pytest

from ai_worker.rag.loaders import pdf_loader
from ai_worker.rag.loaders.pdf_loader import PdfLoader
from ai_worker.schemas.guideline import GuidelineMetadata


class FakePage:
    def __init__(self, text: str | None) -> None:
        self.text = text

    def extract_text(self) -> str | None:
        return self.text


class FakeReader:
    def __init__(self, _: Path) -> None:
        self.pages = [
            FakePage("First page text.\n\nMedication instructions."),
            FakePage("   "),
            FakePage("Third page text."),
        ]


def build_metadata() -> GuidelineMetadata:
    return GuidelineMetadata(
        document_id="stroke-guideline-2020",
        title="Stroke Guideline",
        condition="STROKE",
        care_phase="POST_DISCHARGE",
    )


def test_load_returns_non_empty_pages_with_page_numbers(
    tmp_path,
    monkeypatch,
) -> None:
    pdf_path = tmp_path / "guideline.pdf"
    pdf_path.write_bytes(b"%PDF-test")

    monkeypatch.setattr(
        pdf_loader,
        "PdfReader",
        FakeReader,
    )

    documents = PdfLoader().load(
        pdf_path,
        build_metadata(),
    )

    assert len(documents) == 2
    assert documents[0].metadata.page_number == 1
    assert documents[1].metadata.page_number == 3
    assert documents[0].metadata.document_id == "stroke-guideline-2020"


def test_load_rejects_non_pdf_file(tmp_path) -> None:
    text_path = tmp_path / "guideline.txt"
    text_path.write_text(
        "not a pdf",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="PDF"):
        PdfLoader().load(
            text_path,
            build_metadata(),
        )
