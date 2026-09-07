"""Public preprocessing safety contracts, using generated non-patient fixtures."""

import io
import struct

import cv2
import numpy as np
import pytest
from PIL import Image

from app.services.medication_ocr_v3.domain.image import ImageErrorCode, ImageValidationError, Point, QualityState
from app.services.medication_ocr_v3.pipeline.preprocess import apply_matrix, preprocess_image
from app.services.medication_ocr_v3.pipeline.privacy_artifact import build_privacy_safe_provider_image

VERSIONS = ("v3.4.1", "v3.4.2", "v3.4.3")


def _png(rgb):
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    return stream.getvalue()


def _header(width, height):
    # Dimensions are rejected before decoding/allocation, including a hostile
    # header claiming a huge bitmap but supplying no compressed pixel payload.
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x02\x00\x00\x00"
    )


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize(
    ("content", "mime", "code"),
    [
        (b"", "image/png", ImageErrorCode.UNSUPPORTED_IMAGE),
        (b"\xff\xd8\xffdamaged", "image/jpeg", ImageErrorCode.CORRUPT_IMAGE),
        (_header(10001, 100), "image/png", ImageErrorCode.EDGE_LIMIT_EXCEEDED),
        (_header(10000, 4001), "image/png", ImageErrorCode.PIXEL_LIMIT_EXCEEDED),
        (_header(0, 10), "image/png", ImageErrorCode.PIXEL_LIMIT_EXCEEDED),
    ],
)
def test_adaptive_profiles_reject_empty_corrupt_and_oversized_headers(version, content, mime, code):
    with pytest.raises(ImageValidationError) as error:
        preprocess_image(content, mime, preprocess_version=version)
    assert error.value.code is code


@pytest.mark.parametrize("version", VERSIONS)
def test_adaptive_profiles_reject_mismatched_mime_and_truncated_pixels(version):
    valid = _png(np.full((60, 100, 3), 255, dtype=np.uint8))
    with pytest.raises(ImageValidationError) as mismatch:
        preprocess_image(valid, "image/jpeg", preprocess_version=version)
    assert mismatch.value.code is ImageErrorCode.MIME_MISMATCH
    with pytest.raises(ImageValidationError) as corrupt:
        preprocess_image(valid[:40], "image/png", preprocess_version=version)
    assert corrupt.value.code is ImageErrorCode.CORRUPT_IMAGE


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("shape", [(1, 4096, 3), (4096, 1, 3), (1, 1, 3), (400, 600, 3)])
def test_blank_or_extreme_aspect_input_remains_bounded_and_requires_recapture(version, shape):
    result = preprocess_image(_png(np.full(shape, 255, dtype=np.uint8)), "image/png", preprocess_version=version)
    assert result.quality_state is QualityState.RECAPTURE_REQUIRED
    assert max(result.template_image.width, result.template_image.height) <= 4096
    assert np.isfinite(result.raw_to_template.matrix).all()
    assert np.isfinite(result.raw_to_template.inverse).all()


@pytest.mark.parametrize("version", VERSIONS)
def test_real_perspective_and_manual_rotation_keep_source_roundtrip_and_mask(version):
    rgb = np.full((600, 900, 3), 255, dtype=np.uint8)
    for y in range(90, 550, 45):
        cv2.putText(rgb, "MEDICINE 120mg  1 tablet  3 times  7 days", (65, y), 0, 0.55, (25, 35, 45), 1, cv2.LINE_AA)
    source = _png(rgb)
    # The override is expressed in the 90-degree-oriented image (600 x 900).
    quad = (Point(45, 30), Point(560, 55), Point(570, 860), Point(30, 845))
    result = preprocess_image(
        source, "image/png", manual_rotation=90, document_quad_override=quad, preprocess_version=version
    )
    assert result.template_image.used_perspective
    assert result.source_bytes == source
    for raw in (Point(100, 100), Point(400, 280), Point(700, 450)):
        mapped = apply_matrix(result.raw_to_template.matrix, raw)
        restored = apply_matrix(result.raw_to_template.inverse, mapped)
        assert restored.x == pytest.approx(raw.x, abs=1e-6)
        assert restored.y == pytest.approx(raw.y, abs=1e-6)
    encoded = build_privacy_safe_provider_image(result, ((0.25, 0.25, 0.65, 0.65),))
    masked = np.array(Image.open(io.BytesIO(encoded)))
    for fraction_x in (0.35, 0.45, 0.55):
        for fraction_y in (0.35, 0.45, 0.55):
            oriented = Point(
                result.oriented_dimensions.width * fraction_x, result.oriented_dimensions.height * fraction_y
            )
            raw = apply_matrix(result.raw_to_oriented.inverse, oriented)
            point = apply_matrix(result.raw_to_template.matrix, raw)
            assert masked[round(point.y), round(point.x)].min() > 245


@pytest.mark.parametrize("version", VERSIONS)
def test_horizontal_print_stays_horizontal_without_deskew(version):
    rgb = np.full((500, 800, 3), 255, dtype=np.uint8)
    for y in range(80, 450, 35):
        cv2.putText(rgb, "MEDICINE 1 3 7", (80, y), 0, 0.6, (25, 25, 25), 1, cv2.LINE_AA)
    result = preprocess_image(
        _png(rgb),
        "image/png",
        document_quad_override=(Point(30, 30), Point(770, 30), Point(770, 470), Point(30, 470)),
        preprocess_version=version,
    )
    left = apply_matrix(result.raw_to_template.matrix, Point(100, 250))
    right = apply_matrix(result.raw_to_template.matrix, Point(600, 250))
    assert abs(left.y - right.y) < 1e-6
    assert not any(op.startswith("text_deskew_applied") for op in result.operations)


def test_maximum_source_byte_limit_is_checked_before_decode():
    with pytest.raises(ImageValidationError) as error:
        preprocess_image(b"x" * (50 * 1024 * 1024 + 1), "image/png", preprocess_version="v3.4.1")
    assert error.value.code is ImageErrorCode.SOURCE_TOO_LARGE

