import pytest
from pydantic import ValidationError

from ai_worker.schemas.enums import SourceType
from ai_worker.schemas.guide import (
    GuideSource,
    RecoveryGuideContent,
)


def test_recovery_guide_content_labels_ai_generated_lifestyle() -> None:
    content = RecoveryGuideContent(
        lifestyle_guide=["충분히 쉬고 무리하지 마세요."],
        safety_notice=("이 안내는 의료진의 진료를 대체하지 않습니다."),
    )

    assert content.lifestyle_guide_label == "AI 생성 일반 안내"


def test_recovery_guide_content_rejects_invalid_lifestyle_label() -> None:
    with pytest.raises(ValidationError):
        RecoveryGuideContent(
            lifestyle_guide_label=("공공자료 기반 안내"),
            lifestyle_guide=["충분히 쉬세요."],
            safety_notice=("이 안내는 의료진의 진료를 대체하지 않습니다."),
        )


def test_patient_source_requires_extracted_field_id() -> None:
    with pytest.raises(
        ValidationError,
        match="extracted_field_id",
    ):
        GuideSource(
            source_type=(SourceType.PATIENT_SAVED_FIELD),
        )


@pytest.mark.parametrize(
    "missing_field",
    [
        "public_dataset_key",
        "vector_chunk_id",
        "source_record_key",
    ],
)
def test_public_source_requires_identifiers(
    missing_field: str,
) -> None:
    source_data: dict[str, object] = {
        "source_type": (SourceType.PUBLIC_RAG_CHUNK),
        "public_dataset_key": ("PUBLIC_GUIDELINE"),
        "vector_chunk_id": "chunk-1",
        "source_record_key": "document-1",
    }
    source_data[missing_field] = None

    with pytest.raises(
        ValidationError,
        match=missing_field,
    ):
        GuideSource.model_validate(source_data)


@pytest.mark.parametrize(
    (
        "public_field",
        "public_value",
    ),
    [
        (
            "public_dataset_key",
            "PUBLIC_GUIDELINE",
        ),
        (
            "dataset_version",
            "2020",
        ),
        (
            "vector_chunk_id",
            "chunk-1",
        ),
        (
            "source_record_key",
            "document-1",
        ),
        (
            "source_field",
            "Activity",
        ),
        (
            "chunk_type",
            "LIFESTYLE",
        ),
        (
            "source_title",
            "Stroke Guideline",
        ),
        (
            "source_organization",
            "Test Organization",
        ),
        (
            "source_url",
            "https://example.com/guide",
        ),
        (
            "source_page_number",
            10,
        ),
        (
            "source_license",
            "CC BY-NC-ND 4.0",
        ),
        (
            "similarity_score",
            0.91,
        ),
    ],
)
def test_patient_source_rejects_public_fields(
    public_field: str,
    public_value: object,
) -> None:
    source_data: dict[str, object] = {
        "source_type": (SourceType.PATIENT_SAVED_FIELD),
        "extracted_field_id": 101,
        public_field: public_value,
    }

    with pytest.raises(
        ValidationError,
        match=public_field,
    ):
        GuideSource.model_validate(source_data)


def test_public_source_rejects_extracted_field_id() -> None:
    with pytest.raises(
        ValidationError,
        match="extracted_field_id",
    ):
        GuideSource(
            source_type=(SourceType.PUBLIC_RAG_CHUNK),
            extracted_field_id=101,
            public_dataset_key=("PUBLIC_GUIDELINE"),
            vector_chunk_id="chunk-1",
            source_record_key="document-1",
        )
