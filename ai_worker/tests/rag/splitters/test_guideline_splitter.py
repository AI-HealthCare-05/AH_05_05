import pytest

from ai_worker.rag.splitters.guideline_splitter import GuidelineSplitter
from ai_worker.schemas.guideline import GuidelineDocument, GuidelineMetadata


def build_document(
    content: str,
) -> GuidelineDocument:
    return GuidelineDocument(
        content=content,
        metadata=GuidelineMetadata(
            document_id="stroke-guideline-2020",
            title="Stroke Guideline",
            condition="STROKE",
            care_phase="POST_DISCHARGE",
            page_number=7,
        ),
    )


def test_split_divides_long_text_and_preserves_metadata() -> None:
    document = build_document(("Medication guidance. " * 50) + "\n\n" + ("Lifestyle guidance. " * 50))

    splitter = GuidelineSplitter(
        chunk_size=300,
        chunk_overlap=50,
    )

    chunks = splitter.split([document])

    assert len(chunks) > 1
    assert all(len(chunk.content) <= 300 for chunk in chunks)
    assert all(chunk.metadata.document_id == "stroke-guideline-2020" for chunk in chunks)
    assert all(chunk.metadata.page_number == 7 for chunk in chunks)


def test_split_rejects_overlap_equal_to_chunk_size() -> None:
    with pytest.raises(
        ValueError,
        match="chunk_overlap",
    ):
        GuidelineSplitter(
            chunk_size=100,
            chunk_overlap=100,
        )
