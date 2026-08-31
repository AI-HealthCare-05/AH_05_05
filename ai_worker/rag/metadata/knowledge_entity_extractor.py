import re

from pydantic import BaseModel, Field

from ai_worker.rag.metadata.supplement_interaction_registry import (
    find_supplement_interaction_pair,
)
from ai_worker.schemas.knowledge import KnowledgeDocumentType


class ExtractedKnowledgeEntities(BaseModel):
    drug_names: list[str] = Field(default_factory=list)
    ingredient_names: list[str] = Field(default_factory=list)
    interaction_type: str | None = None
    interaction_pair_keys: list[str] = Field(default_factory=list)


class KnowledgeEntityExtractor:
    _BILINGUAL_DRUG_NAME = re.compile(
        r"^\s*([^()]*[가-힣][^()]*)\s*\(\s*([A-Za-z][A-Za-z0-9 .,+/-]*)\s*\)\s*$",
    )
    _TRAILING_VERSION = re.compile(
        r"(?:[_\s]*20\d{6}|\s*\(\s*\d+\s*페이지\s*\)|"
        r"\s*\(\s*20\d{2}[^)]*시행[^)]*\))+$",
        flags=re.IGNORECASE,
    )
    _LEADING_NUMBER = re.compile(r"^\d+(?:-\d+)?[_\s-]*")

    def extract_from_title(
        self,
        *,
        document_type: KnowledgeDocumentType,
        title: str,
    ) -> ExtractedKnowledgeEntities:
        normalized = self._normalize_title(title)
        if not normalized:
            return ExtractedKnowledgeEntities()

        if document_type == KnowledgeDocumentType.SUPPLEMENT_CODE:
            return ExtractedKnowledgeEntities(
                ingredient_names=[normalized],
            )
        if document_type == KnowledgeDocumentType.ADVERSE_CASE_REPORT:
            return ExtractedKnowledgeEntities(
                drug_names=[normalized.split(maxsplit=1)[0]],
            )
        if document_type == KnowledgeDocumentType.DRUG_ENCYCLOPEDIA:
            bilingual_name = self._BILINGUAL_DRUG_NAME.fullmatch(normalized)
            if bilingual_name is not None:
                return ExtractedKnowledgeEntities(
                    drug_names=[
                        normalized,
                        bilingual_name.group(1).strip(),
                        bilingual_name.group(2).strip(),
                    ],
                )
            return ExtractedKnowledgeEntities(
                drug_names=[normalized],
            )
        if document_type == KnowledgeDocumentType.RESEARCH_ARTICLE:
            pair = find_supplement_interaction_pair(normalized)
            if pair is not None:
                return ExtractedKnowledgeEntities(
                    ingredient_names=list(pair.canonical_names),
                    interaction_type="SUPPLEMENT_SUPPLEMENT",
                    interaction_pair_keys=[pair.pair_key],
                )
        return ExtractedKnowledgeEntities()

    @classmethod
    def _normalize_title(cls, title: str) -> str:
        normalized = title.replace("_", " ").strip()
        normalized = cls._LEADING_NUMBER.sub("", normalized)
        previous = None
        while previous != normalized:
            previous = normalized
            normalized = cls._TRAILING_VERSION.sub("", normalized).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        return normalized.strip(" _-")
