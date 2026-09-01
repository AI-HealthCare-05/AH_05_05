"""Immutable, privacy-safe evidence types for grounded medication extraction."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.services.medication_ocr_v3.pipeline.ocr_layout import AxisAlignedBBox


@dataclass(frozen=True, slots=True)
class EvidenceBlock:
    block_id: str
    text: str
    confidence: float | None
    bbox: AxisAlignedBBox
    line_id: str
    row_ids: tuple[str, ...]
    allowed_fields: tuple[str, ...]

    def to_llm_payload(self) -> dict[str, object]:
        return {
            "blockId": self.block_id,
            "text": self.text,
            "confidence": self.confidence,
            "bbox": self.bbox.as_dict(),
            "allowedFields": list(self.allowed_fields),
        }


@dataclass(frozen=True, slots=True)
class EvidenceRow:
    row_id: str
    bbox: AxisAlignedBBox
    block_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvidenceCatalog:
    blocks: tuple[EvidenceBlock, ...]
    date_candidates: tuple[EvidenceBlock, ...]
    rows: tuple[EvidenceRow, ...]
    schema_version: str = "v3"

    def to_llm_payload(self) -> dict[str, object]:
        blocks_by_id = {block.block_id: block for block in self.blocks}
        return {
            "schemaVersion": self.schema_version,
            "dateCandidates": [
                {**block.to_llm_payload(), "allowedFields": ["dispensedDate"]}
                for block in self.date_candidates
            ],
            "rows": [
                {
                    "rowId": row.row_id,
                    "bbox": row.bbox.as_dict(),
                    "blocks": [
                        {
                            **blocks_by_id[block_id].to_llm_payload(),
                            "allowedFields": ["strength"],
                        }
                        for block_id in row.block_ids
                        if block_id in blocks_by_id
                        and "strength" in blocks_by_id[block_id].allowed_fields
                    ],
                }
                for row in self.rows
            ],
        }


class StrictSelectionModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
        strict=True,
    )


class MedicationBlockSelection(StrictSelectionModel):
    row_id: str = Field(pattern=r"^row-[0-9]{4}$")
    strength_block_ids: list[str] = Field(max_length=16)


class GroundingSelection(StrictSelectionModel):
    dispensed_date_block_ids: list[str] = Field(max_length=8)
    medications: list[MedicationBlockSelection] = Field(max_length=100)

