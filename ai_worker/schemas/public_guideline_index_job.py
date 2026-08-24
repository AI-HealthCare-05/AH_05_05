from pathlib import Path
from typing import Literal, Self

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

PUBLIC_GUIDELINE_INDEX_JOB_TYPE = "PUBLIC_GUIDELINE_INDEX"


class PublicGuidelineIndexRequest(BaseModel):
    job_id: str = Field(min_length=1)
    job_type: Literal["PUBLIC_GUIDELINE_INDEX"] = PUBLIC_GUIDELINE_INDEX_JOB_TYPE

    manifest_path: Path

    chunk_size: int = Field(
        default=1000,
        gt=0,
    )
    chunk_overlap: int = Field(
        default=200,
        ge=0,
    )

    @field_validator("job_id")
    @classmethod
    def normalize_job_id(
        cls,
        value: str,
    ) -> str:
        normalized = value.strip()

        if not normalized:
            raise ValueError("작업 ID는 비어 있을 수 없습니다.")

        return normalized

    @field_validator("manifest_path")
    @classmethod
    def validate_manifest_path(
        cls,
        value: Path,
    ) -> Path:
        if value.suffix.lower() != ".json":
            raise ValueError("manifest는 JSON 파일이어야 합니다.")

        return value

    @model_validator(mode="after")
    def validate_chunk_settings(
        self,
    ) -> Self:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap은 chunk_size보다 작아야 합니다.")

        return self


class PublicGuidelineIndexResult(BaseModel):
    job_id: str
    indexed_document_count: int = Field(ge=0)
    indexed_chunk_count: int = Field(ge=0)
    point_ids_by_document: dict[
        str,
        list[str],
    ] = Field(default_factory=dict)
