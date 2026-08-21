from pathlib import Path
from typing import Self

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)


class GuidelineManifestDocument(BaseModel):
    file_path: Path
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    organization: str | None = None
    dataset_version: str | None = None
    publication_year: int | None = None
    language: str = "en"
    condition: str = Field(min_length=1)
    care_phase: str | None = None
    topic: str | None = None
    source_url: str | None = None
    license: str | None = None

    @field_validator("file_path")
    @classmethod
    def validate_pdf_file_path(
        cls,
        value: Path,
    ) -> Path:
        if value.suffix.lower() != ".pdf":
            raise ValueError("PDF 파일만 manifest에 등록할 수 있습니다.")

        return value


class GuidelineManifest(BaseModel):
    documents: list[GuidelineManifestDocument] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_document_ids(
        self,
    ) -> Self:
        seen_document_ids: set[str] = set()
        duplicate_document_ids: set[str] = set()

        for document in self.documents:
            if document.document_id in seen_document_ids:
                duplicate_document_ids.add(document.document_id)

            seen_document_ids.add(document.document_id)

        if duplicate_document_ids:
            duplicate_values = ", ".join(sorted(duplicate_document_ids))
            raise ValueError(f"중복된 document_id가 있습니다: {duplicate_values}")

        return self
