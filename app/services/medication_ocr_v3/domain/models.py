"""Normalized, provider-independent OCR values safe for later analysis stages."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

from app.services.medication_ocr_v3.domain.image import Quad


class OcrBlockIssueCode(StrEnum):
    INVALID_BLOCK_CONFIDENCE = "INVALID_BLOCK_CONFIDENCE"
    INVALID_BLOCK_GEOMETRY = "INVALID_BLOCK_GEOMETRY"


class OcrErrorCode(StrEnum):
    OCR_TIMEOUT = "OCR_TIMEOUT"
    OCR_CONNECTION_FAILED = "OCR_CONNECTION_FAILED"
    OCR_AUTH_REJECTED = "OCR_AUTH_REJECTED"
    OCR_UPSTREAM_FAILED = "OCR_UPSTREAM_FAILED"
    OCR_PROTOCOL_INVALID = "OCR_PROTOCOL_INVALID"


class OcrProviderError(RuntimeError):
    """A stable provider failure that intentionally contains no upstream details."""

    def __init__(self, code: OcrErrorCode, status_code: int) -> None:
        super().__init__(code.value)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class OcrBlock:
    block_id: str
    text: str
    confidence: float | None
    bbox: Quad | None
    line_break: bool
    issues: tuple[OcrBlockIssueCode, ...]

    def as_dict(self) -> dict[str, object]:
        if self.confidence is not None and not _is_finite_number(self.confidence):
            raise ValueError("OCR block contains non-finite values.")
        bbox: dict[str, object] | None = None
        if self.bbox is not None:
            if any(not _is_finite_number(point.x) or not _is_finite_number(point.y) for point in self.bbox):
                raise ValueError("OCR block contains non-finite values.")
            bbox = {
                "coordinateSpace": "processed",
                "points": [{"x": point.x, "y": point.y} for point in self.bbox],
            }
        return {
            "blockId": self.block_id,
            "text": self.text,
            "confidence": self.confidence,
            "bbox": bbox,
            "lineBreak": self.line_break,
            "issues": [issue.value for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class OcrResult:
    blocks: tuple[OcrBlock, ...]

    def as_dict(self) -> dict[str, object]:
        return {"blocks": [block.as_dict() for block in self.blocks]}


def _is_finite_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False
