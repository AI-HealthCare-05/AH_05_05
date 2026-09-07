from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.dtos.medication_guide_ocr import DocumentOcrReadyResponse
from app.services.medication_ocr_v3.pipeline import preprocess


def _sample_rgb() -> np.ndarray:
    x = np.linspace(35, 225, 96, dtype=np.uint8)
    gray = np.tile(x, (64, 1))
    rgb = np.dstack((gray, np.roll(gray, 8, axis=1), np.roll(gray, 16, axis=1)))
    cv2.putText(rgb, "OCR", (8, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (10, 10, 10), 2)
    return rgb


@pytest.mark.parametrize(
    ("version", "treatment"),
    [
        ("v3.2.1", "control"),
        ("v3.2.2", "unsharp_mild"),
        ("v3.2.3", "unsharp_medium"),
        ("v3.2.4", "contrast_mild"),
        ("v3.2.5", "contrast_unsharp_mild"),
        ("v3.2.6", "desaturate_unsharp_mild"),
        ("v3.2.7", "saturate_unsharp_mild"),
        ("v3.2.8", "grayscale_unsharp"),
    ],
)
def test_v32_profiles_keep_v313_geometry_and_select_one_output_treatment(
    version: str,
    treatment: str,
) -> None:
    profile = preprocess._preprocess_profile(version)

    assert profile.grabcut_iterations == 1
    assert profile.grabcut_max_edge == 800
    assert profile.grabcut_trigger_confidence == 0.82
    assert profile.output_treatment == treatment


@pytest.mark.parametrize(
    "treatment",
    [
        "unsharp_mild",
        "unsharp_medium",
        "contrast_mild",
        "contrast_unsharp_mild",
        "desaturate_unsharp_mild",
        "saturate_unsharp_mild",
        "grayscale_unsharp",
    ],
)
def test_output_treatments_are_deterministic_and_change_pixels(treatment: str) -> None:
    source = _sample_rgb()

    apply_treatment = getattr(preprocess, "_apply_output_treatment", None)
    assert callable(apply_treatment)
    first, operation = apply_treatment(source, treatment)
    second, repeated_operation = apply_treatment(source, treatment)

    assert first.shape == source.shape
    assert first.dtype == np.uint8
    assert operation == repeated_operation
    assert np.array_equal(first, second)
    assert not np.array_equal(first, source)


def test_v321_control_preserves_v313_pixels() -> None:
    source = _sample_rgb()

    apply_treatment = getattr(preprocess, "_apply_output_treatment", None)
    assert callable(apply_treatment)
    output, operation = apply_treatment(source, "control")

    assert np.array_equal(output, source)
    assert operation == "output_treatment_control"


def test_v328_produces_grayscale_rgb() -> None:
    apply_treatment = getattr(preprocess, "_apply_output_treatment", None)
    assert callable(apply_treatment)
    output, _ = apply_treatment(_sample_rgb(), "grayscale_unsharp")

    assert np.array_equal(output[..., 0], output[..., 1])
    assert np.array_equal(output[..., 1], output[..., 2])


def test_ready_response_accepts_v32_preprocess_version() -> None:
    response = DocumentOcrReadyResponse.model_validate(
        {
            "batchId": "batch-1",
            "ocrStatus": "ready_for_review",
            "documentImageUrl": "/api/v1/ocr/jobs/batch-1/image",
            "fields": {},
            "medications": [],
            "lowConfidenceCount": 0,
            "preprocessVersion": "v3.2.8",
        }
    )

    assert response.preprocess_version == "v3.2.8"
