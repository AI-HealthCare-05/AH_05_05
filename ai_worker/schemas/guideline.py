from pydantic import BaseModel, Field


class GuidelineMetadata(BaseModel):
    dataset_key: str = "PUBLIC_GUIDELINE"
    dataset_version: str | None = None
    document_id: str

    title: str
    organization: str | None = None
    publication_year: int | None = None
    country: str | None = None
    language: str = "en"
    document_type: str | None = None

    condition: str
    care_phase: str | None = None
    topic: str | None = None
    section_title: str | None = None
    page_number: int | None = Field(default=None, ge=1)

    source_url: str | None = None
    license: str | None = None


class GuidelineDocument(BaseModel):
    content: str = Field(min_length=1)
    metadata: GuidelineMetadata


class RetrievedGuidelineChunk(BaseModel):
    vector_chunk_id: str
    content: str = Field(min_length=1)
    similarity_score: float | None = None
    metadata: GuidelineMetadata


class GuidelineSearchQuery(BaseModel):
    query: str = Field(min_length=1)
    condition: str = Field(min_length=1)
    care_phase: str | None = None
    topic: str | None = None
    limit: int = Field(default=5, ge=1, le=20)
