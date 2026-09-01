import re
from collections.abc import Iterable

from pydantic import BaseModel, Field

from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.rag.metadata.supplement_interaction_registry import (
    find_supplement_interaction_pair,
)
from ai_worker.schemas.knowledge import (
    KnowledgeDocumentType,
    KnowledgeEvidenceLevel,
    KnowledgeSectionType,
    KnowledgeStudyPopulation,
)


class ExtractedKnowledgeEntities(BaseModel):
    drug_names: list[str] = Field(default_factory=list)
    ingredient_names: list[str] = Field(default_factory=list)
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

    _REGULATORY_DOCUMENT_TYPES = {
        KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE,
        KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE,
        KnowledgeDocumentType.SUPPLEMENT_CODE,
    }

    _PAIR_INFERENCE_DOCUMENT_TYPES = {
        KnowledgeDocumentType.RESEARCH_ARTICLE,
        KnowledgeDocumentType.SUPPLEMENT_INTERACTION_MONOGRAPH,
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
        pair = (
            find_supplement_interaction_pair(f"{title}\n{content}")
            if document_type in self._PAIR_INFERENCE_DOCUMENT_TYPES
            else None
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
        if annotated:
            pair_types = {match.pair_type.value for match in annotated}
            interaction_type = next(iter(pair_types)) if len(pair_types) == 1 else None
            return title_entities.model_copy(
                update={
                    "drug_names": self._unique(name for match in annotated for name in match.drug_names),
                    "ingredient_names": self._unique(name for match in annotated for name in match.ingredient_names),
                    "interaction_type": interaction_type,
                    "interaction_pair_keys": self._unique(
                        key for match in annotated for key in match.interaction_pair_keys
                    ),
                    "evidence_level": evidence_level,
                    "study_population": study_population,
                }
            )
        if pair is None:
            return title_entities.model_copy(
                update={
                    "evidence_level": evidence_level,
                    "study_population": study_population,
                }
            )
        return title_entities.model_copy(
            update={
                "ingredient_names": list(pair.canonical_names),
                "interaction_type": "SUPPLEMENT_SUPPLEMENT",
                "interaction_pair_keys": [pair.pair_key],
                "evidence_level": evidence_level,
                "study_population": study_population,
            }
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
