import re
from collections.abc import Iterable

from pydantic import BaseModel, Field

from ai_worker.rag.metadata.entity_name_policy import (
    is_generic_knowledge_entity_category,
)
from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    KnowledgeEntityCatalogEntry,
    KnowledgeEvidenceLevel,
    KnowledgeSectionType,
    KnowledgeStudyPopulation,
)


class ExtractedKnowledgeEntities(BaseModel):
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
    _HUMAN_STUDY = re.compile(
        r"\b(?:patient|patients|participant|participants|subject|subjects|"
        r"women|woman|men|man|adult|adults|children|postmenopausal|human)\b",
        flags=re.IGNORECASE,
    )
    _ANIMAL_STUDY = re.compile(
        r"\b(?:rat|rats|mouse|mice|rabbit|rabbits|animal|animals|murine)\b",
        flags=re.IGNORECASE,
    )
    _CELL_STUDY = re.compile(
        r"\b(?:cell culture|cell line|cell lines|in vitro|caco-?2 cells?)\b",
        flags=re.IGNORECASE,
    )
    _SYSTEMATIC_REVIEW = re.compile(
        r"\b(?:systematic review|meta-analysis|meta analysis)\b",
        flags=re.IGNORECASE,
    )
    _OBSERVATIONAL_STUDY = re.compile(
        r"\b(?:cohort|case-control|cross-sectional|observational)\b",
        flags=re.IGNORECASE,
    )
    _CLINICAL_STUDY = re.compile(
        r"\b(?:randomi[sz]ed|clinical trial|crossover|cross-over|"
        r"single-meal|double-blind|placebo)\b",
        flags=re.IGNORECASE,
    )
    _REGULATORY_LABEL_DRUG = re.compile(
        r"\b(?P<brand>[A-Z][A-Z0-9-]{2,})®?\s*"
        r"\(\s*(?P<generic>[a-z][a-z0-9 -]{2,})\s*\)",
    )
    _RESEARCH_TABLE_ROW = re.compile(
        r"(?im)^(?:Ingredient|Interfering Substances|열\s*1)="
        r"(?P<entities>[^|\n]+)\s*\|\s*"
        r"(?:Class|Result|열\s*2)=(?P<entity_class>[^|\n]+)"
    )
    _SUPPLEMENT_CLASS = re.compile(
        r"\b(?:supplement|vitamin|nutrient|mineral)\b",
        flags=re.IGNORECASE,
    )

    _REGULATORY_DOCUMENT_TYPES = {
        KnowledgeDocumentType.REGULATORY_DRUG_LABEL,
        KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE,
        KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
        KnowledgeDocumentType.SUPPLEMENT_CODE,
    }

    def __init__(
        self,
        interaction_annotations: KnowledgeInteractionAnnotationRegistry | None = None,
    ) -> None:
        self._interaction_annotations = interaction_annotations

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
            if is_generic_knowledge_entity_category(normalized):
                return ExtractedKnowledgeEntities()
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
        return ExtractedKnowledgeEntities()

    def extract_from_chunk(
        self,
        *,
        document_type: KnowledgeDocumentType,
        title: str,
        content: str,
        document_id: str = "",
        section_type: KnowledgeSectionType = KnowledgeSectionType.OTHER,
    ) -> ExtractedKnowledgeEntities:
        title_entities = self.extract_from_title(
            document_type=document_type,
            title=title,
        )
        evidence_level, study_population = self._classify_evidence(
            document_type=document_type,
            title=title,
            content=content,
            section_type=section_type,
        )
        annotated = (
            self._interaction_annotations.find_matches(
                document_id=document_id,
                text=f"{title}\n{content}",
            )
            if self._interaction_annotations is not None and document_id
            else []
        )
        regulatory_drug_names = self._regulatory_drug_names(
            document_type=document_type,
            content=content,
        )
        table_ingredient_names = self._research_table_ingredient_names(
            document_type=document_type,
            content=content,
        )
        if annotated:
            pair_types = {match.pair_type.value for match in annotated}
            interaction_type = next(iter(pair_types)) if len(pair_types) == 1 else None
            return title_entities.model_copy(
                update={
                    "drug_names": self._unique(name for match in annotated for name in match.drug_names),
                    "ingredient_names": self._unique(
                        [
                            *(name for match in annotated for name in match.ingredient_names),
                            *table_ingredient_names,
                        ]
                    ),
                    "food_names": self._unique(name for match in annotated for name in match.food_names),
                    "entity_catalog_entries": self._unique_catalog_entries(
                        entry for match in annotated for entry in match.entity_catalog_entries
                    ),
                    "interaction_type": interaction_type,
                    "interaction_pair_keys": self._unique(
                        key for match in annotated for key in match.interaction_pair_keys
                    ),
                    "evidence_level": evidence_level,
                    "study_population": study_population,
                }
            )
        return title_entities.model_copy(
            update={
                "drug_names": self._unique(
                    [*title_entities.drug_names, *regulatory_drug_names],
                ),
                "ingredient_names": self._unique(
                    [
                        *title_entities.ingredient_names,
                        *table_ingredient_names,
                    ],
                ),
                "evidence_level": evidence_level,
                "study_population": study_population,
            }
        )

    @classmethod
    def _research_table_ingredient_names(
        cls,
        *,
        document_type: KnowledgeDocumentType,
        content: str,
    ) -> list[str]:
        if document_type != KnowledgeDocumentType.RESEARCH_ARTICLE:
            return []
        return cls._unique(
            entity.strip()
            for match in cls._RESEARCH_TABLE_ROW.finditer(content)
            if cls._SUPPLEMENT_CLASS.search(match.group("entity_class"))
            for entity in match.group("entities").split(";")
        )

    @classmethod
    def _regulatory_drug_names(
        cls,
        *,
        document_type: KnowledgeDocumentType,
        content: str,
    ) -> list[str]:
        if document_type != KnowledgeDocumentType.REGULATORY_DRUG_LABEL:
            return []
        return cls._unique(
            name.strip()
            for match in cls._REGULATORY_LABEL_DRUG.finditer(content)
            for name in (match.group("brand"), match.group("generic"))
        )

    @classmethod
    def _classify_evidence(
        cls,
        *,
        document_type: KnowledgeDocumentType,
        title: str,
        content: str,
        section_type: KnowledgeSectionType,
    ) -> tuple[KnowledgeEvidenceLevel, KnowledgeStudyPopulation]:
        if section_type == KnowledgeSectionType.REFERENCES:
            return (
                KnowledgeEvidenceLevel.UNKNOWN,
                KnowledgeStudyPopulation.UNKNOWN,
            )
        if document_type in cls._REGULATORY_DOCUMENT_TYPES:
            return (
                KnowledgeEvidenceLevel.REGULATORY,
                KnowledgeStudyPopulation.NOT_APPLICABLE,
            )
        if document_type == KnowledgeDocumentType.ADVERSE_CASE_REPORT:
            return (
                KnowledgeEvidenceLevel.CASE_REPORT,
                KnowledgeStudyPopulation.HUMAN,
            )
        if document_type == KnowledgeDocumentType.PHARM_REVIEW:
            return (
                KnowledgeEvidenceLevel.REVIEW_ARTICLE,
                KnowledgeStudyPopulation.NOT_APPLICABLE,
            )
        if document_type != KnowledgeDocumentType.RESEARCH_ARTICLE:
            return (
                KnowledgeEvidenceLevel.UNKNOWN,
                KnowledgeStudyPopulation.UNKNOWN,
            )

        text = f"{title}\n{content}"
        study_population = cls._classify_research_population(text)
        evidence_level = cls._classify_research_evidence(
            text=text,
            study_population=study_population,
        )
        return evidence_level, study_population

    @classmethod
    def _classify_research_population(
        cls,
        text: str,
    ) -> KnowledgeStudyPopulation:
        populations = {
            population
            for pattern, population in (
                (cls._HUMAN_STUDY, KnowledgeStudyPopulation.HUMAN),
                (cls._ANIMAL_STUDY, KnowledgeStudyPopulation.ANIMAL),
                (cls._CELL_STUDY, KnowledgeStudyPopulation.CELL),
            )
            if pattern.search(text)
        }
        if len(populations) > 1:
            return KnowledgeStudyPopulation.MIXED
        if populations:
            return next(iter(populations))
        return KnowledgeStudyPopulation.UNKNOWN

    @classmethod
    def _classify_research_evidence(
        cls,
        *,
        text: str,
        study_population: KnowledgeStudyPopulation,
    ) -> KnowledgeEvidenceLevel:
        if cls._SYSTEMATIC_REVIEW.search(text):
            return KnowledgeEvidenceLevel.SYSTEMATIC_REVIEW
        if study_population in {
            KnowledgeStudyPopulation.ANIMAL,
            KnowledgeStudyPopulation.CELL,
        }:
            return KnowledgeEvidenceLevel.PRECLINICAL
        if study_population == KnowledgeStudyPopulation.HUMAN and cls._CLINICAL_STUDY.search(text):
            return KnowledgeEvidenceLevel.CLINICAL_STUDY
        if study_population == KnowledgeStudyPopulation.HUMAN and cls._OBSERVATIONAL_STUDY.search(text):
            return KnowledgeEvidenceLevel.OBSERVATIONAL_STUDY
        return KnowledgeEvidenceLevel.UNKNOWN

    @staticmethod
    def _unique(values: Iterable[str]) -> list[str]:
        return list(dict.fromkeys(values))

    @staticmethod
    def _unique_catalog_entries(
        values: Iterable[KnowledgeEntityCatalogEntry],
    ) -> list[KnowledgeEntityCatalogEntry]:
        unique: list[KnowledgeEntityCatalogEntry] = []
        seen: set[tuple[str, str, str]] = set()
        for entry in values:
            key = (
                entry.canonical_name,
                entry.entity_type.value,
                entry.kind.value,
            )
            if key not in seen:
                unique.append(entry)
                seen.add(key)
        return unique

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
