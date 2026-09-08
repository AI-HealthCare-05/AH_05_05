import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator, model_validator

from ai_worker.schemas.interaction import InteractionEntityKind


class KnowledgeAccessScope(StrEnum):
    PUBLIC = "PUBLIC"
    DEMO_RESTRICTED = "DEMO_RESTRICTED"


class KnowledgeDocumentType(StrEnum):
    REGULATORY_DRUG_LABEL = "REGULATORY_DRUG_LABEL"
    DRUG_FOOD_INTERACTION_GUIDE = "DRUG_FOOD_INTERACTION_GUIDE"
    SUPPLEMENT_FUNCTION_GUIDE = "SUPPLEMENT_FUNCTION_GUIDE"
    SUPPLEMENT_CODE = "SUPPLEMENT_CODE"
    DRUG_ENCYCLOPEDIA = "DRUG_ENCYCLOPEDIA"
    ADVERSE_CASE_REPORT = "ADVERSE_CASE_REPORT"
    PHARM_REVIEW = "PHARM_REVIEW"
    RESEARCH_ARTICLE = "RESEARCH_ARTICLE"
    SUPPLEMENT_INTERACTION_MONOGRAPH = "SUPPLEMENT_INTERACTION_MONOGRAPH"


class KnowledgeExtractionWarning(StrEnum):
    MULTI_COLUMN_LAYOUT = "MULTI_COLUMN_LAYOUT"
    ROTATED_TEXT = "ROTATED_TEXT"
    TABLE_STRUCTURE_UNSAFE = "TABLE_STRUCTURE_UNSAFE"
    READING_ORDER_UNSAFE = "READING_ORDER_UNSAFE"


class KnowledgeContentKind(StrEnum):
    TEXT = "TEXT"
    TABLE = "TABLE"


class KnowledgeSectionType(StrEnum):
    OVERVIEW = "OVERVIEW"
    SUMMARY = "SUMMARY"
    INGREDIENT = "INGREDIENT"
    STANDARD = "STANDARD"
    FUNCTION = "FUNCTION"
    DAILY_INTAKE = "DAILY_INTAKE"
    CAUTION = "CAUTION"
    INTERACTION = "INTERACTION"
    ADVERSE_EVENT = "ADVERSE_EVENT"
    CASE_SUMMARY = "CASE_SUMMARY"
    ASSESSMENT = "ASSESSMENT"
    INTRODUCTION = "INTRODUCTION"
    METHODS = "METHODS"
    RESULTS = "RESULTS"
    DISCUSSION = "DISCUSSION"
    CONCLUSION = "CONCLUSION"
    REFERENCES = "REFERENCES"
    TEST_METHOD = "TEST_METHOD"
    OTHER = "OTHER"


class KnowledgeSearchMode(StrEnum):
    DENSE = "DENSE"
    BM25 = "BM25"
    HYBRID = "HYBRID"


class KnowledgeVectorDistance(StrEnum):
    COSINE = "COSINE"
    DOT = "DOT"


class KnowledgeSearchTier(StrEnum):
    EXACT_PAIR = "EXACT_PAIR"
    ENTITY = "ENTITY"
    SEMANTIC = "SEMANTIC"


class KnowledgeCandidateRejectionReason(StrEnum):
    BELOW_SCORE = "BELOW_SCORE"
    ENTITY_MISMATCH = "ENTITY_MISMATCH"
    PAIR_MISMATCH = "PAIR_MISMATCH"


class KnowledgeEvidenceLevel(StrEnum):
    REGULATORY = "REGULATORY"
    SYSTEMATIC_REVIEW = "SYSTEMATIC_REVIEW"
    REVIEW_ARTICLE = "REVIEW_ARTICLE"
    CLINICAL_STUDY = "CLINICAL_STUDY"
    OBSERVATIONAL_STUDY = "OBSERVATIONAL_STUDY"
    CASE_REPORT = "CASE_REPORT"
    PRECLINICAL = "PRECLINICAL"
    UNKNOWN = "UNKNOWN"


class KnowledgeStudyPopulation(StrEnum):
    HUMAN = "HUMAN"
    ANIMAL = "ANIMAL"
    CELL = "CELL"
    MIXED = "MIXED"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNKNOWN = "UNKNOWN"


class KnowledgeEntityCatalogEntryType(StrEnum):
    """Qdrant payload에서 Resolver로 전달할 엔터티 표현 유형."""

    PRODUCT_NAME = "PRODUCT_NAME"
    BRAND_ALIAS = "BRAND_ALIAS"
    INGREDIENT_NAME = "INGREDIENT_NAME"
    INGREDIENT_FAMILY = "INGREDIENT_FAMILY"
    FOOD_CATEGORY = "FOOD_CATEGORY"


class KnowledgeEntityCatalogEntry(BaseModel):
    """문서에서 검수된 정식명과 별칭을 함께 보존하는 payload 항목."""

    canonical_name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    entity_type: KnowledgeEntityCatalogEntryType
    kind: InteractionEntityKind

    @field_validator("canonical_name")
    @classmethod
    def normalize_canonical_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("엔터티 정식명은 비어 있을 수 없습니다.")
        return normalized

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class KnowledgeMetadata(BaseModel):
    source_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    access_scope: KnowledgeAccessScope
    document_type: KnowledgeDocumentType
    dataset_version: str = Field(min_length=1)
    source_url: str | None = None
    doi: str | None = None
    authors: list[str] = Field(default_factory=list)
    publication_year: int | None = Field(default=None, ge=1900, le=2100)
    file_name: str | None = None
    entity_type: str | None = None
    drug_names: list[str] = Field(default_factory=list)
    ingredient_names: list[str] = Field(default_factory=list)
    food_names: list[str] = Field(default_factory=list)
    entity_catalog_entries: list[KnowledgeEntityCatalogEntry] = Field(
        default_factory=list,
    )
    interaction_type: str | None = None
    interaction_pair_keys: list[str] = Field(default_factory=list)
    evidence_level: KnowledgeEvidenceLevel = KnowledgeEvidenceLevel.UNKNOWN
    study_population: KnowledgeStudyPopulation = KnowledgeStudyPopulation.UNKNOWN
    special_populations: list[str] = Field(default_factory=list)
    index_eligible: bool = True

    @field_validator(
        "drug_names",
        "ingredient_names",
        "food_names",
        "authors",
        "special_populations",
    )
    @classmethod
    def normalize_unique_values(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for value in values:
            item = value.strip()
            if not item or item in seen:
                continue
            normalized.append(item)
            seen.add(item)

        return normalized

    @field_validator("entity_catalog_entries")
    @classmethod
    def normalize_entity_catalog_entries(
        cls,
        values: list[KnowledgeEntityCatalogEntry],
    ) -> list[KnowledgeEntityCatalogEntry]:
        unique: list[KnowledgeEntityCatalogEntry] = []
        seen: set[tuple[str, KnowledgeEntityCatalogEntryType, InteractionEntityKind]] = set()
        for value in values:
            key = (value.canonical_name, value.entity_type, value.kind)
            if key not in seen:
                unique.append(value)
                seen.add(key)
        return unique

    @field_validator("interaction_pair_keys")
    @classmethod
    def normalize_interaction_pair_keys(
        cls,
        values: list[str],
    ) -> list[str]:
        return normalize_interaction_pair_keys(values)


class KnowledgeBoundingBox(BaseModel):
    x0: float
    top: float
    x1: float
    bottom: float

    @model_validator(mode="after")
    def require_ordered_coordinates(self):
        if self.x1 < self.x0:
            raise ValueError("x1은 x0보다 작을 수 없습니다.")
        if self.bottom < self.top:
            raise ValueError("bottom은 top보다 작을 수 없습니다.")
        return self


class KnowledgeTableRow(BaseModel):
    cells: list[str] = Field(min_length=1)

    @field_validator("cells")
    @classmethod
    def normalize_cells(cls, cells: list[str]) -> list[str]:
        return [cell.strip() for cell in cells]


class KnowledgePageBlock(BaseModel):
    kind: KnowledgeContentKind
    order: int = Field(ge=0)
    bbox: KnowledgeBoundingBox
    content: str = Field(min_length=1)
    headers: list[str] = Field(default_factory=list)
    rows: list[KnowledgeTableRow] = Field(default_factory=list)
    column_count: int | None = Field(default=None, ge=1)
    table_title: str | None = None
    table_super_headers: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)

    @field_validator("table_title")
    @classmethod
    def normalize_table_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("table_super_headers")
    @classmethod
    def normalize_table_super_headers(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))

    @model_validator(mode="after")
    def require_table_shape(self):
        if self.kind == KnowledgeContentKind.TEXT:
            if (
                self.headers
                or self.rows
                or self.column_count is not None
                or self.table_title is not None
                or self.table_super_headers
            ):
                raise ValueError("TEXT 블록에는 표 구조를 지정할 수 없습니다.")
            return self
        if self.column_count is None:
            raise ValueError("TABLE 블록에는 column_count가 필요합니다.")
        return self


class KnowledgePage(BaseModel):
    content: str = Field(min_length=1)
    metadata: KnowledgeMetadata
    page_number: int = Field(ge=1)
    blocks: list[KnowledgePageBlock] = Field(default_factory=list)
    extraction_warnings: list[KnowledgeExtractionWarning] = Field(
        default_factory=list,
    )


class KnowledgeSection(BaseModel):
    content: str = Field(min_length=1)
    section_type: KnowledgeSectionType
    section_title: str | None = None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    source_start: int = Field(ge=0)
    source_end: int = Field(ge=0)

    @model_validator(mode="after")
    def require_valid_ranges(self):
        if self.page_end < self.page_start:
            raise ValueError("page_end는 page_start보다 작을 수 없습니다.")
        if self.source_end < self.source_start:
            raise ValueError("source_end는 source_start보다 작을 수 없습니다.")
        return self


class KnowledgeChunkMetadata(KnowledgeMetadata):
    content_kind: KnowledgeContentKind = KnowledgeContentKind.TEXT
    section_type: KnowledgeSectionType
    section_title: str | None = None
    table_title: str | None = None
    table_super_headers: list[str] = Field(default_factory=list)
    table_group_id: str | None = None
    table_sequence: int | None = Field(default=None, ge=0)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    chunk_index: int = Field(ge=0)
    content_hash: str = Field(min_length=64, max_length=64)


class KnowledgeChunk(BaseModel):
    chunk_id: str = Field(min_length=64, max_length=64)
    content: str = Field(min_length=1)
    embedding_text: str = Field(min_length=1)
    token_count: int = Field(ge=1)
    metadata: KnowledgeChunkMetadata


class KnowledgeSearchQuery(BaseModel):
    query: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    document_types: list[KnowledgeDocumentType] = Field(default_factory=list)
    drug_names: list[str] = Field(default_factory=list)
    ingredient_names: list[str] = Field(default_factory=list)
    interaction_type: str | None = None
    interaction_pair_keys: list[str] = Field(default_factory=list)
    special_populations: list[str] = Field(default_factory=list)
    section_types: list[KnowledgeSectionType] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=50)

    @field_validator(
        "query",
        "dataset_version",
    )
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("검색어와 dataset_version은 비어 있을 수 없습니다.")
        return normalized

    @field_validator(
        "drug_names",
        "ingredient_names",
        "special_populations",
    )
    @classmethod
    def normalize_filter_values(cls, values: list[str]) -> list[str]:
        return KnowledgeMetadata.normalize_unique_values(values)

    @field_validator("interaction_pair_keys")
    @classmethod
    def normalize_interaction_pair_key_filters(
        cls,
        values: list[str],
    ) -> list[str]:
        return normalize_interaction_pair_keys(values)

    @field_validator("interaction_type")
    @classmethod
    def normalize_optional_filter(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class RetrievedKnowledgeChunk(KnowledgeChunk):
    point_id: str = Field(min_length=1)
    similarity_score: float = Field(ge=-1.0, le=1.0)
    search_mode: KnowledgeSearchMode = KnowledgeSearchMode.DENSE
    dense_similarity_score: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
    )


class KnowledgeCandidateDiagnostic(BaseModel):
    """평가·추적에서만 사용하는 검색 후보의 순위 결정 근거."""

    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=64, max_length=64)
    search_tier: KnowledgeSearchTier
    raw_rank: int = Field(ge=1)
    raw_similarity_score: float = Field(ge=-1.0, le=1.0)
    dense_similarity_score: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
    )
    boost_score: float
    adjusted_score: float
    adjusted_rank: int = Field(ge=1)
    entity_matched: bool
    section_matched: bool
    pair_matched: bool | None = None
    eligible: bool
    rejection_reason: KnowledgeCandidateRejectionReason | None = None
    selected_in_top_5: bool = False


class KnowledgeRetrievalDiagnostics(BaseModel):
    raw_candidate_count: int = Field(ge=0)
    entity_filtered_count: int = Field(ge=0)
    broad_candidate_count: int = Field(ge=0)
    fallback_used: bool = False
    eligible_candidate_count: int = Field(ge=0)
    rejected_below_score_count: int = Field(ge=0)
    rejected_entity_mismatch_count: int = Field(ge=0)
    rejected_pair_mismatch_count: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    max_raw_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    max_score: float | None = Field(default=None, ge=-1.0, le=1.0)
    attempted_search_tiers: list[KnowledgeSearchTier] = Field(
        default_factory=list,
    )
    selected_search_tier: KnowledgeSearchTier | None = None
    candidate_diagnostics: list[KnowledgeCandidateDiagnostic] = Field(
        default_factory=list,
        max_length=20,
    )


class KnowledgeRetrievalResult(BaseModel):
    chunks: list[RetrievedKnowledgeChunk] = Field(default_factory=list)
    diagnostics: KnowledgeRetrievalDiagnostics


def normalize_interaction_pair_keys(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = value.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", item):
            raise ValueError("interaction pair key는 SHA-256 형식이어야 합니다.")
        if item not in seen:
            normalized.append(item)
            seen.add(item)
    return normalized
