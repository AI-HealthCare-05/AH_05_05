"""Small, field-scoped fixes for common OCR unit errors."""

from __future__ import annotations

import re
import unicodedata

_KOREAN_MILLIGRAM_ERROR = re.compile(
    r"(?<=\d)(?:밀리그람|밀리그랑|미리그램)"
)
_KOREAN_MILLILITER = re.compile(r"(?<=\d)밀리리터")
_MILLILITER_ERROR = re.compile(r"(?<=\d)[mM][lLI1ℓ](?![A-Za-z])")
_MILLIGRAM_ERROR = re.compile(r"(?<=\d)[mM][gG9](?![A-Za-z])")


def normalize_measurement_unit_ocr(text: str) -> str:
    """Normalize only numeric measurement units, never medication names."""

    normalized = unicodedata.normalize("NFKC", text)
    normalized = _KOREAN_MILLIGRAM_ERROR.sub("밀리그램", normalized)
    normalized = _KOREAN_MILLILITER.sub("mL", normalized)
    normalized = _MILLILITER_ERROR.sub("mL", normalized)
    return _MILLIGRAM_ERROR.sub("mg", normalized)


def normalize_strength_ocr(text: str) -> str:
    """Canonicalize spacing and common mg/mL OCR forms in a strength field."""

    return normalize_measurement_unit_ocr("".join(text.split())).replace(
        "밀리그램",
        "mg",
    )


def normalize_dose_unit_ocr(text: str) -> str:
    """Normalize tightly bounded dosage-form errors inside a dose cell."""

    normalized = "".join(normalize_measurement_unit_ocr(text).split())
    normalized = re.sub(r"(?<=\d)캡술(?=(?:씩)?$)", "캡슐", normalized)
    return re.sub(r"(?<=\d)(?:전|점)(?=(?:씩)?$)", "정", normalized)
