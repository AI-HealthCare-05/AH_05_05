from typing import Any

from ai_worker.rag.loaders.botanical_review_layout_parser import (
    BotanicalReviewLayoutParser,
)
from ai_worker.rag.loaders.drug_vitamin_d_review_layout_parser import (
    DrugVitaminDReviewLayoutParser,
)
from ai_worker.rag.loaders.herb_drug_review_layout_parser import (
    HerbDrugReviewLayoutParser,
)
from ai_worker.rag.loaders.levothyroxine_calcium_review_layout_parser import (
    LevothyroxineCalciumReviewLayoutParser,
)
from ai_worker.rag.loaders.pdf_layout_extractor import PdfLayoutExtraction
from ai_worker.rag.loaders.primary_care_herb_drug_review_layout_parser import (
    PrimaryCareHerbDrugReviewLayoutParser,
)
from ai_worker.rag.loaders.statins_vitamin_d_review_layout_parser import (
    StatinsVitaminDReviewLayoutParser,
)
from ai_worker.rag.loaders.warfarin_review_layout_parser import (
    WarfarinReviewLayoutParser,
)
from ai_worker.schemas.knowledge import (
    KnowledgeContentKind,
    KnowledgeExtractionWarning,
    KnowledgePageBlock,
    KnowledgeTableRow,
)


class VerifiedKnowledgeLayoutParser:
    """출처별로 사람이 검증한 좌표 파서를 선택합니다."""

    def __init__(self) -> None:
        self._parsers = (
            BotanicalReviewLayoutParser(),
            DrugVitaminDReviewLayoutParser(),
            StatinsVitaminDReviewLayoutParser(),
            LevothyroxineCalciumReviewLayoutParser(),
            PrimaryCareHerbDrugReviewLayoutParser(),
            HerbDrugReviewLayoutParser(),
            WarfarinReviewLayoutParser(),
        )

    def parse(
        self,
        *,
        page: Any,
        page_number: int,
        source_id: str,
        document_id: str | None = None,
    ) -> PdfLayoutExtraction | None:
        for parser in self._parsers:
            extraction = parser.parse(
                page=page,
                page_number=page_number,
                source_id=source_id,
                document_id=document_id,
            )
            if extraction is not None:
                return extraction
        return None

    def repair(
        self,
        *,
        extraction: PdfLayoutExtraction,
        page_number: int,
        source_id: str,
    ) -> PdfLayoutExtraction:
        """사람이 원문과 대조한 출처별 표 문맥을 복원합니다."""
        if source_id != "fda_regulatory_drug_labels":
            return extraction
        if page_number == 5:
            return self._repair_fda_pediatric_dosing_table(extraction)
        if page_number == 6:
            return self._set_table_title(
                extraction,
                required_header="Tablet Strength",
                title="LEVO-T tablets are available as follows",
            )
        if page_number == 9:
            return self._repair_fda_page_nine(extraction)
        if page_number == 16:
            return self._set_table_title(
                extraction,
                required_header="Strength (mcg)",
                title=("LEVO-T (levothyroxine sodium, USP) tablets are supplied as follows"),
            )
        return extraction

    @classmethod
    def _repair_fda_page_nine(
        cls,
        extraction: PdfLayoutExtraction,
    ) -> PdfLayoutExtraction:
        potential_impact = next(
            (
                block.content.strip()
                for block in extraction.blocks
                if block.kind == KnowledgeContentKind.TEXT
                and block.content.strip().startswith("Potential impact (below):")
            ),
            None,
        )
        blocks: list[KnowledgePageBlock] = []
        table_index = 0
        for block in extraction.blocks:
            if block.kind == KnowledgeContentKind.TEXT and (
                block.content.strip().startswith("Potential impact (below):")
                or block.content.strip() == "Affecting Free Thyroxine (FT4) Concentration (Euthyroidism)"
            ):
                continue
            if block.kind != KnowledgeContentKind.TABLE:
                blocks.append(block)
                continue

            table_index += 1
            rows = [list(row.cells) for row in block.rows]
            title = block.table_title
            super_headers = list(block.table_super_headers)
            if table_index == 1:
                rows = [
                    [
                        cls._normalize_other_drug_group(row[0]),
                        *row[1:],
                    ]
                    for row in rows
                ]
            elif table_index == 2:
                rows = [
                    [
                        row[0].replace(
                            "Estrogen-containing oral; contraceptives",
                            "Estrogen-containing oral contraceptives",
                        ),
                        *row[1:],
                    ]
                    for row in rows
                ]
                title = (
                    "Drugs That May Alter T4 and Triiodothyronine (T3) Serum "
                    "Transport Without Affecting Free Thyroxine (FT4) "
                    "Concentration (Euthyroidism)"
                )
                if potential_impact:
                    super_headers.append(potential_impact)

            blocks.append(
                cls._replace_table(
                    block,
                    rows=rows,
                    title=title,
                    super_headers=super_headers,
                    validation_errors=[],
                )
            )

        blocks = [block.model_copy(update={"order": index}) for index, block in enumerate(blocks)]
        warnings = [
            warning for warning in extraction.warnings if warning != KnowledgeExtractionWarning.TABLE_STRUCTURE_UNSAFE
        ]
        return PdfLayoutExtraction(blocks=blocks, warnings=warnings)

    @classmethod
    def _repair_fda_pediatric_dosing_table(
        cls,
        extraction: PdfLayoutExtraction,
    ) -> PdfLayoutExtraction:
        footnote_prefix = "a. The dose should be adjusted based on clinical response"
        blocks: list[KnowledgePageBlock] = []
        for block in extraction.blocks:
            if block.kind != KnowledgeContentKind.TABLE or "AGE" not in block.headers:
                blocks.append(block)
                continue
            footnotes = [
                row.cells[0].replace(
                    "Dosage and; Administration",
                    "Dosage and Administration",
                )
                for row in block.rows
                if row.cells and row.cells[0].startswith(footnote_prefix)
            ]
            rows = [
                list(row.cells) for row in block.rows if not row.cells or not row.cells[0].startswith(footnote_prefix)
            ]
            blocks.append(
                cls._replace_table(
                    block,
                    rows=rows,
                    title=block.table_title,
                    super_headers=[*block.table_super_headers, *footnotes],
                    validation_errors=block.validation_errors,
                )
            )
        return PdfLayoutExtraction(blocks=blocks, warnings=extraction.warnings)

    @staticmethod
    def _normalize_other_drug_group(value: str) -> str:
        marker = "Other drugs:"
        if marker not in value:
            return value
        value = value.replace(
            "Antacids; - Aluminum & Magnesium; Hydroxides; - Simethicone",
            "Antacids - Aluminum & Magnesium Hydroxides; Antacids - Simethicone",
        )
        members = [item.strip() for item in value.split(";") if item.strip()]
        normalized: list[str] = []
        for member in members:
            if member == marker:
                continue
            normalized.append(f"{marker} {member}")
        return "; ".join(normalized)

    @classmethod
    def _set_table_title(
        cls,
        extraction: PdfLayoutExtraction,
        *,
        required_header: str,
        title: str,
    ) -> PdfLayoutExtraction:
        blocks = [
            (
                block.model_copy(update={"table_title": title})
                if block.kind == KnowledgeContentKind.TABLE and required_header in block.headers
                else block
            )
            for block in extraction.blocks
        ]
        return PdfLayoutExtraction(blocks=blocks, warnings=extraction.warnings)

    @staticmethod
    def _replace_table(
        block: KnowledgePageBlock,
        *,
        rows: list[list[str]],
        title: str | None,
        super_headers: list[str],
        validation_errors: list[str],
    ) -> KnowledgePageBlock:
        content = "\n".join(
            " | ".join(f"{header}={cell}" for header, cell in zip(block.headers, row, strict=True)) for row in rows
        )
        return block.model_copy(
            update={
                "content": content,
                "rows": [KnowledgeTableRow(cells=row) for row in rows],
                "table_title": title,
                "table_super_headers": list(dict.fromkeys(super_headers)),
                "validation_errors": validation_errors,
            }
        )
