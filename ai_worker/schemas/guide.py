from typing import Literal, Self

from pydantic import (
    BaseModel,
    Field,
    model_validator,
)

from ai_worker.schemas.enums import (
    CareEpisodeSourceField,
    PatientSourceKind,
    SafetyStatus,
    SourceType,
)


class GuideSource(BaseModel):
    source_type: SourceType

    patient_source_kind: (
        PatientSourceKind | None
    ) = None
    patient_field: (
        CareEpisodeSourceField | None
    ) = None
    medication_id: int | None = None
    care_advice_id: int | None = None
    follow_up_visit_id: int | None = None

    public_dataset_key: str | None = None
    dataset_version: str | None = None
    vector_chunk_id: str | None = None
    source_record_key: str | None = None
    source_field: str | None = None
    chunk_type: str | None = None

    source_title: str | None = None
    source_organization: str | None = None
    source_url: str | None = None
    source_page_number: int | None = Field(
        default=None,
        ge=1,
    )
    source_license: str | None = None
    similarity_score: float | None = None

    citation_order: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_source_fields(
        self,
    ) -> Self:
        if (
            self.source_type
            == SourceType.PATIENT_SAVED_FIELD
        ):
            self._validate_patient_source()

        if (
            self.source_type
            == SourceType.PUBLIC_RAG_CHUNK
        ):
            self._validate_public_source()

        return self

    def _validate_patient_source(self) -> None:
        if self.patient_source_kind is None:
            raise ValueError(
                "환자 출처에는 "
                "patient_source_kind가 필요합니다."
            )

        forbidden_public_fields = (
            "public_dataset_key",
            "dataset_version",
            "vector_chunk_id",
            "source_record_key",
            "source_field",
            "chunk_type",
            "source_title",
            "source_organization",
            "source_url",
            "source_page_number",
            "source_license",
            "similarity_score",
        )

        self._reject_non_null_fields(
            field_names=forbidden_public_fields,
            message_prefix="환자 출처에는",
        )

        if (
            self.patient_source_kind
            == PatientSourceKind.CARE_EPISODE_FIELD
        ):
            self._require_field("patient_field")
            self._reject_patient_ids(
                allowed_field=None
            )
            return

        if (
            self.patient_source_kind
            == PatientSourceKind.MEDICATION
        ):
            self._require_field("medication_id")
            self._reject_patient_fields(
                allowed_field="medication_id"
            )
            return

        if (
            self.patient_source_kind
            == PatientSourceKind.CARE_ADVICE
        ):
            self._require_field("care_advice_id")
            self._reject_patient_fields(
                allowed_field="care_advice_id"
            )
            return

        if (
            self.patient_source_kind
            == PatientSourceKind.FOLLOW_UP_VISIT
        ):
            self._require_field(
                "follow_up_visit_id"
            )
            self._reject_patient_fields(
                allowed_field="follow_up_visit_id"
            )

    def _validate_public_source(self) -> None:
        forbidden_patient_fields = (
            "patient_source_kind",
            "patient_field",
            "medication_id",
            "care_advice_id",
            "follow_up_visit_id",
        )

        self._reject_non_null_fields(
            field_names=forbidden_patient_fields,
            message_prefix="공공 출처에는",
        )

        required_public_fields = (
            "public_dataset_key",
            "dataset_version",
            "vector_chunk_id",
            "source_record_key",
        )

        for field_name in required_public_fields:
            self._require_field(field_name)

    def _reject_patient_ids(
        self,
        allowed_field: str | None,
    ) -> None:
        patient_id_fields = (
            "medication_id",
            "care_advice_id",
            "follow_up_visit_id",
        )

        fields_to_reject = tuple(
            field_name
            for field_name in patient_id_fields
            if field_name != allowed_field
        )

        self._reject_non_null_fields(
            field_names=fields_to_reject,
            message_prefix="해당 환자 출처에는",
        )

    def _reject_patient_fields(
        self,
        allowed_field: str,
    ) -> None:
        patient_fields = (
            "patient_field",
            "medication_id",
            "care_advice_id",
            "follow_up_visit_id",
        )

        fields_to_reject = tuple(
            field_name
            for field_name in patient_fields
            if field_name != allowed_field
        )

        self._reject_non_null_fields(
            field_names=fields_to_reject,
            message_prefix="해당 환자 출처에는",
        )

    def _require_field(
        self,
        field_name: str,
    ) -> None:
        if getattr(self, field_name) is None:
            raise ValueError(
                f"{field_name}가 필요합니다."
            )

    def _reject_non_null_fields(
        self,
        field_names: tuple[str, ...],
        message_prefix: str,
    ) -> None:
        for field_name in field_names:
            if getattr(self, field_name) is not None:
                raise ValueError(
                    f"{message_prefix} "
                    f"{field_name}를 사용할 수 없습니다."
                )


class RecoveryGuideSupplement(BaseModel):
    """LLM이 생성할 수 있는 보충정보."""

    public_information: list[str] = Field(
        default_factory=list
    )
    lifestyle_guide: list[str] = Field(
        default_factory=list
    )


class RecoveryGuideContent(BaseModel):
    medication_guide: list[str] = Field(
        default_factory=list
    )
    patient_instructions: list[str] = Field(
        default_factory=list
    )
    public_information: list[str] = Field(
        default_factory=list
    )
    lifestyle_guide_label: Literal[
        "AI 생성 일반 안내"
    ] = "AI 생성 일반 안내"
    lifestyle_guide: list[str] = Field(
        default_factory=list
    )
    warning_signs: list[str] = Field(
        default_factory=list
    )
    follow_up_schedule: list[str] = Field(
        default_factory=list
    )
    safety_notice: str


class RecoveryGuideResult(BaseModel):
    care_episode_id: int
    guide_content: RecoveryGuideContent
    sources: list[GuideSource] = Field(
        default_factory=list
    )
    safety_status: SafetyStatus
    safety_reason_codes: list[str] = Field(
        default_factory=list
    )
