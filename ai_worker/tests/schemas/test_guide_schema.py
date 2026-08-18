import pytest
from pydantic import ValidationError

from ai_worker.schemas.enums import (
    CareEpisodeSourceField,
    PatientSourceKind,
    SafetyStatus,
    SourceType,
)
from ai_worker.schemas.guide import (
    GuideSource,
    RecoveryGuideContent,
    RecoveryGuideResult,
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


def test_care_episode_source_uses_patient_field() -> None:
    source = GuideSource(
        source_type=(SourceType.PATIENT_SAVED_FIELD),
        patient_source_kind=(PatientSourceKind.CARE_EPISODE_FIELD),
        patient_field=(CareEpisodeSourceField.DIAGNOSIS),
        citation_order=1,
    )

    assert source.patient_field == CareEpisodeSourceField.DIAGNOSIS


@pytest.mark.parametrize(
    (
        "source_kind",
        "id_field",
        "id_value",
    ),
    [
        (
            PatientSourceKind.MEDICATION,
            "medication_id",
            101,
        ),
        (
            PatientSourceKind.CARE_ADVICE,
            "care_advice_id",
            201,
        ),
        (
            PatientSourceKind.FOLLOW_UP_VISIT,
            "follow_up_visit_id",
            301,
        ),
    ],
)
def test_patient_domain_source_uses_matching_id(
    source_kind: PatientSourceKind,
    id_field: str,
    id_value: int,
) -> None:
    source_data: dict[str, object] = {
        "source_type": (SourceType.PATIENT_SAVED_FIELD),
        "patient_source_kind": source_kind,
        "citation_order": 1,
        id_field: id_value,
    }

    source = GuideSource.model_validate(source_data)

    assert getattr(source, id_field) == id_value


def test_patient_source_requires_source_kind() -> None:
    with pytest.raises(
        ValidationError,
        match="patient_source_kind",
    ):
        GuideSource(
            source_type=(SourceType.PATIENT_SAVED_FIELD),
            citation_order=1,
        )


@pytest.mark.parametrize(
    (
        "source_kind",
        "required_field",
    ),
    [
        (
            PatientSourceKind.MEDICATION,
            "medication_id",
        ),
        (
            PatientSourceKind.CARE_ADVICE,
            "care_advice_id",
        ),
        (
            PatientSourceKind.FOLLOW_UP_VISIT,
            "follow_up_visit_id",
        ),
    ],
)
def test_patient_source_requires_matching_id(
    source_kind: PatientSourceKind,
    required_field: str,
) -> None:
    with pytest.raises(
        ValidationError,
        match=required_field,
    ):
        GuideSource(
            source_type=(SourceType.PATIENT_SAVED_FIELD),
            patient_source_kind=source_kind,
            citation_order=1,
        )


def test_patient_source_rejects_mixed_domain_ids() -> None:
    with pytest.raises(
        ValidationError,
        match="care_advice_id",
    ):
        GuideSource(
            source_type=(SourceType.PATIENT_SAVED_FIELD),
            patient_source_kind=(PatientSourceKind.MEDICATION),
            medication_id=101,
            care_advice_id=201,
            citation_order=1,
        )


def test_care_episode_source_rejects_domain_id() -> None:
    with pytest.raises(
        ValidationError,
        match="medication_id",
    ):
        GuideSource(
            source_type=(SourceType.PATIENT_SAVED_FIELD),
            patient_source_kind=(PatientSourceKind.CARE_EPISODE_FIELD),
            patient_field=(CareEpisodeSourceField.DIAGNOSIS),
            medication_id=101,
            citation_order=1,
        )


def test_patient_source_rejects_public_fields() -> None:
    with pytest.raises(
        ValidationError,
        match="public_dataset_key",
    ):
        GuideSource(
            source_type=(SourceType.PATIENT_SAVED_FIELD),
            patient_source_kind=(PatientSourceKind.MEDICATION),
            medication_id=101,
            public_dataset_key=("PUBLIC_GUIDELINE"),
            citation_order=1,
        )


@pytest.mark.parametrize(
    "missing_field",
    [
        "public_dataset_key",
        "dataset_version",
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
        "dataset_version": "2020",
        "vector_chunk_id": "chunk-1",
        "source_record_key": "document-1",
        "citation_order": 1,
    }
    source_data[missing_field] = None

    with pytest.raises(
        ValidationError,
        match=missing_field,
    ):
        GuideSource.model_validate(source_data)


def test_public_source_allows_optional_section_metadata() -> None:
    source = GuideSource(
        source_type=(SourceType.PUBLIC_RAG_CHUNK),
        public_dataset_key=("PUBLIC_GUIDELINE"),
        dataset_version="2020",
        vector_chunk_id="chunk-1",
        source_record_key="document-1",
        source_field=None,
        chunk_type=None,
        citation_order=1,
    )

    assert source.source_field is None
    assert source.chunk_type is None


def test_public_source_rejects_patient_fields() -> None:
    with pytest.raises(
        ValidationError,
        match="medication_id",
    ):
        GuideSource(
            source_type=(SourceType.PUBLIC_RAG_CHUNK),
            medication_id=101,
            public_dataset_key=("PUBLIC_GUIDELINE"),
            dataset_version="2020",
            vector_chunk_id="chunk-1",
            source_record_key="document-1",
            citation_order=1,
        )


@pytest.mark.parametrize(
    "citation_order",
    [
        0,
        -1,
    ],
)
def test_source_rejects_invalid_citation_order(
    citation_order: int,
) -> None:
    with pytest.raises(ValidationError):
        GuideSource(
            source_type=(SourceType.PATIENT_SAVED_FIELD),
            patient_source_kind=(PatientSourceKind.MEDICATION),
            medication_id=101,
            citation_order=citation_order,
        )

def test_recovery_guide_result_tracks_generation_versions() -> None:
    result = RecoveryGuideResult(
        care_episode_id=100,
        guide_content=RecoveryGuideContent(
            safety_notice=(
                "이 안내는 의료진의 진료를 "
                "대체하지 않습니다."
            ),
        ),
        safety_status=SafetyStatus.SAFE,
        patient_context_hash="a" * 64,
        model_name="gpt-4o-mini",
        model_version=None,
        prompt_version=(
            "recovery-guide-prompt-v1"
        ),
        schema_version=(
            "recovery-guide-result-v1"
        ),
    )

    assert (
        result.patient_context_hash
        == "a" * 64
    )
    assert result.model_name == "gpt-4o-mini"
    assert result.model_version is None
    assert (
        result.prompt_version
        == "recovery-guide-prompt-v1"
    )
    assert (
        result.schema_version
        == "recovery-guide-result-v1"
    )
