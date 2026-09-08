import hashlib
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol

from langchain_text_splitters import RecursiveCharacterTextSplitter

from ai_worker.rag.metadata.interaction_annotation_registry import (
    KnowledgeInteractionAnnotationRegistry,
)
from ai_worker.rag.metadata.knowledge_entity_extractor import (
    KnowledgeEntityExtractor,
)
from ai_worker.rag.parsers.supplement_code_parser import (
    SupplementCodeParser,
)
from ai_worker.rag.splitters.repairers import (
    CallableDocumentChunkRepairer,
    DocumentChunkRepairRegistry,
)
from ai_worker.schemas.knowledge import (
    KnowledgeChunk,
    KnowledgeChunkMetadata,
    KnowledgeContentKind,
    KnowledgeDocumentType,
    KnowledgeEvidenceLevel,
    KnowledgePage,
    KnowledgeSection,
    KnowledgeSectionType,
    KnowledgeStudyPopulation,
)


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class WordTokenCounter:
    """테스트와 오프라인 규칙 검증에 사용하는 단순 카운터입니다."""

    def count(self, text: str) -> int:
        return len(text.split())


class TiktokenTokenCounter:
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        import tiktoken

        self._encoding = tiktoken.get_encoding(encoding_name)

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text))


@dataclass(frozen=True)
class ChunkingPolicy:
    target_min_tokens: int
    hard_max_tokens: int
    overlap_tokens: int


_POLICIES = {
    KnowledgeDocumentType.REGULATORY_DRUG_LABEL: ChunkingPolicy(250, 600, 40),
    KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE: ChunkingPolicy(150, 450, 0),
    KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE: ChunkingPolicy(250, 600, 40),
    KnowledgeDocumentType.SUPPLEMENT_CODE: ChunkingPolicy(200, 500, 0),
    KnowledgeDocumentType.DRUG_ENCYCLOPEDIA: ChunkingPolicy(250, 600, 50),
    KnowledgeDocumentType.ADVERSE_CASE_REPORT: ChunkingPolicy(300, 700, 0),
    KnowledgeDocumentType.PHARM_REVIEW: ChunkingPolicy(400, 750, 80),
    KnowledgeDocumentType.RESEARCH_ARTICLE: ChunkingPolicy(400, 800, 100),
    KnowledgeDocumentType.SUPPLEMENT_INTERACTION_MONOGRAPH: ChunkingPolicy(150, 450, 0),
}


_INTERACTION_LABELS = {
    "DRUG_DRUG": "약-약",
    "DRUG_SUPPLEMENT": "약-영양제",
    "SUPPLEMENT_SUPPLEMENT": "영양제-영양제",
    "DRUG_FOOD": "약-음식",
}

_EVIDENCE_LABELS = {
    "REGULATORY": "공인 규정·가이드",
    "SYSTEMATIC_REVIEW": "체계적 문헌고찰",
    "REVIEW_ARTICLE": "종설",
    "CLINICAL_STUDY": "임상시험",
    "OBSERVATIONAL_STUDY": "관찰연구",
    "CASE_REPORT": "사례보고",
    "PRECLINICAL": "전임상 연구",
}

_POPULATION_LABELS = {
    "HUMAN": "사람",
    "ANIMAL": "동물",
    "CELL": "세포",
    "MIXED": "혼합",
    "NOT_APPLICABLE": "해당 없음",
}

_ASPIRIN_WARFARIN_REVIEW_DOCUMENT_ID = "research_drug_nutrient_interactions-3dd5c1de206c9a88"
_WARFARIN_SUPPLEMENT_REVIEW_DOCUMENT_ID = "research_drug_nutrient_interactions-299edbe35f581616"
_DRUG_VITAMIN_D_REVIEW_DOCUMENT_ID = "research_drug_nutrient_interactions-80c3d674cbc86d03"
_STATINS_VITAMIN_D_REVIEW_DOCUMENT_ID = "research_drug_nutrient_interactions-186668a2a92b533c"
_LEVOTHYROXINE_CALCIUM_REVIEW_DOCUMENT_ID = "research_drug_nutrient_interactions-502801c809b5ec8d"
_PRIMARY_CARE_HERB_DRUG_REVIEW_DOCUMENT_ID = "research_herb_drug_interactions-83a8fd3c37dd38e1"
_ST_JOHNS_WORT_REVIEW_DOCUMENT_ID = "research_herb_drug_interactions-e5fcbe5d02f9650c"
_VITAMIN_B12_DEFICIENCY_DOCUMENT_ID = "research_supplement_interactions-87c6ca8187e6dab7"
_BOTANICAL_SUPPLEMENT_ADVERSE_EFFECTS_DOCUMENT_ID = "research_supplement_adverse_effects-69b9c0581b9f9612"
_CALCIUM_IRON_ABSORPTION_REVIEW_DOCUMENT_ID = "research_supplement_interactions-016c81c9a3e29ebd"
_CALCIUM_IRON_META_ANALYSIS_DOCUMENT_ID = "research_supplement_interactions-7983c60e9a092828"
_OLDER_ADULT_SUPPLEMENT_INTERACTION_REVIEW_DOCUMENT_ID = "research_supplement_interactions-d2e4dfcb8919c4c3"
_ZINC_IRON_STATUS_STUDY_DOCUMENT_ID = "research_supplement_interactions-ce2c45272c5bd272"
_VITAMIN_C_COPPER_STUDY_DOCUMENT_ID = "research_supplement_interactions-7cc01e25b07044ff"
_STATINS_VITAMIN_D_REVIEW_TITLE = "Statins, Vitamin D, and Cardiovascular Health: A Comprehensive Review"

_DRUG_VITAMIN_D_DISCUSSION_BOUNDARIES = (
    "The currently available literature on drug-vitamin D interactions",
    "Because vitamin D is highly hydrophobic",
    "Given the increasing prevalence of vitamin D supplementation",
)

_DRUG_VITAMIN_D_REVIEW_BOUNDARIES = (
    "Introduction",
    "The metabolically active 1,25(OH)2 D form",
    "Methods Study selection",
    "Data abstraction and quality assessment",
    "Results",
    "Drugs that interfere with vitamin D absorption",
    "Drugs that interfere with vitamin D metabolism Statins",
    "Antimicrobials",
    "Antiepileptic drugs",
    "Corticosteroids",
    "Immunosuppressive agents",
    "Chemotherapeutic agents",
    "Highly active antiretroviral agents (HAART)",
    "Histamine H2-receptor antagonists",
    "Drug-vitamin D interactions that induce side effects",
    "Discussion",
    *_DRUG_VITAMIN_D_DISCUSSION_BOUNDARIES,
)

_DRUG_VITAMIN_D_VERIFIED_PAGE_RANGES = {
    "Drug-vitamin D interactions: A systematic review of the literature": (1, 1),
    "Introduction": (2, 2),
    "Methods Study selection": (3, 4),
    "Results": (5, 5),
    "Drugs that interfere with vitamin D metabolism Statins": (6, 6),
    "Antiepileptic drugs": (7, 8),
    "Corticosteroids": (8, 9),
    "Chemotherapeutic agents": (10, 10),
    "Highly active antiretroviral agents (HAART)": (10, 11),
    "Histamine H2-receptor antagonists": (11, 11),
}

_STATINS_VITAMIN_D_REVIEW_BOUNDARIES = (
    "1. Introduction",
    "2. Statins and Vitamin D: Mechanistic Interactions",
    "2.3. Molecular Mediators and Transport Proteins Involved in Statin–Vitamin D Interactions",
    "2.4. Influence on Vitamin D Synthesis and Metabolism",
    "Although cholesterol and vitamin D",
    "2.5. Combined Role of Statins and Vitamin D in Cardiovascular Risk Reduction",
    "• Endothelial Protection",
    "3. Changes in Vitamin D Levels in Statin Users: Clinical Evidence",
    "Key Point: Current evidence",
    "4. Vitamin D Supplementation in Statin-Treated Patients",
    "Guideline Recommendations for Vitamin D Testing and Supplementation",
    "5. Vitamin D, Atherosclerosis, and Coronary Artery Disease",
    "5.4. Current Consensus",
    "5.7. Preventive Cardiovascular Strategies",
    "6. Summary of Key Findings and Future Therapeutic Directions",
    "7. Limitations of the Study",
    "8. Conclusions",
)

_STATINS_VITAMIN_D_VERIFIED_PAGE_RANGES = {
    "2. Statins and Vitamin D: Mechanistic Interactions": (2, 3),
    "• Endothelial Protection": (6, 7),
    "4. Vitamin D Supplementation in Statin-Treated Patients": (10, 10),
}

_STATINS_VITAMIN_D_CONCLUSION_END = "vitamin D-deficient populations."

_LEVOTHYROXINE_CALCIUM_REVIEW_BOUNDARIES = (
    "Results:",
    "Conclusions:",
    "Introduction",
    "Materials and Methods Subjects",
    "Study design",
    "Assays",
    "Statistics",
    "Discussion",
    "Our study also indicates that the effects",
    "One possible limitation of this study",
)
_LEVOTHYROXINE_CALCIUM_REVIEW_END = "separated from all of these calcium products."
_PARENTHETICAL_NUMERIC_CITATION_PATTERN = re.compile(r"\s*\(\s*\d+(?:\s*(?:[,;]|[-–—])\s*\d+)*\s*\)")
_INLINE_FIGURE_REFERENCE_PATTERN = re.compile(
    r"\s*[\[(]\s*Fig\.?\s*\d+\s*[\])]",
    flags=re.IGNORECASE,
)

_PRIMARY_CARE_HERB_DRUG_REVIEW_BOUNDARIES = (
    "Introduction",
    "Prevalence and patterns in primary care",
    "Primary healthcare and common herbal products",
    "Disclosure patterns",
    "Patient communication barriers",
    "High-risk clinical scenarios in primary care",
    "Detection and assessment challenges",
    "Operational constraints",
    "Existing knowledge and gaps in training",
    "Information resource challenge",
    "Evidence quality levels",
    "Recent advancements in drug–herb interaction management",
    "Scope and boundaries of the review",
    "Future directions and recommendations",
    "Conclusion",
)
_PRIMARY_CARE_HERB_DRUG_REVIEW_END = "avoid fatal outcomes."
_PRIMARY_CARE_HERB_DRUG_NUMERIC_CITATION_PATTERN = re.compile(r"\s*\(\s*\d+(?:\s*(?:,|[-–—])\s*\d+)*\s*\)")
_PRIMARY_CARE_HERB_DRUG_FIGURE_PATTERN = re.compile(
    r"\s*FIGURE\s+\d+.*?(?=Information resource challenge)",
    flags=re.DOTALL | re.IGNORECASE,
)

_ST_JOHNS_WORT_REVIEW_TITLE = (
    "Interaction of St John’s wort with conventional drugs: systematic review of clinical trials"
)
_ST_JOHNS_WORT_REVIEW_BOUNDARIES = (
    "Introduction",
    "Methods",
    "Results",
    "Pharmacokinetic details",
    "Study design",
    "Effects of St John’s wort",
    "Discussion",
    "We used a somewhat arbitrary threshold (20%)",
    "What is already known on this topic",
)
_ST_JOHNS_WORT_REVIEW_END = "particularly in conjunction with conventional drugs"
_ST_JOHNS_WORT_TABLE_PATTERN = re.compile(
    r"Characteristics of methods used in 22 reviewed studies.*?(?=Discussion)",
    flags=re.DOTALL | re.IGNORECASE,
)
_ST_JOHNS_WORT_VERIFIED_PAGE_RANGES = {
    _ST_JOHNS_WORT_REVIEW_TITLE: (1, 1),
    "Introduction": (1, 1),
    "Methods": (1, 2),
    "Results": (2, 2),
    "Pharmacokinetic details": (2, 2),
    "Study design": (2, 2),
    "Effects of St John’s wort": (2, 2),
    "Discussion": (2, 3),
    "We used a somewhat arbitrary threshold (20%)": (3, 3),
    "What is already known on this topic": (3, 3),
}

_VITAMIN_B12_DEFICIENCY_END_MARKERS = (
    "stored in the liver.",
    "mental function, including dementia.",
    "cells that produce intrinsic factor.",
    "not improve after treatment.",
)
_VITAMIN_B12_DEFICIENCY_PREVENTION_HEADING = "Prevention of Vitamin B12 Deficiency"
_VITAMIN_B12_DEFICIENCY_PREVENTION_END = "vitamin B12 deficiency."

_BOTANICAL_SUPPLEMENT_ADVERSE_EFFECTS_END_MARKERS = (
    "and Ginkgo biloba (14).",
    "transplantation.",
    "of green tea, consumed as tea or in capsules.",
    "extracts were the most usual forms involved.",
    "cytochrome P450 (CYP) 3A4 activity was observed.",
    "or conventional drug was found.",
    "Food and Drug Administration (FDA).",
    "in a case of fatal breakthrough seizure.",
    "transient methaemoglobinaemia.",
    "hypokalaemia and metabolic alkalosis.",
    "responsible for liver damage via an interaction with CYP3A4.",
    "No interaction with nutrients or conventional drugs has been described.",
)

_CALCIUM_IRON_ABSORPTION_REVIEW_BOUNDARIES = (
    "Introduction",
    "A critical evaluation of studies showing an acute effect of calcium on iron absorption",
    "The “timing” of the calcium effect on iron absorption",
    "Using another approach, Tidehag",
    "Does high calcium intake affect iron status in vulnerable populations?",
    "Why is iron absorption sometimes affected by high calcium intake, while there is no effect on iron status?",
    "We have investigated the potential",
    "Conclusions",
)
_CALCIUM_IRON_ABSORPTION_REVIEW_END = "public health problems instead of resolving them."
_ZINC_IRON_STATUS_STUDY_BOUNDARIES = (
    "SUBJECTS AND METHODS",
    "Sample collection.",
    "RESULTS",
    "DISCUSSION",
)
_ZINC_IRON_STATUS_STUDY_END = "impairs the iron status of women with low iron stores."
_BRACKETED_NUMERIC_CITATION_PATTERN = re.compile(r"\s*\[\s*\d+(?:\s*(?:[,;]|[-–—])\s*\d+)*\s*\]")


_COMMON_CAUTION_HEADINGS = {
    "섭취 시 주의사항": KnowledgeSectionType.CAUTION,
    "사용상의 주의사항": KnowledgeSectionType.CAUTION,
    "주의사항": KnowledgeSectionType.CAUTION,
    "부작용": KnowledgeSectionType.ADVERSE_EVENT,
    "상호작용": KnowledgeSectionType.INTERACTION,
}


_KPICIA_ATTACHED_DRUG_ENCYCLOPEDIA_HEADINGS = {
    "요약": KnowledgeSectionType.SUMMARY,
    "약리작용": KnowledgeSectionType.OVERVIEW,
    "효능.효과": KnowledgeSectionType.FUNCTION,
    "용법": KnowledgeSectionType.DAILY_INTAKE,
    "용법·용량": KnowledgeSectionType.DAILY_INTAKE,
    "용법․용량": KnowledgeSectionType.DAILY_INTAKE,
    "경고": KnowledgeSectionType.CAUTION,
    "금기": KnowledgeSectionType.CAUTION,
    "주의사항": KnowledgeSectionType.CAUTION,
    "접종권장대상": KnowledgeSectionType.FUNCTION,
    "종류": KnowledgeSectionType.OVERVIEW,
    "부작용": KnowledgeSectionType.ADVERSE_EVENT,
    "다른백신과의동시접종": KnowledgeSectionType.INTERACTION,
}


_HEADINGS: dict[KnowledgeDocumentType, dict[str, KnowledgeSectionType]] = {
    KnowledgeDocumentType.REGULATORY_DRUG_LABEL: {
        "HIGHLIGHTS OF PRESCRIBING INFORMATION": KnowledgeSectionType.SUMMARY,
        "WARNING: NOT FOR TREATMENT OF OBESITY OR FOR WEIGHT LOSS": KnowledgeSectionType.CAUTION,
        "INDICATIONS AND USAGE": KnowledgeSectionType.FUNCTION,
        "1 INDICATIONS AND USAGE": KnowledgeSectionType.FUNCTION,
        "DOSAGE AND ADMINISTRATION": KnowledgeSectionType.DAILY_INTAKE,
        "2 DOSAGE AND ADMINISTRATION": KnowledgeSectionType.DAILY_INTAKE,
        "DOSAGE FORMS AND STRENGTHS": KnowledgeSectionType.DAILY_INTAKE,
        "3 DOSAGE FORMS AND STRENGTHS": KnowledgeSectionType.DAILY_INTAKE,
        "CONTRAINDICATIONS": KnowledgeSectionType.CAUTION,
        "4 CONTRAINDICATIONS": KnowledgeSectionType.CAUTION,
        "WARNINGS AND PRECAUTIONS": KnowledgeSectionType.CAUTION,
        "5 WARNINGS AND PRECAUTIONS": KnowledgeSectionType.CAUTION,
        "ADVERSE REACTIONS": KnowledgeSectionType.ADVERSE_EVENT,
        "6 ADVERSE REACTIONS": KnowledgeSectionType.ADVERSE_EVENT,
        "DRUG INTERACTIONS": KnowledgeSectionType.INTERACTION,
        "7 DRUG INTERACTIONS": KnowledgeSectionType.INTERACTION,
        "USE IN SPECIFIC POPULATIONS": KnowledgeSectionType.CAUTION,
        "8 USE IN SPECIFIC POPULATIONS": KnowledgeSectionType.CAUTION,
        "10 OVERDOSAGE": KnowledgeSectionType.CAUTION,
        "11 DESCRIPTION": KnowledgeSectionType.OVERVIEW,
        "12 CLINICAL PHARMACOLOGY": KnowledgeSectionType.OVERVIEW,
        "13 NONCLINICAL TOXICOLOGY": KnowledgeSectionType.OVERVIEW,
        "16 HOW SUPPLIED/STORAGE AND HANDLING": KnowledgeSectionType.OVERVIEW,
        "17 PATIENT COUNSELING INFORMATION": KnowledgeSectionType.CAUTION,
    },
    KnowledgeDocumentType.SUPPLEMENT_CODE: {
        "원료": KnowledgeSectionType.INGREDIENT,
        "규격": KnowledgeSectionType.STANDARD,
        "기능성 내용": KnowledgeSectionType.FUNCTION,
        "일일섭취량": KnowledgeSectionType.DAILY_INTAKE,
        "시험법": KnowledgeSectionType.TEST_METHOD,
        **_COMMON_CAUTION_HEADINGS,
    },
    KnowledgeDocumentType.SUPPLEMENT_FUNCTION_GUIDE: {
        "기능성 내용": KnowledgeSectionType.FUNCTION,
        "기능성 원료": KnowledgeSectionType.INGREDIENT,
        "일일섭취량": KnowledgeSectionType.DAILY_INTAKE,
        "섭취 시 주의사항": KnowledgeSectionType.CAUTION,
    },
    KnowledgeDocumentType.DRUG_ENCYCLOPEDIA: {
        "개요": KnowledgeSectionType.OVERVIEW,
        "효능·효과": KnowledgeSectionType.FUNCTION,
        "효능․효과": KnowledgeSectionType.FUNCTION,
        "용법·용량": KnowledgeSectionType.DAILY_INTAKE,
        "용법․용량": KnowledgeSectionType.DAILY_INTAKE,
        **_COMMON_CAUTION_HEADINGS,
        **_KPICIA_ATTACHED_DRUG_ENCYCLOPEDIA_HEADINGS,
    },
    KnowledgeDocumentType.ADVERSE_CASE_REPORT: {
        "환자 정보": KnowledgeSectionType.CASE_SUMMARY,
        "이상사례": KnowledgeSectionType.ADVERSE_EVENT,
        "복용 의약품 정보": KnowledgeSectionType.INGREDIENT,
        "상세 사항": KnowledgeSectionType.ASSESSMENT,
        "평가 의견 및 참고 사항": KnowledgeSectionType.ASSESSMENT,
        "WHO-UMC 인과성 평가 기준": KnowledgeSectionType.ASSESSMENT,
    },
    KnowledgeDocumentType.PHARM_REVIEW: {
        "개요": KnowledgeSectionType.OVERVIEW,
        "키워드": KnowledgeSectionType.SUMMARY,
        "서론": KnowledgeSectionType.INTRODUCTION,
        "결론": KnowledgeSectionType.CONCLUSION,
        "참고문헌": KnowledgeSectionType.REFERENCES,
        "◘ 참고문헌 ◘": KnowledgeSectionType.REFERENCES,
    },
    KnowledgeDocumentType.RESEARCH_ARTICLE: {
        "Abstract": KnowledgeSectionType.SUMMARY,
        "Keywords": KnowledgeSectionType.SUMMARY,
        "Introduction": KnowledgeSectionType.INTRODUCTION,
        "Materials and Methods": KnowledgeSectionType.METHODS,
        "Methods": KnowledgeSectionType.METHODS,
        "Results": KnowledgeSectionType.RESULTS,
        "Discussion": KnowledgeSectionType.DISCUSSION,
        "Limitations": KnowledgeSectionType.DISCUSSION,
        "Conclusion": KnowledgeSectionType.CONCLUSION,
        "Conclusions": KnowledgeSectionType.CONCLUSION,
        "References": KnowledgeSectionType.REFERENCES,
        "Bibliography": KnowledgeSectionType.REFERENCES,
        "Drug-Nutrient Interactions": KnowledgeSectionType.INTERACTION,
        "Drug–Nutrient Interactions": KnowledgeSectionType.INTERACTION,
        "Food-Drug Interactions": KnowledgeSectionType.INTERACTION,
        "Food–Drug Interactions": KnowledgeSectionType.INTERACTION,
    },
    KnowledgeDocumentType.DRUG_FOOD_INTERACTION_GUIDE: {
        "의약품-식품간 상호작용 요약서": KnowledgeSectionType.INTERACTION,
        "그밖에 안전한 약복용 방법": KnowledgeSectionType.CAUTION,
        "발 행 일": KnowledgeSectionType.REFERENCES,
    },
    KnowledgeDocumentType.SUPPLEMENT_INTERACTION_MONOGRAPH: {
        **_COMMON_CAUTION_HEADINGS,
    },
}


_ATTACHED_BODY_HEADINGS_BY_SOURCE = {
    "kpicia_drug_encyclopedia": frozenset(_KPICIA_ATTACHED_DRUG_ENCYCLOPEDIA_HEADINGS),
    "research_supplement_adverse_effects": frozenset(
        {
            "Camellia sinensis (L.) Kuntze (green tea)",
            "Cinnamomum verum J. Presl (Cinnamomum zeylanicum cinnamon)",
            "Citrus aurantium L. (bitter orange)",
            "Echinacea purpurea (L.) Moench (Eastern purple coneflower)",
            "Ginkgo biloba L. (Ginkgo/maidenhair tree)",
            "Glycine max (L.) Merr. (soybean)",
            "Glycyrrhiza glabra L. (liquorice)",
            "Harpagophytum procumbens (Burch.) DC. (Devil’s claw)",
            "Hypericum perforatum L. (St John’s wort)",
            "Panax ginseng C.A. Meyer (ginseng)",
            "Valeriana officinalis L. (valerian)",
            "Vitex agnus castus L. (vitex or ‘chaste tree’)",
            "Vitis vinifera L. (grape)",
        }
    ),
}
_ADVERSE_CASE_SUMMARY_FIELDS = (
    r"나이\s*[·ㆍ]\s*성별",
    r"현재\s*병력",
    r"투여\s*목적",
    r"의심\s*약물",
    r"병용\s*약물",
)

_ATTACHED_BODY_PROSE_CONTINUATION = re.compile(r"^(?:하면|하자면|은|는|이|가|을|를|의|도|만|에서|에는|으로)(?:\s|$)")
_RESEARCH_NUMBERED_INTERACTION_HEADING = re.compile(
    r"(?im)^\s*\d+(?:\.\d+)*\.?(?:\s*\|\s*|\s+)"
    r"(?P<title>[^\n]{0,80}\b(?:DNIs?|"
    r"Drug[\s–—-]*Nutrient\s+Interactions?|"
    r"Food[\s–—-]*Drug\s+Interactions?)"
    r"(?:\s*\([^\n)]+\))?)\s*$"
)
_RESEARCH_NUMBERED_SUBSECTION_HEADING = re.compile(
    r"(?im)^\s*\d+(?:\.\d+)+\.?(?:\s*\|\s*|\s+)"
    r"(?P<title>[A-Z][^\n]{1,120}?)\s*$"
)
_RESEARCH_NUMBERED_TOP_LEVEL_HEADING = re.compile(
    r"(?im)^\s*\d+(?:\.\s+|\s*\|\s*)"
    r"(?P<title>[A-Z][^\n]{1,120}?)\s*$"
)
_RESEARCH_NUTRIENT_SUBHEADING = re.compile(
    r"(?im)^\s*(?P<title>[A-Z][A-Za-z]*(?:[\s/–—-]+[A-Za-z]+){0,5}"
    r"\s*\((?:B\s*\d+|[A-Z])\))\s*$"
)
_REGULATORY_NUMBERED_SUBSECTION_HEADING = re.compile(
    r"(?im)^\s*\d+\.\d+(?:\.\d+)*\s+"
    r"(?P<title>[A-Z][^\n]{1,120}?)\s*$"
)
_REGULATORY_BODY_SUBHEADING = re.compile(
    r"(?im)^\s*(?P<title>Adults|Pediatrics|Absorption|Distribution|"
    r"Elimination|Metabolism|Excretion|Secondary and Tertiary Hypothyroidism)\s*$"
)

_HeadingCandidate = tuple[
    int,
    int,
    str,
    KnowledgeSectionType | None,
]


class KnowledgeSplitter:
    _SEPARATORS = [
        "\n\n",
        "\n",
        "다. ",
        ". ",
        "? ",
        "! ",
        "; ",
        ", ",
        " ",
        "",
    ]

    def __init__(
        self,
        token_counter: TokenCounter | None = None,
        interaction_annotations: KnowledgeInteractionAnnotationRegistry | None = None,
        tokenizer_encoding: str = "cl100k_base",
    ) -> None:
        self._tokenizer_encoding = tokenizer_encoding.strip()
        if not self._tokenizer_encoding:
            raise ValueError("tokenizer_encoding은 비어 있을 수 없습니다.")
        self._token_counter = token_counter or TiktokenTokenCounter(self._tokenizer_encoding)
        self._supplement_code_parser = SupplementCodeParser()
        self._entity_extractor = KnowledgeEntityExtractor(
            interaction_annotations=interaction_annotations,
        )

    @property
    def tokenizer_encoding(self) -> str:
        return self._tokenizer_encoding

    def split(
        self,
        pages: list[KnowledgePage],
        *,
        verified_section_headings: list[str] | None = None,
    ) -> list[KnowledgeChunk]:
        if not pages:
            return []

        self._validate_single_document(pages)
        if pages[0].metadata.document_id == _PRIMARY_CARE_HERB_DRUG_REVIEW_DOCUMENT_ID and any(
            page.blocks for page in pages
        ):
            return self._split_primary_care_herb_drug_review_pages(pages)
        if any(page.blocks for page in pages):
            return self._repair_verified_document_chunks(
                self._split_block_pages(
                    pages,
                    verified_section_headings=verified_section_headings,
                )
            )

        metadata = pages[0].metadata
        policy = _POLICIES[metadata.document_type]
        sections, page_ranges = self._split_sections(
            pages,
            verified_section_headings=verified_section_headings,
        )
        sections = self._drop_publication_front_matter(
            sections,
            metadata.document_type,
        )
        sections = self._merge_leading_context(
            sections,
            policy,
        )
        sections = self._merge_heading_only_sections(sections)
        chunks: list[KnowledgeChunk] = []

        for section in sections:
            if self._should_skip_section(
                section,
                document_type=metadata.document_type,
            ):
                continue
            if not self._has_meaningful_body(section):
                continue

            contents = self._split_section_content(
                section.content,
                policy,
                document_type=metadata.document_type,
            )
            for content, local_start, local_end in contents:
                cleaned = content.strip()
                if not cleaned or not self._has_meaningful_text(
                    cleaned,
                    section.section_title,
                ):
                    continue
                if metadata.document_type == KnowledgeDocumentType.SUPPLEMENT_CODE:
                    page_start, page_end = (
                        section.page_start,
                        section.page_end,
                    )
                else:
                    page_start, page_end = self._page_range_for(
                        section.source_start + local_start,
                        section.source_start + local_end,
                        page_ranges,
                    )
                chunk_section = section.model_copy(
                    update={
                        "page_start": page_start,
                        "page_end": page_end,
                    }
                )
                chunks.append(
                    self._build_chunk(
                        content=cleaned,
                        section=chunk_section,
                        chunk_index=len(chunks),
                        metadata=metadata,
                    )
                )

        return self._repair_verified_document_chunks(chunks)

    def _split_primary_care_herb_drug_review_pages(
        self,
        pages: list[KnowledgePage],
    ) -> list[KnowledgeChunk]:
        """검증한 좌표 블록을 일반 섹션 필터 전에 페이지 순서로 보존합니다."""
        metadata = pages[0].metadata
        page_chunks: list[KnowledgeChunk] = []
        for page in pages:
            content = "\n".join(
                block.content.strip()
                for block in sorted(page.blocks, key=lambda item: item.order)
                if block.kind == KnowledgeContentKind.TEXT and block.content.strip()
            ).strip()
            if not content:
                continue
            section = KnowledgeSection(
                content=content,
                section_type=KnowledgeSectionType.INTERACTION,
                section_title=metadata.title,
                page_start=page.page_number,
                page_end=page.page_number,
                source_start=0,
                source_end=len(content),
            )
            page_chunks.append(
                self._build_chunk(
                    content=content,
                    section=section,
                    chunk_index=len(page_chunks),
                    metadata=metadata,
                )
            )
        return self._repair_verified_document_chunks(page_chunks)

    def _repair_verified_document_chunks(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        if not chunks:
            return chunks

        repaired = self._verified_document_repair_registry().repair(chunks)
        if repaired is chunks:
            return chunks
        return [self._rebuild_verified_chunk(chunk, index) for index, chunk in enumerate(repaired)]

    def _verified_document_repair_registry(self) -> DocumentChunkRepairRegistry:
        return DocumentChunkRepairRegistry(
            repairers=(
                CallableDocumentChunkRepairer(
                    _VITAMIN_B12_DEFICIENCY_DOCUMENT_ID,
                    self._resegment_vitamin_b12_deficiency,
                ),
                CallableDocumentChunkRepairer(
                    _BOTANICAL_SUPPLEMENT_ADVERSE_EFFECTS_DOCUMENT_ID,
                    self._resegment_botanical_supplement_adverse_effects,
                ),
                CallableDocumentChunkRepairer(
                    _CALCIUM_IRON_ABSORPTION_REVIEW_DOCUMENT_ID,
                    self._resegment_calcium_iron_absorption_review,
                ),
                CallableDocumentChunkRepairer(
                    _ZINC_IRON_STATUS_STUDY_DOCUMENT_ID,
                    self._resegment_zinc_iron_status_study,
                ),
                CallableDocumentChunkRepairer(
                    _VITAMIN_C_COPPER_STUDY_DOCUMENT_ID,
                    self._clean_vitamin_c_copper_study,
                ),
                CallableDocumentChunkRepairer(
                    _CALCIUM_IRON_META_ANALYSIS_DOCUMENT_ID,
                    self._clean_calcium_iron_meta_analysis,
                ),
                CallableDocumentChunkRepairer(
                    _OLDER_ADULT_SUPPLEMENT_INTERACTION_REVIEW_DOCUMENT_ID,
                    self._clean_older_adult_supplement_interaction_review,
                ),
                CallableDocumentChunkRepairer(
                    _PRIMARY_CARE_HERB_DRUG_REVIEW_DOCUMENT_ID,
                    self._resegment_primary_care_herb_drug_review,
                ),
                CallableDocumentChunkRepairer(
                    _ST_JOHNS_WORT_REVIEW_DOCUMENT_ID,
                    self._resegment_st_johns_wort_review,
                ),
                CallableDocumentChunkRepairer(
                    _LEVOTHYROXINE_CALCIUM_REVIEW_DOCUMENT_ID,
                    self._resegment_levothyroxine_calcium_review,
                ),
                CallableDocumentChunkRepairer(
                    _STATINS_VITAMIN_D_REVIEW_DOCUMENT_ID,
                    self._repair_statins_vitamin_d_review,
                ),
                CallableDocumentChunkRepairer(
                    _DRUG_VITAMIN_D_REVIEW_DOCUMENT_ID,
                    self._resegment_drug_vitamin_d_review,
                ),
                CallableDocumentChunkRepairer(
                    _WARFARIN_SUPPLEMENT_REVIEW_DOCUMENT_ID,
                    self._repair_warfarin_supplement_review,
                ),
                CallableDocumentChunkRepairer(
                    _ASPIRIN_WARFARIN_REVIEW_DOCUMENT_ID,
                    self._repair_aspirin_warfarin_review,
                ),
            )
        )

    def _repair_statins_vitamin_d_review(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        text_chunks = [chunk for chunk in chunks if chunk.metadata.content_kind != KnowledgeContentKind.TABLE]
        table_chunks = [chunk for chunk in chunks if chunk.metadata.content_kind == KnowledgeContentKind.TABLE]
        return [
            *self._resegment_statins_vitamin_d_review(text_chunks),
            *table_chunks,
        ]

    def _repair_warfarin_supplement_review(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        repaired = list(chunks)
        self._repair_warfarin_review_discussion_boundary(repaired)
        return repaired

    def _repair_aspirin_warfarin_review(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        repaired = list(chunks)
        self._move_aspirin_review_abstract_sentence(repaired)
        self._split_aspirin_review_pantothenic_acid(repaired)
        self._repair_aspirin_review_vitamin_k_boundary(repaired)
        self._repair_aspirin_review_discussion_overlap(repaired)
        repaired = [
            self._repair_aspirin_review_table_chunk(chunk)
            if chunk.metadata.content_kind == KnowledgeContentKind.TABLE
            else chunk
            for chunk in repaired
        ]
        repaired = self._regroup_verified_table_chunks(repaired)
        return [chunk for chunk in repaired if chunk.content.strip()]

    def _resegment_vitamin_b12_deficiency(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        merged = self._merge_verified_chunk_text(chunks)
        merged = re.sub(
            r"\bFull Review:.*?\bLast updated:\s*[A-Za-z]+\s+\d{4}\s*",
            "",
            merged,
            count=1,
        ).strip()
        segments = self._split_merged_text_at_end_markers(
            merged,
            _VITAMIN_B12_DEFICIENCY_END_MARKERS,
        )
        if len(segments) != len(_VITAMIN_B12_DEFICIENCY_END_MARKERS) + 1:
            return chunks

        prevention = segments[-1]
        prevention_start = prevention.find(_VITAMIN_B12_DEFICIENCY_PREVENTION_HEADING)
        if prevention_start < 0:
            return chunks
        prevention = prevention[prevention_start:]
        prevention_end = prevention.find(_VITAMIN_B12_DEFICIENCY_PREVENTION_END)
        if prevention_end < 0:
            return chunks
        prevention = prevention[: prevention_end + len(_VITAMIN_B12_DEFICIENCY_PREVENTION_END)]
        segments[-1] = f"{segments[-2]} {prevention}".strip()
        segments.pop(-2)

        repaired: list[KnowledgeChunk] = []
        for content in segments:
            repaired.append(
                chunks[0].model_copy(
                    update={
                        "content": self._format_vitamin_b12_deficiency_heading(content),
                        "metadata": self._verified_span_metadata(
                            content=content,
                            chunks=chunks,
                        ),
                    }
                )
            )
        return repaired

    def _resegment_calcium_iron_absorption_review(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        """검수된 Calcium–Iron 종설의 제목·본문·결론 경계를 복원합니다."""
        merged = self._merge_verified_chunk_text(chunks)
        title = chunks[0].metadata.title
        title_start = merged.find(title)
        if title_start >= 0:
            merged = merged[title_start:]
        merged = re.sub(
            r"\bArticle to the Special Issue\b.*?(?=\bAbstract:|\bIntroduction\b)",
            "",
            merged,
            flags=re.DOTALL,
        )
        merged = re.sub(r"\bDOI\s+10\.1024/0300-9831/a000036\b.*?(?:Bern\b)?", "", merged)
        merged = _PARENTHETICAL_NUMERIC_CITATION_PATTERN.sub("", merged)
        merged = _BRACKETED_NUMERIC_CITATION_PATTERN.sub("", merged)
        references = re.search(r"(?im)^\s*References\b", merged)
        if references is not None:
            merged = merged[: references.start()]
        end = merged.find(_CALCIUM_IRON_ABSORPTION_REVIEW_END)
        if end >= 0:
            merged = merged[: end + len(_CALCIUM_IRON_ABSORPTION_REVIEW_END)]

        positions = sorted(
            {
                position
                for marker in _CALCIUM_IRON_ABSORPTION_REVIEW_BOUNDARIES
                if (position := merged.find(marker)) >= 0
            }
        )
        if not positions or positions[0] <= 0:
            return chunks
        positions.insert(0, 0)
        positions.append(len(merged))

        repaired: list[KnowledgeChunk] = []
        for start, stop in zip(positions, positions[1:], strict=False):
            content = merged[start:stop].strip()
            if not content:
                continue
            formatted_content = self._format_calcium_iron_absorption_heading(content, title=title)
            for bounded_content, _, _ in self._split_section_content(
                formatted_content,
                self.policy_for(KnowledgeDocumentType.RESEARCH_ARTICLE),
                document_type=KnowledgeDocumentType.RESEARCH_ARTICLE,
            ):
                repaired.append(
                    chunks[0].model_copy(
                        update={
                            "content": bounded_content,
                            "metadata": self._verified_span_metadata(content=bounded_content, chunks=chunks),
                        }
                    )
                )
        return repaired

    def _clean_calcium_iron_meta_analysis(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        """메타분석에서 preprint·저자·참고문헌만 제거하고 검수된 본문은 보존합니다."""
        cleaned: list[KnowledgeChunk] = []
        reached_references = False
        title = chunks[0].metadata.title
        for index, chunk in enumerate(chunks):
            if reached_references:
                continue
            content = chunk.content
            if index == 0:
                content = self._remove_meta_analysis_front_matter(content, title=title)
            references = re.search(r"(?im)^\s*References\b", content)
            if references is not None:
                content = content[: references.start()]
                reached_references = True
            content = _PARENTHETICAL_NUMERIC_CITATION_PATTERN.sub("", content)
            content = _BRACKETED_NUMERIC_CITATION_PATTERN.sub("", content)
            content = re.sub(r"[ \t]+", " ", content)
            content = re.sub(r" *\n *", "\n", content).strip()
            if content:
                cleaned.append(chunk.model_copy(update={"content": content}))
        return cleaned

    @staticmethod
    def _remove_meta_analysis_front_matter(
        content: str,
        *,
        title: str,
    ) -> str:
        title_start = content.find(title)
        if title_start >= 0:
            content = content[title_start:]
        abstract = re.search(r"\bAbstract\b", content)
        if abstract is None:
            return content
        title_prefix = content[: len(title)].strip() if content.startswith(title) else ""
        body = content[abstract.start() :]
        return f"{title_prefix}\n\n{body}".strip()

    def _clean_older_adult_supplement_interaction_review(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        """고령자 종설의 첫 청크에서 출판 메타데이터를 제거합니다."""
        cleaned = list(chunks)
        first = cleaned[0]
        title = first.metadata.title
        content = first.content
        title_start = content.find(title)
        if title_start >= 0:
            content = content[title_start:]
        abstract = re.search(r"\bAbstract\b", content)
        if abstract is not None:
            content = f"Open Access Review Article\n{title}\n\n{content[abstract.start() :]}"
        content = re.sub(r"\bReview began\b.*?(?=\bAbstract\b)", "", content, flags=re.DOTALL)
        content = re.sub(r"\bDOI:\s*\S+", "", content)
        content = re.sub(r"[ \t]+", " ", content)
        content = re.sub(r" *\n *", "\n", content).strip()
        cleaned[0] = first.model_copy(update={"content": content})
        return cleaned

    def _resegment_zinc_iron_status_study(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        """아연–철 연구에서 본문만 남기고 표·각주·참고문헌을 제외합니다."""
        text_chunks = [chunk for chunk in chunks if chunk.metadata.content_kind != KnowledgeContentKind.TABLE]
        if not text_chunks:
            return chunks
        merged = self._merge_verified_chunk_text(text_chunks)
        title = text_chunks[0].metadata.title
        title_start = merged.find(title)
        if title_start >= 0:
            merged = merged[title_start:]
        abstract = re.search(r"\bABSTRACT\b", merged)
        if abstract is not None:
            merged = f"{title}\n\n{merged[abstract.start() :]}"
        merged = re.sub(
            r"\b1\s+Presented in part at Experimental Biology 2000\..*?(?=\bSample collection\.)",
            "",
            merged,
            flags=re.DOTALL,
        )
        merged = re.sub(
            r"\b0022-3166/02\b.*?(?=\bSample collection\.)",
            "",
            merged,
            flags=re.DOTALL,
        )
        merged = re.sub(r"\b4\s+Abbreviations used:.*?(?=\bRESULTS\b)", "", merged, flags=re.DOTALL)
        merged = re.sub(r"\bTABLE\s+[123]\b.*?(?=\bDISCUSSION\b)", "", merged, flags=re.DOTALL)
        acknowledgment = re.search(r"\bACKNOWLEDGMENT\b", merged)
        if acknowledgment is not None:
            merged = merged[: acknowledgment.start()]
        end = merged.find(_ZINC_IRON_STATUS_STUDY_END)
        if end >= 0:
            merged = merged[: end + len(_ZINC_IRON_STATUS_STUDY_END)]
        merged = _PARENTHETICAL_NUMERIC_CITATION_PATTERN.sub("", merged)
        merged = _BRACKETED_NUMERIC_CITATION_PATTERN.sub("", merged)

        positions = sorted(
            {position for marker in _ZINC_IRON_STATUS_STUDY_BOUNDARIES if (position := merged.find(marker)) >= 0}
        )
        if not positions or positions[0] <= 0:
            return chunks
        positions.insert(0, 0)
        positions.append(len(merged))
        repaired: list[KnowledgeChunk] = []
        for start, stop in zip(positions, positions[1:], strict=False):
            content = merged[start:stop].strip()
            if not content:
                continue
            repaired.append(
                text_chunks[0].model_copy(
                    update={
                        "content": self._format_zinc_iron_study_heading(content),
                        "metadata": self._verified_span_metadata(content=content, chunks=text_chunks),
                    }
                )
            )
        return repaired

    def _clean_vitamin_c_copper_study(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        """비타민 C–구리 실험 논문의 쪽 번호·그림 캡션을 본문에서 제거합니다."""
        body_starts = (
            "Because the digestive system",
            "As an organ that stores urine",
            "Further analysis revealed",
            "We also observed the long-term effect",
            "3.2.",
            "3.3.",
            "3.4.",
            "Discussion",
            "Conclusions",
        )
        body_pattern = "|".join(re.escape(value) for value in body_starts)
        figure_caption = re.compile(
            rf"(?ms)^Figure\s+\d+\..*?(?=^(?:{body_pattern}))",
        )
        figure_continuation = re.compile(
            r"(?is)^(?:"
            r"of combined administration on colon length\."
            r"|the indicated concentrations of AA together with or without 1 mg/kg Cu\+"
            r"|of AA and Cu\+ on renal tubular cell death\."
            r"|methods section\. Data shown"
            r"|status and renal injury\."
            r").*"
        )
        inline_figure_caption = re.compile(
            r"(?ms)\n{2,}\s*(?:"
            r"on kidney size\."
            r"|AA \(1000 mg/kg\) plus Cu\+ \(1 mg/kg\)"
            r"|in vivo\."
            r").*$"
        )
        cleaned: list[KnowledgeChunk] = []
        for chunk in chunks:
            content = chunk.content
            content = re.sub(
                r"(?m)^Biomolecules\s+\d{4},\s+\d+,\s+\d+\s*\n\s*\d+\s+of\s+\d+\s*",
                "",
                content,
            )
            content = re.sub(r"(?m)^\s*2\s+2\s*$", "", content)
            content = re.sub(r"(?m)^\s*2\s+2\s+(?=\S)", "", content)
            content = figure_caption.sub("", content)
            content = inline_figure_caption.sub("", content)
            stripped_content = content.strip()
            if re.match(r"(?s)^Figure\s+\d+\..*$", stripped_content):
                continue
            if figure_continuation.match(stripped_content):
                continue
            content = re.sub(r"(?<![A-Za-z0-9])Cu\+(?![A-Za-z0-9+])", "Cu2+", content)
            content = re.sub(r"\bH\s+O\b", "H2O", content)
            content = re.sub(r"\n{3,}", "\n\n", content).strip()
            if content:
                cleaned.append(chunk.model_copy(update={"content": content}))
        return cleaned

    @staticmethod
    def _format_calcium_iron_absorption_heading(content: str, *, title: str) -> str:
        if content.startswith(f"{title} Abstract:"):
            return content.replace(f"{title} Abstract:", f"{title}\n\nAbstract:", 1)
        if content.startswith("Introduction") and len(content) > len("Introduction"):
            return f"Introduction\n{content[len('Introduction') :].strip()}"
        if content.startswith("Conclusions") and len(content) > len("Conclusions"):
            return f"Conclusions\n{content[len('Conclusions') :].strip()}"
        return content

    @staticmethod
    def _format_zinc_iron_study_heading(content: str) -> str:
        for heading in _ZINC_IRON_STATUS_STUDY_BOUNDARIES:
            if content.startswith(heading) and len(content) > len(heading):
                return f"{heading}\n{content[len(heading) :].strip()}"
        return content

    def _resegment_botanical_supplement_adverse_effects(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        text_chunks = [chunk for chunk in chunks if chunk.metadata.content_kind != KnowledgeContentKind.TABLE]
        table_chunks = [chunk for chunk in chunks if chunk.metadata.content_kind == KnowledgeContentKind.TABLE]
        if not text_chunks:
            return chunks

        first_marker = _BOTANICAL_SUPPLEMENT_ADVERSE_EFFECTS_END_MARKERS[0]
        first_marker_chunk_index = next(
            (index for index, chunk in enumerate(text_chunks) if first_marker in chunk.content),
            None,
        )
        if first_marker_chunk_index is None:
            return chunks

        prefix = self._merge_botanical_introduction_chunks(text_chunks[:first_marker_chunk_index])
        merged = self._merge_verified_chunk_text(text_chunks[first_marker_chunk_index:])
        merged = re.sub(r"transplanta-\s*tion", "transplantation", merged)
        merged = re.sub(r"predomi-\s*nant", "predominant", merged)
        merged = re.sub(r"\bobserved\s+\.", "observed.", merged)
        references_start = re.search(
            r"\bREFERENCES\b(?=\s+(?:\d+[.)]|remove\b))",
            merged,
        )
        if references_start is not None:
            merged = merged[: references_start.start()].strip()

        segments = self._split_merged_text_at_end_markers(
            merged,
            _BOTANICAL_SUPPLEMENT_ADVERSE_EFFECTS_END_MARKERS,
        )
        if len(segments) != len(_BOTANICAL_SUPPLEMENT_ADVERSE_EFFECTS_END_MARKERS) + 1:
            return chunks

        repaired = list(prefix)
        for content in segments:
            repaired.append(
                text_chunks[0].model_copy(
                    update={
                        "content": content,
                        "metadata": self._verified_span_metadata(
                            content=content,
                            chunks=text_chunks,
                        ),
                    }
                )
            )
        return [*repaired, *table_chunks]

    def _merge_botanical_introduction_chunks(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        merged: list[KnowledgeChunk] = []
        for chunk in chunks:
            if (
                merged
                and chunk.metadata.section_type == KnowledgeSectionType.INTRODUCTION
                and merged[-1].metadata.section_type == KnowledgeSectionType.INTRODUCTION
            ):
                content = self._merge_verified_chunk_text([merged[-1], chunk])
                merged[-1] = merged[-1].model_copy(
                    update={
                        "content": content,
                        "metadata": self._verified_span_metadata(
                            content=content,
                            chunks=[merged[-1], chunk],
                        ),
                    }
                )
                continue
            merged.append(chunk)
        return merged

    @staticmethod
    def _split_merged_text_at_end_markers(
        text: str,
        end_markers: tuple[str, ...],
    ) -> list[str]:
        segments: list[str] = []
        start = 0
        for marker in end_markers:
            marker_start = text.find(marker, start)
            if marker_start < 0:
                return []
            end = marker_start + len(marker)
            content = text[start:end].strip()
            if not content:
                return []
            segments.append(content)
            start = end
        tail = text[start:].strip()
        if tail:
            segments.append(tail)
        return segments

    @staticmethod
    def _format_vitamin_b12_deficiency_heading(content: str) -> str:
        title = "Vitamin B12 Deficiency"
        if content.startswith(f"{title} "):
            return f"{title}\n\n{content[len(title) :].strip()}"
        if content.startswith(_VITAMIN_B12_DEFICIENCY_PREVENTION_HEADING):
            body = content[len(_VITAMIN_B12_DEFICIENCY_PREVENTION_HEADING) :].strip()
            return f"{_VITAMIN_B12_DEFICIENCY_PREVENTION_HEADING}\n{body}"
        return content

    def _resegment_statins_vitamin_d_review(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        merged = self._merge_verified_chunk_text(chunks)
        abstract_start = merged.find("Abstract")
        if abstract_start >= 0:
            merged = f"{_STATINS_VITAMIN_D_REVIEW_TITLE} {merged[abstract_start:]}"
        conclusion_end = merged.find(_STATINS_VITAMIN_D_CONCLUSION_END)
        if conclusion_end >= 0:
            merged = merged[: conclusion_end + len(_STATINS_VITAMIN_D_CONCLUSION_END)]

        positions = sorted(
            {position for marker in _STATINS_VITAMIN_D_REVIEW_BOUNDARIES if (position := merged.find(marker)) >= 0}
        )
        if not positions:
            return chunks
        if positions[0] > 0:
            positions.insert(0, 0)
        positions.append(len(merged))

        repaired: list[KnowledgeChunk] = []
        for start, end in zip(positions, positions[1:], strict=False):
            content = merged[start:end].strip()
            if not content:
                continue
            metadata = self._verified_span_metadata(
                content=content,
                chunks=chunks,
            )
            verified_page_range = next(
                (
                    page_range
                    for prefix, page_range in _STATINS_VITAMIN_D_VERIFIED_PAGE_RANGES.items()
                    if content.startswith(prefix)
                ),
                None,
            )
            if verified_page_range is not None:
                metadata = metadata.model_copy(
                    update={
                        "page_start": verified_page_range[0],
                        "page_end": verified_page_range[1],
                    }
                )
            repaired.append(
                chunks[0].model_copy(
                    update={
                        "content": self._format_statins_vitamin_d_heading(content),
                        "metadata": metadata,
                    }
                )
            )
        return repaired

    def _resegment_primary_care_herb_drug_review(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        merged = self._merge_verified_chunk_text(chunks)
        merged = _PRIMARY_CARE_HERB_DRUG_NUMERIC_CITATION_PATTERN.sub("", merged)
        merged = re.sub(
            r"\bAcross[-‐–—]sectional\b",
            "A cross-sectional",
            merged,
        )
        merged = _PRIMARY_CARE_HERB_DRUG_FIGURE_PATTERN.sub(" ", merged)
        end = merged.find(_PRIMARY_CARE_HERB_DRUG_REVIEW_END)
        if end >= 0:
            merged = merged[: end + len(_PRIMARY_CARE_HERB_DRUG_REVIEW_END)]

        positions = sorted(
            {position for marker in _PRIMARY_CARE_HERB_DRUG_REVIEW_BOUNDARIES if (position := merged.find(marker)) >= 0}
        )
        if not positions or positions[0] > 0:
            positions.insert(0, 0)
        positions.append(len(merged))

        repaired: list[KnowledgeChunk] = []
        for start, stop in zip(positions, positions[1:], strict=False):
            content = merged[start:stop].strip()
            if not content:
                continue
            repaired.append(
                chunks[0].model_copy(
                    update={
                        "content": self._format_primary_care_herb_drug_heading(content),
                        "metadata": self._verified_span_metadata(
                            content=content,
                            chunks=chunks,
                        ),
                    }
                )
            )
        return repaired

    def _resegment_st_johns_wort_review(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        merged = self._merge_verified_chunk_text(chunks)
        title_start = merged.find(_ST_JOHNS_WORT_REVIEW_TITLE)
        if title_start >= 0:
            merged = merged[title_start:]
        merged = _ST_JOHNS_WORT_TABLE_PATTERN.sub(" ", merged)
        end = merged.find(_ST_JOHNS_WORT_REVIEW_END)
        if end >= 0:
            end_offset = end + len(_ST_JOHNS_WORT_REVIEW_END)
            has_terminal_period = merged[end_offset : end_offset + 1] == "."
            merged = merged[:end_offset]
            if has_terminal_period:
                merged += "."

        positions = sorted(
            {position for marker in _ST_JOHNS_WORT_REVIEW_BOUNDARIES if (position := merged.find(marker)) >= 0}
        )
        if not positions or positions[0] > 0:
            positions.insert(0, 0)
        positions.append(len(merged))

        repaired: list[KnowledgeChunk] = []
        for start, stop in zip(positions, positions[1:], strict=False):
            content = merged[start:stop].strip()
            if not content:
                continue
            metadata = self._verified_span_metadata(
                content=content,
                chunks=chunks,
            )
            verified_page_range = next(
                (
                    page_range
                    for prefix, page_range in _ST_JOHNS_WORT_VERIFIED_PAGE_RANGES.items()
                    if content.startswith(prefix)
                ),
                None,
            )
            if verified_page_range is not None:
                metadata = metadata.model_copy(
                    update={
                        "page_start": verified_page_range[0],
                        "page_end": verified_page_range[1],
                    }
                )
            repaired.append(
                chunks[0].model_copy(
                    update={
                        "content": self._format_st_johns_wort_review_heading(content),
                        "metadata": metadata,
                    }
                )
            )
        return repaired

    @staticmethod
    def _format_st_johns_wort_review_heading(content: str) -> str:
        if content.startswith(_ST_JOHNS_WORT_REVIEW_TITLE):
            body = content[len(_ST_JOHNS_WORT_REVIEW_TITLE) :].strip()
            if body.startswith("Abstract"):
                body = f"Abstract\n{body[len('Abstract') :].strip()}"
            return f"{_ST_JOHNS_WORT_REVIEW_TITLE}\n\n{body}"
        for heading in _ST_JOHNS_WORT_REVIEW_BOUNDARIES:
            if content.startswith(heading) and len(content) > len(heading):
                body = content[len(heading) :].strip()
                if heading == "What is already known on this topic":
                    body = re.sub(
                        r"\s+What this study adds\s+",
                        "\n\nWhat this study adds\n",
                        body,
                        count=1,
                    )
                return f"{heading}\n{body}"
        return content

    @staticmethod
    def _format_primary_care_herb_drug_heading(content: str) -> str:
        title = "Drug–herb interactions: a challenge and clinical concern in primary healthcare"
        if content.startswith(title):
            body = content[len(title) :].strip()
            body = re.sub(r"\s+KEYWORDS\s+", "\n\nKEYWORDS\n", body, count=1)
            return f"{title}\n\n{body}"
        for heading in _PRIMARY_CARE_HERB_DRUG_REVIEW_BOUNDARIES:
            if content.startswith(heading) and len(content) > len(heading):
                return f"{heading}\n{content[len(heading) :].strip()}"
        return content

    def _resegment_levothyroxine_calcium_review(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        merged = self._merge_verified_chunk_text(chunks)
        merged = _PARENTHETICAL_NUMERIC_CITATION_PATTERN.sub("", merged)
        merged = _INLINE_FIGURE_REFERENCE_PATTERN.sub("", merged)
        end = merged.find(_LEVOTHYROXINE_CALCIUM_REVIEW_END)
        if end >= 0:
            merged = merged[: end + len(_LEVOTHYROXINE_CALCIUM_REVIEW_END)]

        positions = {
            position for marker in _LEVOTHYROXINE_CALCIUM_REVIEW_BOUNDARIES if (position := merged.find(marker)) >= 0
        }
        statistics_start = merged.find("Statistics")
        if statistics_start >= 0:
            main_results = re.search(
                r"\bResults\b(?!:)",
                merged[statistics_start + len("Statistics") :],
            )
            if main_results is not None:
                positions.add(statistics_start + len("Statistics") + main_results.start())
        ordered_positions = sorted(positions)
        if not ordered_positions or ordered_positions[0] > 0:
            ordered_positions.insert(0, 0)
        ordered_positions.append(len(merged))

        repaired: list[KnowledgeChunk] = []
        for start, stop in zip(ordered_positions, ordered_positions[1:], strict=False):
            content = merged[start:stop].strip()
            if not content:
                continue
            repaired.append(
                chunks[0].model_copy(
                    update={
                        "content": self._format_levothyroxine_calcium_heading(content),
                        "metadata": self._verified_span_metadata(
                            content=content,
                            chunks=chunks,
                        ),
                    }
                )
            )
        return repaired

    @staticmethod
    def _format_levothyroxine_calcium_heading(content: str) -> str:
        title = "Absorption of Levothyroxine When Coadministered with Various Calcium Formulations"
        if content.startswith(title):
            content = content.replace(f"{title} Background:", f"{title}\n\nBackground:", 1)
            content = content.replace(" Materials and Methods:", "\n\nMaterials and Methods:", 1)
            return content
        if content.startswith("Materials and Methods Subjects"):
            return content.replace("Materials and Methods Subjects", "Materials and Methods\nSubjects", 1)
        headings = (
            "Results:",
            "Conclusions:",
            "Introduction",
            "Study design",
            "Assays",
            "Statistics",
            "Results",
            "Discussion",
            "Our study also indicates that the effects",
            "One possible limitation of this study",
        )
        for heading in headings:
            if content.startswith(heading) and len(content) > len(heading):
                return f"{heading}\n{content[len(heading) :].strip()}"
        return content

    @staticmethod
    def _format_statins_vitamin_d_heading(content: str) -> str:
        if content.startswith(f"{_STATINS_VITAMIN_D_REVIEW_TITLE} ") and " Abstract " in content:
            before_abstract, abstract = content.split(" Abstract ", maxsplit=1)
            abstract = re.sub(r"\s+Keywords:\s*", "\n\nKeywords: ", abstract, count=1)
            return f"{before_abstract.strip()}\n\nAbstract\n{abstract.strip()}"

        nested_headings = (
            "2.1. Shared Precursors and Metabolic Pathways",
            "5.1. Vitamin D Levels and Cardiovascular Risk",
            "6.1. Summary of Key Findings",
        )
        for nested in nested_headings:
            content = content.replace(f" {nested} ", f"\n{nested}\n", 1)

        for heading in _STATINS_VITAMIN_D_REVIEW_BOUNDARIES:
            if content.startswith(heading) and len(content) > len(heading):
                return f"{heading}\n{content[len(heading) :].strip()}"
        return content

    def _resegment_drug_vitamin_d_review(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        merged = self._merge_verified_chunk_text(chunks)
        merged = re.sub(r"Histamine H2\s+-receptor", "Histamine H2-receptor", merged)
        positions = sorted(
            {position for marker in _DRUG_VITAMIN_D_REVIEW_BOUNDARIES if (position := merged.find(marker)) >= 0}
        )
        if not positions:
            return chunks
        if positions[0] > 0:
            positions.insert(0, 0)
        positions.append(len(merged))

        repaired: list[KnowledgeChunk] = []
        for start, end in zip(positions, positions[1:], strict=False):
            content = merged[start:end].strip()
            if not content:
                continue
            metadata = self._verified_span_metadata(
                content=content,
                chunks=chunks,
            )
            verified_page_range = self._drug_vitamin_d_verified_page_range(content)
            if verified_page_range is not None:
                metadata = metadata.model_copy(
                    update={
                        "page_start": verified_page_range[0],
                        "page_end": verified_page_range[1],
                    }
                )
            repaired.append(
                chunks[0].model_copy(
                    update={
                        "content": self._format_drug_vitamin_d_heading(content),
                        "metadata": metadata,
                    }
                )
            )
        return repaired

    @staticmethod
    def _drug_vitamin_d_verified_page_range(
        content: str,
    ) -> tuple[int, int] | None:
        return next(
            (
                page_range
                for prefix, page_range in _DRUG_VITAMIN_D_VERIFIED_PAGE_RANGES.items()
                if content.startswith(prefix)
            ),
            None,
        )

    @staticmethod
    def _merge_verified_chunk_text(chunks: list[KnowledgeChunk]) -> str:
        merged_words: list[str] = []
        for chunk in chunks:
            words = chunk.content.split()
            overlap = 0
            max_overlap = min(len(merged_words), len(words), 250)
            for size in range(max_overlap, 2, -1):
                if merged_words[-size:] == words[:size]:
                    overlap = size
                    break
            merged_words.extend(words[overlap:])
        return " ".join(merged_words)

    @staticmethod
    def _verified_span_metadata(
        *,
        content: str,
        chunks: list[KnowledgeChunk],
    ) -> KnowledgeChunkMetadata:
        words = content.split()
        start_probe = " ".join(words[: min(8, len(words))])
        end_probe = " ".join(words[-min(8, len(words)) :])
        normalized_chunks = [
            (
                chunk,
                re.sub(
                    r"Histamine H2\s+-receptor",
                    "Histamine H2-receptor",
                    " ".join(chunk.content.split()),
                ),
            )
            for chunk in chunks
        ]
        start_chunk = next(
            (chunk for chunk, normalized in normalized_chunks if start_probe in normalized),
            chunks[0],
        )
        end_chunk = next(
            (chunk for chunk, normalized in reversed(normalized_chunks) if end_probe in normalized),
            start_chunk,
        )
        return start_chunk.metadata.model_copy(
            update={
                "page_start": start_chunk.metadata.page_start,
                "page_end": max(
                    start_chunk.metadata.page_end,
                    end_chunk.metadata.page_end,
                ),
            }
        )

    @staticmethod
    def _format_drug_vitamin_d_heading(content: str) -> str:
        title = "Drug-vitamin D interactions: A systematic review of the literature"
        abstract_prefix = f"{title} Abstract "
        if content.startswith(abstract_prefix):
            return f"{title}\n\nAbstract\n{content[len(abstract_prefix) :].strip()}"

        compound_headings = {
            "Methods Study selection": "Methods\nStudy selection",
            "Drugs that interfere with vitamin D metabolism Statins": (
                "Drugs that interfere with vitamin D metabolism\nStatins"
            ),
        }
        for flat, rendered in compound_headings.items():
            if content.startswith(flat):
                return f"{rendered}\n{content[len(flat) :].strip()}".strip()

        heading_markers = {
            marker
            for marker in _DRUG_VITAMIN_D_REVIEW_BOUNDARIES
            if marker not in compound_headings
            and marker != "The metabolically active 1,25(OH)2 D form"
            and marker not in _DRUG_VITAMIN_D_DISCUSSION_BOUNDARIES
        }
        for heading in heading_markers:
            if content.startswith(heading) and len(content) > len(heading):
                return f"{heading}\n{content[len(heading) :].strip()}"
        return content

    @staticmethod
    def _repair_warfarin_review_discussion_boundary(
        chunks: list[KnowledgeChunk],
    ) -> None:
        boundary = "multiple active ingredients listed in the current review to avoid the risk of interaction."
        continuation = "Concurrent use of other antiplatelet or anticoagulants"
        for index in range(len(chunks) - 1):
            current = chunks[index]
            boundary_index = current.content.find(boundary)
            if boundary_index < 0:
                continue
            following = chunks[index + 1]
            continuation_index = following.content.find(continuation)
            if continuation_index < 0:
                continue
            chunks[index] = current.model_copy(
                update={"content": current.content[: boundary_index + len(boundary)].rstrip()}
            )
            chunks[index + 1] = following.model_copy(
                update={"content": following.content[continuation_index:].lstrip()}
            )
            return

    @staticmethod
    def _move_aspirin_review_abstract_sentence(
        chunks: list[KnowledgeChunk],
    ) -> None:
        sentence = "drug–nutrient interactions that alter micronutritional status."
        for index in range(len(chunks) - 1):
            current = chunks[index]
            following = chunks[index + 1]
            if not current.content.rstrip().endswith("Our article reviews the"):
                continue
            if not following.content.lstrip().startswith(sentence):
                continue
            chunks[index] = current.model_copy(update={"content": f"{current.content.rstrip()} {sentence}"})
            chunks[index + 1] = following.model_copy(
                update={"content": following.content.lstrip()[len(sentence) :].strip()}
            )
            return

    @staticmethod
    def _split_aspirin_review_pantothenic_acid(
        chunks: list[KnowledgeChunk],
    ) -> None:
        heading = "\nPantothenic Acid (B5)\n"
        completion = (
            "supplement. In a human study on 31 diabetic patients with "
            "hyperlipidemia, pantethine had mild antiplatelet aggregation "
            "properties."
        )
        for index, chunk in enumerate(chunks):
            if heading not in chunk.content:
                continue
            before, after = chunk.content.split(heading, maxsplit=1)
            if re.search(r"(?:It|Pantethine) is used as a$", after.rstrip()):
                after = f"{after.rstrip()} {completion}"
            chunks[index] = chunk.model_copy(update={"content": before.strip()})
            chunks.insert(
                index + 1,
                chunk.model_copy(update={"content": f"Pantothenic Acid (B5)\n{after.strip()}"}),
            )
            return

    @staticmethod
    def _repair_aspirin_review_vitamin_k_boundary(
        chunks: list[KnowledgeChunk],
    ) -> None:
        heading = "K Vitamin\n"
        for index in range(len(chunks) - 1):
            chunk = chunks[index]
            heading_index = chunk.content.find(f"\n{heading}")
            if heading_index < 0:
                if chunk.content.startswith(heading):
                    chunks[index] = chunk.model_copy(
                        update={
                            "content": re.sub(
                                r"factors II, VII, IX, and\s+X\. It is expected",
                                "factors II, VII, IX, and X. It is expected",
                                chunk.content,
                            )
                        }
                    )
                continue

            vitamin_k_content = re.sub(
                r"factors II, VII, IX, and\s+X\. It is expected",
                "factors II, VII, IX, and X. It is expected",
                chunk.content[heading_index + 1 :],
            )
            chunks[index] = chunk.model_copy(update={"content": chunk.content[:heading_index].rstrip()})
            following = chunks[index + 1]
            chunks[index + 1] = following.model_copy(
                update={
                    "content": (f"{vitamin_k_content.rstrip()} {following.content.lstrip()}"),
                    "metadata": chunk.metadata.model_copy(
                        update={
                            "page_end": max(
                                chunk.metadata.page_end,
                                following.metadata.page_end,
                            )
                        }
                    ),
                }
            )
            return

    @staticmethod
    def _repair_aspirin_review_discussion_overlap(
        chunks: list[KnowledgeChunk],
    ) -> None:
        duplicated_prefix = re.compile(
            r"^developing countries\. DNIs and polypharmacy theoretically "
            r"increase the risks of\s+micronutritional deficiencies, enhancing "
            r"the risk of adverse effect on chronically ill people\s+with impaired "
            r"nutritional status\.\s*",
        )
        marker = "Karadima et al."
        for index, chunk in enumerate(chunks):
            content = duplicated_prefix.sub("", chunk.content.strip())
            first = content.find(marker)
            second = content.find(marker, first + len(marker)) if first >= 0 else -1
            if second >= 0 and content[:second].rstrip().endswith("functionality of"):
                repeated = content[second:]
                continuation = repeated.find("functionality of systems")
                if continuation >= 0:
                    suffix = repeated[continuation + len("functionality of") :]
                    content = f"{content[:second].rstrip()} {suffix.lstrip()}"
            content = re.sub(r"functionality of\s+systems", "functionality of systems", content)
            if content != chunk.content:
                chunks[index] = chunk.model_copy(update={"content": content})

    @staticmethod
    def _repair_aspirin_review_table_chunk(
        chunk: KnowledgeChunk,
    ) -> KnowledgeChunk:
        lines: list[str] = []
        previous_iron_effect = ""
        previous_iron_number = ""
        for line in chunk.content.splitlines():
            if line.startswith("Nutriment=ascorbic acid (C) |") and (
                "↓ C intragastric concentration ↑ urinary excretion" in line
            ):
                lines.extend(KnowledgeSplitter._aspirin_vitamin_c_rows())
                continue
            if line.startswith("Nutriment=folate (B9) |") and ("↑ clearance of S-7-hydroxywarfarin" in line):
                lines.extend(KnowledgeSplitter._warfarin_folate_rows())
                continue
            if line.startswith("Nutriment=iron |"):
                line, previous_iron_effect, previous_iron_number = KnowledgeSplitter._inherit_aspirin_iron_fields(
                    line,
                    previous_effect=previous_iron_effect,
                    previous_number=previous_iron_number,
                )
            lines.append(line)
        return chunk.model_copy(update={"content": "\n".join(lines)})

    @staticmethod
    def _inherit_aspirin_iron_fields(
        line: str,
        *,
        previous_effect: str,
        previous_number: str,
    ) -> tuple[str, str, str]:
        effect = KnowledgeSplitter._table_field(
            line,
            "Effect on Nutrient Status or Function",
        )
        number = KnowledgeSplitter._table_field(line, "Number")
        resolved_effect = effect or previous_effect
        resolved_number = number or previous_number

        if not effect and resolved_effect:
            field = f"Effect on Nutrient Status or Function={resolved_effect}"
            if "Effect on Nutrient Status or Function=" in line:
                line = line.replace(
                    "Effect on Nutrient Status or Function= |",
                    f"{field} |",
                )
            else:
                line = line.replace(" | ", f" | {field} | ", 1)
        if not number and resolved_number:
            field = f"Number={resolved_number}"
            if "Number=" in line:
                line = line.replace("Number= |", f"{field} |")
            elif " | Study Design=" in line:
                line = line.replace(
                    " | Study Design=",
                    f" | {field} | Study Design=",
                )
        return line, resolved_effect, resolved_number

    def _regroup_verified_table_chunks(
        self,
        chunks: list[KnowledgeChunk],
    ) -> list[KnowledgeChunk]:
        regrouped: list[KnowledgeChunk] = []
        for chunk in chunks:
            if chunk.metadata.content_kind != KnowledgeContentKind.TABLE:
                regrouped.append(chunk)
                continue
            policy = _POLICIES[chunk.metadata.document_type]
            regrouped.extend(
                chunk.model_copy(update={"content": content})
                for content in self._group_table_rows(chunk.content, policy)
            )

        table_sequences: dict[str, int] = {}
        sequenced: list[KnowledgeChunk] = []
        for chunk in regrouped:
            table_group_id = chunk.metadata.table_group_id
            if not table_group_id:
                sequenced.append(chunk)
                continue
            sequence = table_sequences.get(table_group_id, 0)
            sequenced.append(
                chunk.model_copy(update={"metadata": chunk.metadata.model_copy(update={"table_sequence": sequence})})
            )
            table_sequences[table_group_id] = sequence + 1
        return sequenced

    @staticmethod
    def _table_field(line: str, name: str) -> str:
        match = re.search(rf"(?:^| \| ){re.escape(name)}=(.*?)(?= \| |$)", line)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _aspirin_vitamin_c_rows() -> list[str]:
        prefix = "Nutriment=ascorbic acid (C)"
        return [
            f"{prefix} | Effect on Nutrient Status or Function=↓ C intragastric concentration | Number=1 | Study Design=interventional—randomized, double-blind, parallel group | Number of Patients=45 | Dosage=3 × 80 mg ASA for 6 days | Result=↓ gastric mucosa concentration per 10%",
            f"{prefix} | Effect on Nutrient Status or Function=↑ urinary excretion | Number=1 | Study Design=case report | Number of Patients=3 | Dosage=162 mg ASA 2 times at 3 days interval | Result=↑ urinary excretion",
            f"{prefix} | Effect on Nutrient Status or Function=↓ C leukocyte concentration | Number=1 | Study Design=interventional | Number of Patients=10 | Dosage=600 mg ASA, 500 mg C | Result=↓ C leukocyte concentration by 114%",
        ]

    @staticmethod
    def _warfarin_folate_rows() -> list[str]:
        prefix = "Nutriment=folate (B9)"
        return [
            f"{prefix} | Effect on Nutrient Status or Function=no association with bleeding | Number=1 | Study Design=longitudinal cohort | Number of Patients=719 | Dosage=86% patients in INR 2.0–3.5 | Result=no association",
            f"{prefix} | Effect on Nutrient Status or Function=↑ clearance of S-7-hydroxywarfarin | Number=1 | Study Design=interventional | Number of Patients=24 | Dosage=5 mg/day B9 supplementation | Result=non significant changes in dose and INR",
            f"{prefix} | Effect on Nutrient Status or Function=dietary-induced Folate deficiency | Number=1 | Study Design=observational | Number of Patients=114 | Dosage=dose unavailable | Result=impaired folate status in as little as 6 months",
        ]

    def _rebuild_verified_chunk(
        self,
        chunk: KnowledgeChunk,
        chunk_index: int,
    ) -> KnowledgeChunk:
        content = chunk.content.strip()
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        metadata = chunk.metadata.model_copy(
            update={
                "chunk_index": chunk_index,
                "content_hash": content_hash,
            }
        )
        chunk_key = "|".join(
            [
                metadata.document_id,
                metadata.section_type.value,
                str(metadata.page_start),
                str(metadata.page_end),
                str(chunk_index),
                content_hash,
            ]
        )
        return KnowledgeChunk(
            chunk_id=hashlib.sha256(chunk_key.encode("utf-8")).hexdigest(),
            content=content,
            embedding_text=self._build_embedding_text(
                content=content,
                metadata=metadata,
            ),
            token_count=self._token_counter.count(content),
            metadata=metadata,
        )

    @staticmethod
    def _should_skip_section(
        section: KnowledgeSection,
        *,
        document_type: KnowledgeDocumentType,
    ) -> bool:
        if section.section_type == KnowledgeSectionType.REFERENCES:
            return True
        if document_type == KnowledgeDocumentType.REGULATORY_DRUG_LABEL and section.section_title == "10 OVERDOSAGE":
            return True
        return document_type == KnowledgeDocumentType.SUPPLEMENT_CODE and section.section_type in {
            KnowledgeSectionType.STANDARD,
            KnowledgeSectionType.TEST_METHOD,
        }

    def _split_block_pages(
        self,
        pages: list[KnowledgePage],
        *,
        verified_section_headings: list[str] | None = None,
    ) -> list[KnowledgeChunk]:
        text_pages: list[KnowledgePage] = []
        for page in pages:
            text_blocks = [
                block.content
                for block in sorted(
                    page.blocks,
                    key=lambda item: item.order,
                )
                if block.kind == KnowledgeContentKind.TEXT
            ]
            text_content = ""
            for block_content in text_blocks:
                if text_content:
                    text_content += self._page_separator(
                        text_content,
                        block_content,
                    )
                text_content += block_content
            text_content = text_content.strip()
            if text_content:
                text_pages.append(
                    page.model_copy(
                        update={
                            "content": text_content,
                            "blocks": [],
                        }
                    )
                )

        chunks = (
            self.split(
                text_pages,
                verified_section_headings=verified_section_headings,
            )
            if text_pages
            else []
        )
        metadata = pages[0].metadata
        policy = _POLICIES[metadata.document_type]
        table_sequences: dict[str, int] = {}
        for page in pages:
            for block in sorted(
                page.blocks,
                key=lambda item: item.order,
            ):
                if block.kind != KnowledgeContentKind.TABLE:
                    continue
                table_group_id = self._table_group_id(
                    document_id=metadata.document_id,
                    table_title=block.table_title,
                )
                for table_content in self._group_table_rows(
                    block.content,
                    policy,
                ):
                    section = KnowledgeSection(
                        content=table_content,
                        section_type=self._table_section_type(
                            "\n".join(
                                filter(
                                    None,
                                    [
                                        block.table_title,
                                        *block.table_super_headers,
                                        table_content,
                                    ],
                                )
                            ),
                            metadata,
                        ),
                        section_title=block.table_title or "표",
                        page_start=page.page_number,
                        page_end=page.page_number,
                        source_start=0,
                        source_end=len(table_content),
                    )
                    chunks.append(
                        self._build_chunk(
                            content=table_content,
                            section=section,
                            chunk_index=len(chunks),
                            metadata=metadata,
                            content_kind=KnowledgeContentKind.TABLE,
                            table_title=block.table_title,
                            table_super_headers=block.table_super_headers,
                            table_group_id=table_group_id,
                            table_sequence=(table_sequences.get(table_group_id, 0) if table_group_id else None),
                        )
                    )
                    if table_group_id:
                        table_sequences[table_group_id] = table_sequences.get(table_group_id, 0) + 1
        return chunks

    @staticmethod
    def _table_group_id(
        *,
        document_id: str,
        table_title: str | None,
    ) -> str | None:
        if not table_title:
            return None
        key = f"{document_id}|{table_title.strip().casefold()}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _group_table_rows(
        self,
        content: str,
        policy: ChunkingPolicy,
    ) -> list[str]:
        rows = [row.strip() for row in content.splitlines() if row.strip()]
        groups: list[str] = []
        current_rows: list[str] = []
        for row in rows:
            candidate = "\n".join([*current_rows, row])
            if current_rows and self._token_counter.count(candidate) > policy.hard_max_tokens:
                groups.append("\n".join(current_rows))
                current_rows = [row]
            else:
                current_rows.append(row)
        if current_rows:
            groups.append("\n".join(current_rows))
        return groups

    @staticmethod
    def _table_section_type(
        content: str,
        metadata,
    ) -> KnowledgeSectionType:
        if metadata.interaction_type or re.search(
            r"(?i)interaction|\bDNIs?\b|상호작용",
            content,
        ):
            return KnowledgeSectionType.INTERACTION
        if re.search(r"(?i)contraindicat|금기", content):
            return KnowledgeSectionType.CAUTION
        if re.search(r"(?i)adverse|부작용|이상사례", content):
            return KnowledgeSectionType.ADVERSE_EVENT
        if re.search(r"(?i)dosage|dose|용량|섭취량", content):
            return KnowledgeSectionType.DAILY_INTAKE
        return KnowledgeSectionType.OTHER

    @staticmethod
    def _drop_publication_front_matter(
        sections: list[KnowledgeSection],
        document_type: KnowledgeDocumentType,
    ) -> list[KnowledgeSection]:
        if (
            document_type != KnowledgeDocumentType.RESEARCH_ARTICLE
            or len(sections) < 2
            or sections[0].section_type != KnowledgeSectionType.OTHER
        ):
            return sections
        front_matter = sections[0].content
        if not re.search(
            r"(?im)^[ \t]*(?:[*†‡]\s*)?"
            r"(?:Citation|Copyright|Correspondence|Received|Published):",
            front_matter,
        ):
            return sections
        if sections[1].section_type not in {
            KnowledgeSectionType.SUMMARY,
            KnowledgeSectionType.INTRODUCTION,
        }:
            return sections
        return sections[1:]

    @staticmethod
    def _has_meaningful_body(section: KnowledgeSection) -> bool:
        return KnowledgeSplitter._has_meaningful_text(
            section.content,
            section.section_title,
        )

    @staticmethod
    def _has_meaningful_text(
        content: str,
        section_title: str | None,
    ) -> bool:
        body = content
        if section_title:
            body = re.sub(
                rf"^\s*{re.escape(section_title)}",
                "",
                body,
                count=1,
                flags=re.IGNORECASE,
            )
        meaningful_characters = re.findall(r"[A-Za-z0-9가-힣]", body)
        return len(meaningful_characters) >= 2

    def _merge_leading_context(
        self,
        sections: list[KnowledgeSection],
        policy: ChunkingPolicy,
    ) -> list[KnowledgeSection]:
        if len(sections) < 2:
            return sections

        leading, following = sections[0], sections[1]
        if (
            leading.section_type != KnowledgeSectionType.OTHER
            or self._token_counter.count(leading.content) >= policy.target_min_tokens
        ):
            return sections

        merged_content = f"{leading.content}\n\n{following.content}"
        if self._token_counter.count(merged_content) > policy.hard_max_tokens:
            return sections

        merged = following.model_copy(
            update={
                "content": merged_content,
                "page_start": min(leading.page_start, following.page_start),
                "source_start": leading.source_start,
                "source_end": following.source_end,
            }
        )
        return [merged, *sections[2:]]

    @staticmethod
    def _merge_heading_only_sections(
        sections: list[KnowledgeSection],
    ) -> list[KnowledgeSection]:
        if len(sections) < 2:
            return sections

        merged: list[KnowledgeSection] = []
        pending_headings: list[KnowledgeSection] = []
        for section in sections:
            if KnowledgeSplitter._is_heading_only_section(section):
                pending_headings.append(section)
                continue

            if pending_headings:
                prefix = "\n".join(heading.content for heading in pending_headings)
                first_heading = pending_headings[0]
                section = section.model_copy(
                    update={
                        "content": f"{prefix}\n{section.content}",
                        "page_start": min(
                            first_heading.page_start,
                            section.page_start,
                        ),
                        "source_start": first_heading.source_start,
                    }
                )
                pending_headings.clear()
            merged.append(section)

        merged.extend(pending_headings)
        return merged

    @staticmethod
    def _is_heading_only_section(section: KnowledgeSection) -> bool:
        if not section.section_title:
            return False
        body = re.sub(
            rf"^\s*(?:\d+(?:\.\d+)*\.?(?:\s*\|\s*|\s+))?"
            rf"{re.escape(section.section_title)}",
            "",
            section.content,
            count=1,
            flags=re.IGNORECASE,
        )
        return re.search(r"[A-Za-z0-9가-힣]", body) is None

    @staticmethod
    def policy_for(document_type: KnowledgeDocumentType) -> ChunkingPolicy:
        return _POLICIES[document_type]

    def _split_sections(
        self,
        pages: list[KnowledgePage],
        *,
        verified_section_headings: list[str] | None = None,
    ) -> tuple[list[KnowledgeSection], list[tuple[int, int, int]]]:
        metadata = pages[0].metadata
        if metadata.document_type == KnowledgeDocumentType.SUPPLEMENT_CODE:
            supplement_sections, supplement_page_ranges = self._supplement_code_parser.parse(pages)
            if supplement_sections:
                return supplement_sections, supplement_page_ranges
        headings: dict[str, KnowledgeSectionType | None] = dict(_HEADINGS.get(metadata.document_type, {}))
        headings.update({heading: None for heading in verified_section_headings or []})
        combined, page_ranges = self._combine_pages(pages)
        combined = self._truncate_document_back_matter(
            combined,
            metadata.document_type,
        )
        matches = self._find_heading_matches(
            combined,
            headings,
            document_type=metadata.document_type,
            attached_body_headings=_ATTACHED_BODY_HEADINGS_BY_SOURCE.get(
                metadata.source_id,
                frozenset(),
            ),
        )
        matches = self._truncate_after_references(matches)

        if not matches:
            content = combined.strip()
            source_start = len(combined) - len(combined.lstrip())
            return [
                KnowledgeSection(
                    content=content,
                    section_type=KnowledgeSectionType.OTHER,
                    page_start=pages[0].page_number,
                    page_end=pages[-1].page_number,
                    source_start=source_start,
                    source_end=source_start + len(content),
                )
            ], page_ranges

        boundaries = [(0, None, KnowledgeSectionType.OTHER), *matches]
        sections: list[KnowledgeSection] = []

        for index, (start, title, section_type) in enumerate(boundaries):
            end = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(combined)
            raw_content = combined[start:end]
            content = self._clean_section_content(
                raw_content.strip(),
                title=title,
            )
            if not content:
                continue
            if self._is_adverse_case_summary_context(
                content,
                document_type=metadata.document_type,
                section_type=section_type,
            ):
                section_type = KnowledgeSectionType.CASE_SUMMARY
                title = "환자 정보"
            source_start = start + len(raw_content) - len(raw_content.lstrip())
            source_end = source_start + len(content)
            page_start, page_end = self._page_range_for(
                source_start,
                source_end,
                page_ranges,
            )
            sections.append(
                KnowledgeSection(
                    content=content,
                    section_type=section_type,
                    section_title=title,
                    page_start=page_start,
                    page_end=page_end,
                    source_start=source_start,
                    source_end=source_end,
                )
            )

        return sections, page_ranges

    @staticmethod
    def _is_adverse_case_summary_context(
        content: str,
        *,
        document_type: KnowledgeDocumentType,
        section_type: KnowledgeSectionType,
    ) -> bool:
        if document_type != KnowledgeDocumentType.ADVERSE_CASE_REPORT or section_type != KnowledgeSectionType.OTHER:
            return False
        return sum(bool(re.search(pattern, content)) for pattern in _ADVERSE_CASE_SUMMARY_FIELDS) >= 2

    @staticmethod
    def _truncate_document_back_matter(
        content: str,
        document_type: KnowledgeDocumentType,
    ) -> str:
        if document_type == KnowledgeDocumentType.REGULATORY_DRUG_LABEL:
            marker = re.search(
                r"(?im)^\s*Manufactured and Distributed by:\s*",
                content,
            )
            return content[: marker.start()].rstrip() if marker else content

        if document_type != KnowledgeDocumentType.RESEARCH_ARTICLE:
            return content

        marker = re.search(
            r"(?im)^\s*(?:Abbreviations|Data Sharing Statement|"
            r"Author Contributions|Funding|Acknowledgments|"
            r"Conflicts? of Interest|Disclosure)\s*:?[^\n]*$",
            content,
        )
        if marker and marker.start() >= len(content) * 0.25:
            return content[: marker.start()].rstrip()
        return content

    @staticmethod
    def _clean_section_content(
        content: str,
        *,
        title: str | None,
    ) -> str:
        if not title:
            return content
        lines = content.splitlines()
        if not lines:
            return content
        lines[0] = re.sub(
            rf"^({re.escape(title)})\s*[-–—\u00ad]+\s*$",
            r"\1",
            lines[0],
            flags=re.IGNORECASE,
        )
        lines = [line for line in lines if re.fullmatch(r"\s*[-–—\u00ad]{4,}\s*", line) is None]
        return "\n".join(lines).strip()

    @staticmethod
    def _truncate_after_references(
        matches: list[tuple[int, str, KnowledgeSectionType]],
    ) -> list[tuple[int, str, KnowledgeSectionType]]:
        for index, (_, _, section_type) in enumerate(matches):
            if section_type == KnowledgeSectionType.REFERENCES:
                return matches[: index + 1]
        return matches

    @staticmethod
    def _combine_pages(
        pages: list[KnowledgePage],
    ) -> tuple[str, list[tuple[int, int, int]]]:
        parts: list[str] = []
        ranges: list[tuple[int, int, int]] = []
        offset = 0

        previous_content = ""
        for page in pages:
            if parts:
                separator = KnowledgeSplitter._page_separator(
                    previous_content,
                    page.content,
                )
                parts.append(separator)
                offset += len(separator)
            start = offset
            parts.append(page.content)
            offset += len(page.content)
            ranges.append((start, offset, page.page_number))
            previous_content = page.content

        return "".join(parts), ranges

    @staticmethod
    def _page_separator(previous: str, following: str) -> str:
        previous = previous.rstrip()
        following = following.lstrip()
        if not previous or not following:
            return "\n\n"
        first_word = re.search(r"[A-Za-z가-힣]", following)
        if first_word and first_word.group(0).islower() and previous[-1] not in ".!?。！？:;":
            return " "
        return "\n\n"

    @staticmethod
    def _find_heading_matches(
        content: str,
        headings: dict[str, KnowledgeSectionType | None],
        *,
        document_type: KnowledgeDocumentType,
        attached_body_headings: frozenset[str],
    ) -> list[tuple[int, str, KnowledgeSectionType]]:
        candidates: list[_HeadingCandidate] = []

        for heading, section_type in sorted(headings.items(), key=lambda item: len(item[0]), reverse=True):
            for match in KnowledgeSplitter._heading_occurrences(
                content,
                heading,
                require_standalone=KnowledgeSplitter._requires_standalone_heading(
                    heading=heading,
                    section_type=section_type,
                    document_type=document_type,
                    attached_body_headings=attached_body_headings,
                ),
            ):
                if not KnowledgeSplitter._is_eligible_heading_match(
                    content=content,
                    match=match,
                    section_type=section_type,
                    document_type=document_type,
                ):
                    continue
                is_decorated_heading = KnowledgeSplitter._is_decorated_heading_line(
                    content,
                    match.start(),
                    match.end(),
                )
                if not is_decorated_heading and not KnowledgeSplitter._is_heading_boundary(
                    content,
                    match.start(),
                    match.end(),
                    allow_attached_body=(heading in attached_body_headings),
                ):
                    continue
                candidate_start = KnowledgeSplitter._numbered_heading_start(
                    content,
                    match.start(),
                )
                candidates.append(
                    (
                        candidate_start,
                        match.end(),
                        heading,
                        section_type,
                    )
                )

        if document_type == KnowledgeDocumentType.RESEARCH_ARTICLE:
            candidates.extend(
                KnowledgeSplitter._research_heading_candidates(
                    content,
                    headings,
                )
            )
        elif document_type == KnowledgeDocumentType.REGULATORY_DRUG_LABEL:
            candidates.extend(KnowledgeSplitter._regulatory_heading_candidates(content))

        selected: list[_HeadingCandidate] = []
        last_selected_end = -1
        last_start_by_heading: dict[str, int] = {}
        for candidate in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
            start, end, heading, _ = candidate
            if start < last_selected_end:
                continue
            normalized_heading = heading.casefold()
            previous_start = last_start_by_heading.get(normalized_heading)
            if previous_start is not None and start - previous_start < 120:
                continue
            selected.append(candidate)
            last_selected_end = end
            last_start_by_heading[normalized_heading] = start

        return KnowledgeSplitter._resolve_inherited_heading_types(selected)

    @staticmethod
    def _requires_standalone_heading(
        *,
        heading: str,
        section_type: KnowledgeSectionType | None,
        document_type: KnowledgeDocumentType,
        attached_body_headings: frozenset[str],
    ) -> bool:
        if section_type is None:
            return heading not in attached_body_headings
        return (
            section_type == KnowledgeSectionType.REFERENCES and document_type != KnowledgeDocumentType.RESEARCH_ARTICLE
        )

    @staticmethod
    def _is_eligible_heading_match(
        *,
        content: str,
        match: re.Match[str],
        section_type: KnowledgeSectionType | None,
        document_type: KnowledgeDocumentType,
    ) -> bool:
        if document_type != KnowledgeDocumentType.RESEARCH_ARTICLE:
            return True
        line_start = content.rfind("\n", 0, match.start()) + 1
        if re.match(
            r"(?i)^\s*Keywords?\s*:",
            content[line_start : match.start()],
        ):
            return False
        if section_type == KnowledgeSectionType.REFERENCES:
            return KnowledgeSplitter._is_references_section_start(
                content,
                match.start(),
                match.end(),
            )
        if KnowledgeSplitter._is_inline_abstract_label(
            content,
            match.start(),
            match.end(),
        ):
            return False
        if section_type == KnowledgeSectionType.RESULTS:
            line_end = content.find("\n", match.end())
            if line_end < 0:
                line_end = len(content)
            suffix = content[match.end() : line_end].lstrip()
            if suffix.startswith("of "):
                return False
        return True

    @staticmethod
    def _is_references_section_start(
        content: str,
        heading_start: int,
        heading_end: int,
    ) -> bool:
        """표 머리글의 References와 실제 참고문헌 섹션을 구분합니다."""
        if not KnowledgeSplitter._is_standalone_heading_line(
            content,
            heading_start,
            heading_end,
        ):
            # 한 줄짜리 합성 테스트와 일부 PDF는 ``References`` 뒤에 바로
            # 첫 인용문을 둡니다. 표 열 이름은 대개 소문자이므로 정확한
            # 대문자 표기만 참고문헌 시작으로 인정합니다.
            return content[heading_start:heading_end] in {
                "References",
                "Bibliography",
            }
        following = content[heading_end:]
        first_entry = re.match(
            r"\s*(?:\[?\d{1,3}\]?)[.)]?\s+[A-Z가-힣]",
            following,
        )
        return first_entry is not None

    @staticmethod
    def _heading_occurrences(
        content: str,
        heading: str,
        *,
        require_standalone: bool,
    ) -> Iterator[re.Match[str]]:
        heading_parts = heading.split()
        if not heading_parts:
            return iter(())
        pattern = r"\s+".join(re.escape(part) for part in heading_parts)
        matches = re.finditer(pattern, content, flags=re.IGNORECASE)
        if not require_standalone:
            return matches
        return (
            match
            for match in matches
            if KnowledgeSplitter._is_standalone_heading_line(
                content,
                match.start(),
                match.end(),
            )
        )

    @staticmethod
    def _is_standalone_heading_line(
        content: str,
        start: int,
        end: int,
    ) -> bool:
        line_start = content.rfind("\n", 0, start) + 1
        line_end = content.find("\n", end)
        if line_end < 0:
            line_end = len(content)
        return not content[line_start:start].strip() and not content[end:line_end].strip()

    @staticmethod
    def _is_inline_abstract_label(
        content: str,
        start: int,
        end: int,
    ) -> bool:
        if not content[end:].lstrip().startswith(":"):
            return False
        abstract_start = re.search(r"(?im)^\s*Abstract\s*$", content)
        body_start = re.search(r"(?im)^\s*Introduction\s*$", content)
        if not abstract_start or start <= abstract_start.start():
            return False
        return body_start is None or start < body_start.start()

    @staticmethod
    def _regulatory_heading_candidates(
        content: str,
    ) -> list[_HeadingCandidate]:
        matches = [
            *_REGULATORY_NUMBERED_SUBSECTION_HEADING.finditer(content),
            *_REGULATORY_BODY_SUBHEADING.finditer(content),
        ]
        return [
            (
                match.start(),
                match.end(),
                match.group("title").strip(),
                None,
            )
            for match in matches
        ]

    @staticmethod
    def _research_heading_candidates(
        content: str,
        headings: dict[str, KnowledgeSectionType | None],
    ) -> list[_HeadingCandidate]:
        candidates: list[_HeadingCandidate] = [
            (
                match.start(),
                match.end(),
                match.group("title").strip(),
                KnowledgeSectionType.INTERACTION,
            )
            for match in _RESEARCH_NUMBERED_INTERACTION_HEADING.finditer(content)
        ]
        known_headings = {heading.casefold() for heading in headings}
        for match in _RESEARCH_NUMBERED_SUBSECTION_HEADING.finditer(content):
            title = match.group("title").strip()
            if title.casefold() in known_headings:
                continue
            candidates.append(
                (
                    match.start(),
                    match.end(),
                    title,
                    None,
                )
            )
        for match in _RESEARCH_NUMBERED_TOP_LEVEL_HEADING.finditer(content):
            title = match.group("title").strip()
            if title.casefold() in known_headings or re.search(
                r"(?i)\b(?:DNIs?|interaction)s?\b",
                title,
            ):
                continue
            candidates.append(
                (
                    match.start(),
                    match.end(),
                    title,
                    KnowledgeSectionType.OTHER,
                )
            )
        return candidates

    @staticmethod
    def _resolve_inherited_heading_types(
        selected: list[_HeadingCandidate],
    ) -> list[tuple[int, str, KnowledgeSectionType]]:
        resolved: list[tuple[int, str, KnowledgeSectionType]] = []
        inherited_type = KnowledgeSectionType.OTHER
        for start, _, heading, section_type in sorted(selected):
            if section_type is not None:
                inherited_type = section_type
            resolved.append(
                (
                    start,
                    heading,
                    section_type or inherited_type,
                )
            )
        return resolved

    @staticmethod
    def _numbered_heading_start(content: str, heading_start: int) -> int:
        line_start = content.rfind("\n", 0, heading_start) + 1
        prefix = content[line_start:heading_start]
        if re.fullmatch(
            r"\s*\d+(?:\.\d+)*[.)]?(?:\s*\|\s*|\s+)",
            prefix,
        ):
            return line_start
        return heading_start

    @staticmethod
    def _is_decorated_heading_line(
        content: str,
        start: int,
        end: int,
    ) -> bool:
        line_start = content.rfind("\n", 0, start) + 1
        line_end = content.find("\n", end)
        if line_end < 0:
            line_end = len(content)

        prefix = content[line_start:start].strip()
        suffix = content[end:line_end].strip()
        decorations = f"{prefix}{suffix}"
        return bool(decorations) and re.fullmatch(r"[-–—\u00ad]+", decorations) is not None

    @staticmethod
    def _is_heading_boundary(
        content: str,
        start: int,
        end: int,
        *,
        allow_attached_body: bool = False,
    ) -> bool:
        at_line_start = start == 0
        if start > 0:
            prefix = content[:start]
            line_prefix = prefix.rsplit("\n", maxsplit=1)[-1]
            at_line_start = not line_prefix.strip()
            follows_numbered_prefix = (
                re.fullmatch(
                    r"\s*\d+(?:\.\d+)*[.)]?(?:\s*\|\s*|\s+)",
                    line_prefix,
                )
                is not None
            )
            previous_non_space = prefix.rstrip()
            if not at_line_start and not follows_numbered_prefix and previous_non_space:
                if previous_non_space[-1] not in ".!?。:;)]}":
                    return False

        if end < len(content):
            following_text = content[end:]
            following = following_text[0]
            if not following.isspace() and following not in ":：-–—([{•·":
                if not (allow_attached_body and (at_line_start or following.isdigit())):
                    return False
                if _ATTACHED_BODY_PROSE_CONTINUATION.match(following_text):
                    return False

        return True

    def _split_section_content(
        self,
        content: str,
        policy: ChunkingPolicy,
        *,
        document_type: KnowledgeDocumentType | None = None,
    ) -> list[tuple[str, int, int]]:
        if self._token_counter.count(content) <= policy.hard_max_tokens:
            return [(content, 0, len(content))]

        if document_type == KnowledgeDocumentType.RESEARCH_ARTICLE:
            nutrient_chunks = self._split_research_nutrient_units(
                content,
                policy,
            )
            if nutrient_chunks:
                return nutrient_chunks

        return self._recursive_split_content(content, policy)

    def _split_research_nutrient_units(
        self,
        content: str,
        policy: ChunkingPolicy,
    ) -> list[tuple[str, int, int]]:
        matches = list(_RESEARCH_NUTRIENT_SUBHEADING.finditer(content))
        if len(matches) < 2:
            return []

        units: list[tuple[int, int]] = []
        for index, match in enumerate(matches):
            start = 0 if index == 0 else match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            units.append((start, end))

        grouped: list[tuple[str, int, int]] = []
        group_start, group_end = units[0]
        for unit_start, unit_end in units[1:]:
            candidate = content[group_start:unit_end].strip()
            if self._token_counter.count(candidate) <= policy.hard_max_tokens:
                group_end = unit_end
                continue
            grouped.extend(
                self._bounded_semantic_group(
                    content,
                    group_start,
                    group_end,
                    policy,
                )
            )
            group_start, group_end = unit_start, unit_end
        grouped.extend(
            self._bounded_semantic_group(
                content,
                group_start,
                group_end,
                policy,
            )
        )
        return grouped

    def _bounded_semantic_group(
        self,
        source: str,
        start: int,
        end: int,
        policy: ChunkingPolicy,
    ) -> list[tuple[str, int, int]]:
        content = source[start:end].strip()
        leading = len(source[start:end]) - len(source[start:end].lstrip())
        absolute_start = start + leading
        if self._token_counter.count(content) <= policy.hard_max_tokens:
            return [(content, absolute_start, absolute_start + len(content))]
        return [
            (chunk, absolute_start + local_start, absolute_start + local_end)
            for chunk, local_start, local_end in self._recursive_split_content(
                content,
                policy,
            )
        ]

    def _recursive_split_content(
        self,
        content: str,
        policy: ChunkingPolicy,
    ) -> list[tuple[str, int, int]]:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=policy.hard_max_tokens,
            chunk_overlap=policy.overlap_tokens,
            length_function=self._token_counter.count,
            separators=self._SEPARATORS,
            is_separator_regex=False,
        )
        chunks = self._locate_split_chunks(
            content,
            splitter.split_text(content),
        )
        return self._merge_small_fragments(
            content,
            chunks,
            policy,
        )

    @staticmethod
    def _locate_split_chunks(
        source: str,
        split_chunks: list[str],
    ) -> list[tuple[str, int, int]]:
        located: list[tuple[str, int, int]] = []
        previous_start = -1

        for chunk in split_chunks:
            start = source.find(chunk, previous_start + 1)
            if start < 0 and located:
                previous_content, nested_start, _ = located[-1]
                if chunk.startswith(previous_content) and source.startswith(
                    chunk,
                    nested_start,
                ):
                    located[-1] = (
                        chunk,
                        nested_start,
                        nested_start + len(chunk),
                    )
                    previous_start = nested_start
                    continue
            if start < 0:
                raise ValueError("재귀 분할 청크의 원문 위치를 찾지 못했습니다.")
            previous_start = start
            located.append((chunk, start, start + len(chunk)))

        return located

    def _merge_small_fragments(
        self,
        source: str,
        chunks: list[tuple[str, int, int]],
        policy: ChunkingPolicy,
    ) -> list[tuple[str, int, int]]:
        merged: list[tuple[str, int, int]] = []

        for content, start, end in chunks:
            if merged and self._token_counter.count(content) < policy.target_min_tokens:
                _, previous_start, _ = merged[-1]
                combined = source[previous_start:end].strip()
                if self._token_counter.count(combined) <= policy.hard_max_tokens:
                    merged[-1] = (
                        combined,
                        previous_start,
                        end,
                    )
                    continue
            merged.append((content, start, end))

        return merged

    def _build_chunk(
        self,
        *,
        content: str,
        section: KnowledgeSection,
        chunk_index: int,
        metadata,
        content_kind: KnowledgeContentKind = KnowledgeContentKind.TEXT,
        table_title: str | None = None,
        table_super_headers: list[str] | None = None,
        table_group_id: str | None = None,
        table_sequence: int | None = None,
    ) -> KnowledgeChunk:
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunk_key = "|".join(
            [
                metadata.document_id,
                section.section_type.value,
                str(section.page_start),
                str(section.page_end),
                str(chunk_index),
                content_hash,
            ]
        )
        chunk_id = hashlib.sha256(chunk_key.encode("utf-8")).hexdigest()
        entities = self._entity_extractor.extract_from_chunk(
            document_type=metadata.document_type,
            title=metadata.title,
            content=content,
            document_id=metadata.document_id,
            section_type=section.section_type,
        )
        metadata_values = metadata.model_dump()
        metadata_values.update(
            {
                "drug_names": entities.drug_names or metadata.drug_names,
                "ingredient_names": entities.ingredient_names or metadata.ingredient_names,
                "food_names": entities.food_names or metadata.food_names,
                "entity_catalog_entries": (entities.entity_catalog_entries or metadata.entity_catalog_entries),
                "interaction_type": entities.interaction_type or metadata.interaction_type,
                "interaction_pair_keys": (entities.interaction_pair_keys or metadata.interaction_pair_keys),
                "evidence_level": (
                    entities.evidence_level
                    if entities.evidence_level != KnowledgeEvidenceLevel.UNKNOWN
                    else metadata.evidence_level
                ),
                "study_population": (
                    entities.study_population
                    if entities.study_population != KnowledgeStudyPopulation.UNKNOWN
                    else metadata.study_population
                ),
                "content_kind": content_kind,
                "table_title": table_title,
                "table_super_headers": table_super_headers or [],
                "table_group_id": table_group_id,
                "table_sequence": table_sequence,
            }
        )
        chunk_metadata = KnowledgeChunkMetadata(
            **metadata_values,
            section_type=section.section_type,
            section_title=section.section_title,
            page_start=section.page_start,
            page_end=section.page_end,
            chunk_index=chunk_index,
            content_hash=content_hash,
        )

        return KnowledgeChunk(
            chunk_id=chunk_id,
            content=content,
            embedding_text=self._build_embedding_text(
                content=content,
                metadata=chunk_metadata,
            ),
            token_count=self._token_counter.count(content),
            metadata=chunk_metadata,
        )

    @staticmethod
    def _build_embedding_text(
        *,
        content: str,
        metadata: KnowledgeChunkMetadata,
    ) -> str:
        prefixes = [f"[문서] {metadata.title}"]
        if metadata.drug_names:
            prefixes.append(f"[약] {', '.join(metadata.drug_names)}")
        if metadata.ingredient_names:
            prefixes.append(f"[성분] {', '.join(metadata.ingredient_names)}")
        if metadata.food_names:
            prefixes.append(f"[음식] {', '.join(metadata.food_names)}")
        if metadata.interaction_type:
            label = _INTERACTION_LABELS.get(
                metadata.interaction_type,
                metadata.interaction_type,
            )
            prefixes.append(f"[상호작용] {label}")
        evidence_label = _EVIDENCE_LABELS.get(metadata.evidence_level.value)
        if evidence_label:
            prefixes.append(f"[근거 수준] {evidence_label}")
        population_label = _POPULATION_LABELS.get(metadata.study_population.value)
        if population_label:
            prefixes.append(f"[연구 대상] {population_label}")
        section_name = metadata.section_title or metadata.section_type.value
        prefixes.append(f"[섹션] {section_name}")
        if metadata.table_title:
            prefixes.append(f"[표 제목] {metadata.table_title}")
        if metadata.table_super_headers:
            prefixes.append(f"[표 설명] {', '.join(metadata.table_super_headers)}")
        return "\n".join([*prefixes, "[원문]", content])

    @staticmethod
    def _page_range_for(
        start: int,
        end: int,
        page_ranges: list[tuple[int, int, int]],
    ) -> tuple[int, int]:
        overlapping = [
            page_number for page_start, page_end, page_number in page_ranges if start < page_end and end > page_start
        ]
        if not overlapping:
            return page_ranges[0][2], page_ranges[-1][2]
        return min(overlapping), max(overlapping)

    @staticmethod
    def _validate_single_document(pages: list[KnowledgePage]) -> None:
        document_ids = {page.metadata.document_id for page in pages}
        if len(document_ids) != 1:
            raise ValueError("한 번에 하나의 지식 문서만 청킹할 수 있습니다.")
