from __future__ import annotations

from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

from app.services.medication_ocr_v3.domain.image import ImageQualityMetrics

type UInt8Image = NDArray[np.uint8]


def _bounded_rgb(rgb: UInt8Image, max_edge: int) -> UInt8Image:
    height, width = rgb.shape[:2]
    scale = min(1.0, max_edge / max(width, height))
    if scale >= 1.0:
        return rgb
    return cast(
        UInt8Image,
        cv2.resize(
            rgb,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        ),
    )


def measure_pixels(rgb: UInt8Image) -> tuple[float, float, float, float, float]:
    bounded = _bounded_rgb(rgb, 1600)
    gray = cast(UInt8Image, cv2.cvtColor(bounded, cv2.COLOR_RGB2GRAY))
    blur_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    dark_clip = float(np.mean(gray <= 4))
    bright_clip = float(np.mean(gray >= 251))
    illumination_gray = _bounded_rgb(gray, 1024)
    shorter = min(illumination_gray.shape)
    kernel = min(63, max(9, (shorter // 18) | 1))
    background = cv2.GaussianBlur(illumination_gray, (kernel, kernel), 0)
    illumination = float(np.std(background) / 255.0)
    median = float(np.median(gray))
    lower = int(max(20.0, 0.66 * median))
    upper = int(min(240.0, max(lower + 20.0, 1.33 * median)))
    edges = cv2.Canny(gray, lower, upper)
    edge_density = float(np.mean(edges > 0))
    return blur_variance, dark_clip, bright_clip, illumination, edge_density


def build_metrics(
    rgb: UInt8Image,
    *,
    page_coverage: float,
    corner_confidence: float,
    skew_degrees: float,
    likely_document_count: int,
) -> ImageQualityMetrics:
    blur, dark, bright, illumination, edges = measure_pixels(rgb)
    return ImageQualityMetrics(
        blur_variance=blur,
        dark_clipping_ratio=dark,
        bright_clipping_ratio=bright,
        illumination_variation=illumination,
        page_coverage=page_coverage,
        corner_confidence=corner_confidence,
        skew_degrees=skew_degrees,
        edge_density=edges,
        likely_document_count=likely_document_count,
    )


def warp_quality_is_acceptable(
    *,
    baseline_blur: float,
    baseline_dark_clip: float,
    baseline_bright_clip: float,
    baseline_edge_density: float,
    candidate_blur: float,
    candidate_dark_clip: float,
    candidate_bright_clip: float,
    candidate_edge_density: float,
) -> bool:
    """Reject only meaningful regressions; small interpolation changes are tolerated."""
    blur_ok = candidate_blur >= max(8.0, baseline_blur * 0.48)
    dark_ok = candidate_dark_clip <= baseline_dark_clip + 0.08
    bright_ok = candidate_bright_clip <= baseline_bright_clip + 0.12
    edges_ok = candidate_edge_density >= max(0.002, baseline_edge_density * 0.35)
    return blur_ok and dark_ok and bright_ok and edges_ok
