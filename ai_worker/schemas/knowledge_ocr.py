import re
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class KnowledgeOcrBoundingBox(BaseModel):
    x0: float = Field(ge=0)
    top: float = Field(ge=0)
    x1: float = Field(ge=0)
    bottom: float = Field(ge=0)

    @model_validator(mode="after")
    def require_non_empty_area(self):
        if self.x1 <= self.x0 or self.bottom <= self.top:
            raise ValueError("OCR bounding box는 양의 너비와 높이가 필요합니다.")
        return self


class KnowledgeOcrBlock(BaseModel):
    block_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: KnowledgeOcrBoundingBox
    line_break: bool = False

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("OCR block text는 비어 있을 수 없습니다.")
        return normalized


class KnowledgeOcrRendererMetadata(BaseModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    dpi: int = Field(ge=72, le=600)


class KnowledgeOcrEngineMetadata(BaseModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)


class KnowledgeOcrPageArtifact(BaseModel):
    page_number: int = Field(ge=1)
    image_sha256: str
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    rotation_degrees: int = Field(default=0)
    blocks: list[KnowledgeOcrBlock] = Field(min_length=1)

    @field_validator("image_sha256")
    @classmethod
    def validate_image_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("image_sha256은 64자리 SHA-256이어야 합니다.")
        return normalized

    @field_validator("rotation_degrees")
    @classmethod
    def require_right_angle_rotation(cls, value: int) -> int:
        if value not in {0, 90, 180, 270}:
            raise ValueError("rotation_degrees는 0, 90, 180, 270 중 하나여야 합니다.")
        return value

    @model_validator(mode="after")
    def require_unique_block_ids(self):
        block_ids = [block.block_id for block in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("OCR page의 block_id는 중복될 수 없습니다.")
        if any(block.bbox.x1 > self.width or block.bbox.bottom > self.height for block in self.blocks):
            raise ValueError("OCR block 좌표가 페이지 경계를 벗어났습니다.")
        return self


class KnowledgeOcrDocumentArtifact(BaseModel):
    schema_version: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    source_sha256: str
    renderer: KnowledgeOcrRendererMetadata
    ocr_engine: KnowledgeOcrEngineMetadata
    pages: list[KnowledgeOcrPageArtifact] = Field(min_length=1)

    @field_validator("source_sha256")
    @classmethod
    def validate_source_sha256(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not _SHA256_PATTERN.fullmatch(normalized):
            raise ValueError("source_sha256은 64자리 SHA-256이어야 합니다.")
        return normalized

    @model_validator(mode="after")
    def require_contiguous_page_numbers(self):
        actual_numbers = [page.page_number for page in self.pages]
        expected_numbers = list(range(1, len(actual_numbers) + 1))
        if actual_numbers != expected_numbers:
            raise ValueError("OCR artifact 페이지는 1부터 연속된 순서여야 합니다.")
        return self


def knowledge_ocr_artifact_path(*, artifact_root: Path, document_id: str) -> Path:
    return Path(artifact_root) / f"{document_id}.json"
