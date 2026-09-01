from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

type Matrix3 = tuple[
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
    float,
]


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float


type Quad = tuple[Point, Point, Point, Point]


class QualityState(StrEnum):
    PROCESSED = "PROCESSED"
    RECAPTURE_REQUIRED = "RECAPTURE_REQUIRED"


class PreprocessingMode(StrEnum):
    PERSPECTIVE = "PERSPECTIVE"
    CROP_DESKEW = "CROP_DESKEW"
    FULL_FRAME = "FULL_FRAME"
    RECAPTURE = "RECAPTURE"


class CorrectionPreset(StrEnum):
    NONE = "none"
    CONSERVATIVE = "conservative"
    ILLUMINATION = "illumination"
    CONTRAST = "contrast"


class ImageErrorCode(StrEnum):
    UNSUPPORTED_IMAGE = "unsupportedImage"
    MIME_MISMATCH = "mimeMismatch"
    CORRUPT_IMAGE = "corruptImage"
    ANIMATED_IMAGE = "animatedImage"
    SOURCE_TOO_LARGE = "sourceTooLarge"
    PIXEL_LIMIT_EXCEEDED = "pixelLimitExceeded"
    EDGE_LIMIT_EXCEEDED = "edgeLimitExceeded"
    INVALID_ROTATION = "invalidRotation"
    INVALID_GRAYSCALE_LEVEL = "invalidGrayscaleLevel"


class ImageValidationError(ValueError):
    """A validation failure whose attributes are safe for a public response."""

    def __init__(self, code: ImageErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ImageDimensions:
    width: int
    height: int

    def as_tuple(self) -> tuple[int, int]:
        return self.width, self.height


@dataclass(frozen=True, slots=True)
class MatrixTransform:
    source_width: int
    source_height: int
    target_width: int
    target_height: int
    matrix: Matrix3
    inverse: Matrix3


@dataclass(frozen=True, slots=True)
class ImageQualityMetrics:
    blur_variance: float
    dark_clipping_ratio: float
    bright_clipping_ratio: float
    illumination_variation: float
    page_coverage: float
    corner_confidence: float
    skew_degrees: float
    edge_density: float
    likely_document_count: int

    def as_dict(self) -> dict[str, float | int]:
        return {
            "blurVariance": self.blur_variance,
            "darkClippingRatio": self.dark_clipping_ratio,
            "brightClippingRatio": self.bright_clipping_ratio,
            "illuminationVariation": self.illumination_variation,
            "pageCoverage": self.page_coverage,
            "cornerConfidence": self.corner_confidence,
            "skewDegrees": self.skew_degrees,
            "edgeDensity": self.edge_density,
            "likelyDocumentCount": self.likely_document_count,
        }


@dataclass(frozen=True, slots=True)
class DocumentDetection:
    polygon: Quad | None
    likely_document_count: int
    confidence: float
    crop_suspicion: bool


@dataclass(frozen=True, slots=True)
class EncodedImage:
    jpeg_bytes: bytes = field(repr=False)
    mime_type: str
    width: int
    height: int
    used_perspective: bool
    rollback_reason: str | None


@dataclass(frozen=True, slots=True)
class PreviewImage:
    image_id: str
    jpeg_bytes: bytes = field(repr=False)
    mime_type: str
    width: int
    height: int
    source_dimensions: ImageDimensions
    source_to_preview: Matrix3
    preview_to_source: Matrix3


@dataclass(frozen=True, slots=True)
class PreprocessResult:
    source_bytes: bytes = field(repr=False)
    source_sha256: str = field(repr=False)
    source_format: str
    decoded_dimensions: ImageDimensions
    oriented_dimensions: ImageDimensions
    raw_to_oriented: MatrixTransform
    raw_to_template: MatrixTransform
    document: DocumentDetection
    metrics: ImageQualityMetrics
    quality_state: QualityState
    preprocessing_mode: PreprocessingMode
    correction_preset: CorrectionPreset
    grayscale_level: int
    reasons: tuple[str, ...]
    operations: tuple[str, ...]
    template_image: EncodedImage
    oriented_preview: PreviewImage
