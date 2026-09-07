import io
import math

import cv2
import numpy as np
import pytest
from PIL import Image

from app.services.medication_ocr_v3.domain.image import Point
from app.services.medication_ocr_v3.pipeline.preprocess import apply_matrix, preprocess_image


def _page(angle: float = 0, *, rules_only: bool = False) -> tuple[bytes, tuple[Point, Point]]:
    rgb = np.full((720, 1000, 3), 255, dtype=np.uint8)
    for y in range(100, 640, 55):
        if not rules_only:
            cv2.putText(
                rgb,
                "MEDICINE 120mg  1 tablet  3 times  7 days",
                (90, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 0, 0),
                1,
                cv2.LINE_AA,
            )
        cv2.line(rgb, (60, y + 15), (930, y + 15), (80, 80, 80), 1)
    matrix = cv2.getRotationMatrix2D((500, 360), -angle, 1)
    rgb = cv2.warpAffine(rgb, matrix, (1000, 720), borderValue=(255, 255, 255))
    points = cv2.transform(np.array([[[100.0, 300.0], [700.0, 300.0]]]), matrix)[0]
    output = io.BytesIO()
    Image.fromarray(rgb).save(output, format="PNG")
    return output.getvalue(), tuple(Point(float(x), float(y)) for x, y in points)


@pytest.mark.parametrize("angle", [-5.0, 4.0, 15.0])
def test_text_deskew_levels_printed_rows_and_preserves_coordinate_roundtrip(angle: float) -> None:
    source, points = _page(angle)
    result = preprocess_image(
        source,
        "image/png",
        preprocess_version="v3.3.1",
        document_quad_override=(Point(0, 0), Point(1000, 0), Point(1000, 720), Point(0, 720)),
    )
    assert any(op.startswith("text_deskew_applied") for op in result.operations)
    a, b = [apply_matrix(result.raw_to_template.matrix, point) for point in points]
    residual = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
    assert abs(residual) < 0.7
    assert result.source_bytes == source
    for point in points:
        mapped = apply_matrix(result.raw_to_template.matrix, point)
        restored = apply_matrix(result.raw_to_template.inverse, mapped)
        assert restored.x == pytest.approx(point.x)
        assert restored.y == pytest.approx(point.y)
    assert max(result.template_image.width, result.template_image.height) <= 4096


@pytest.mark.parametrize("rules_only", [False, True])
def test_text_deskew_does_not_rotate_horizontal_text_or_table_rules(rules_only: bool) -> None:
    source, _ = _page(0 if not rules_only else 4, rules_only=rules_only)
    result = preprocess_image(source, "image/png", preprocess_version="v3.3.1")
    assert not any(op.startswith("text_deskew_applied") for op in result.operations)


def test_existing_profile_remains_unchanged_by_deskew_opt_in() -> None:
    source, _ = _page(4)
    result = preprocess_image(source, "image/png", preprocess_version="v3.1.3")
    assert not any(op.startswith("text_deskew") for op in result.operations)


def test_text_deskew_preserves_privacy_mask_mapping() -> None:
    from app.services.medication_ocr_v3.pipeline.privacy_artifact import build_privacy_safe_provider_image

    source, _ = _page(4)
    result = preprocess_image(
        source,
        "image/png",
        preprocess_version="v3.3.1",
        document_quad_override=(Point(0, 0), Point(1000, 0), Point(1000, 720), Point(0, 720)),
    )
    assert any(op.startswith("text_deskew_applied") for op in result.operations)
    masked = build_privacy_safe_provider_image(result, ((0.1, 0.2, 0.5, 0.5),))
    pixels = np.array(Image.open(io.BytesIO(masked)))
    for x in (150, 300, 450):
        for y in (175, 250, 330):
            point = apply_matrix(result.raw_to_template.matrix, Point(x, y))
            assert pixels[round(point.y), round(point.x)].min() > 245


def test_text_deskew_skips_blank_and_conflicting_text_angles() -> None:
    from app.services.medication_ocr_v3.pipeline.text_deskew import estimate_text_angle

    assert estimate_text_angle(np.full((600, 800, 3), 255, dtype=np.uint8))[0] == 0
    positive, _ = _page(5)
    negative, _ = _page(-5)
    first = np.array(Image.open(io.BytesIO(positive)))
    second = np.array(Image.open(io.BytesIO(negative)))
    first[360:] = second[360:]
    assert estimate_text_angle(first)[0] == 0


@pytest.mark.parametrize("shape", [(1, 4096, 3), (4096, 1, 3)])
def test_text_deskew_skips_extreme_aspect_without_invalid_resize(shape) -> None:
    from app.services.medication_ocr_v3.pipeline.text_deskew import estimate_text_angle

    assert estimate_text_angle(np.full(shape, 255, dtype=np.uint8))[0] == 0


@pytest.mark.parametrize("angle", [4, 6, 15])
@pytest.mark.parametrize("text_rows", [0, 3, 10])
def test_slanted_dashed_rules_do_not_rotate_horizontal_text(angle, text_rows) -> None:
    from app.services.medication_ocr_v3.pipeline.text_deskew import estimate_text_angle

    rgb = np.full((720, 1000, 3), 255, dtype=np.uint8)
    for y in range(100, 640, 35):
        for x in range(60, 930, 20):
            cv2.rectangle(rgb, (x, y), (x + 8, y + 2), (0, 0, 0), -1)
    rgb = cv2.warpAffine(rgb, cv2.getRotationMatrix2D((500, 360), -angle, 1), (1000, 720), borderValue=(255, 255, 255))
    for y in range(100, 100 + text_rows * 55, 55):
        cv2.putText(
            rgb,
            "MEDICINE 120mg 1 tablet 3 times 7 days",
            (90, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    assert estimate_text_angle(rgb)[0] == 0
