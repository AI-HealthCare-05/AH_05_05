"""Adaptive profiles must not alter pixels on an untrusted geometry branch."""

import io

import cv2
import numpy as np
import pytest
from PIL import Image

from app.services.medication_ocr_v3.domain.image import Point, PreprocessingMode
from app.services.medication_ocr_v3.pipeline.preprocess import preprocess_image


def _page() -> bytes:
    rgb = np.full((720, 1000, 3), 255, dtype=np.uint8)
    for y in range(120, 620, 50):
        cv2.putText(rgb, "MEDICINE 120mg  1  3  7", (100, y), 0, 0.8, (25, 40, 60), 1, cv2.LINE_AA)
    cv2.rectangle(rgb, (820, 90), (890, 600), (190, 220, 210), -1)
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    return stream.getvalue()


@pytest.mark.parametrize(
    ("quad", "expected_version", "expected_mode"),
    [
        (
            (Point(40, 40), Point(960, 40), Point(960, 680), Point(40, 680)),
            "v3.2.7",
            PreprocessingMode.PERSPECTIVE,
        ),
        (
            (Point(0, 0), Point(1000, 0), Point(1000, 720), Point(0, 720)),
            "v3.1.3",
            PreprocessingMode.RECAPTURE,
        ),
    ],
)
def test_adaptive_photometric_uses_geometry_and_keeps_exact_fallback_pixels(quad, expected_version, expected_mode):
    source = _page()
    reference = preprocess_image(source, "image/png", preprocess_version=expected_version, document_quad_override=quad)
    candidate = preprocess_image(source, "image/png", preprocess_version="v3.4.1", document_quad_override=quad)
    assert candidate.preprocessing_mode is expected_mode
    assert candidate.template_image.jpeg_bytes == reference.template_image.jpeg_bytes
    assert candidate.raw_to_template == reference.raw_to_template
    assert candidate.quality_state == reference.quality_state
    assert candidate.source_bytes == source


def test_promoted_default_uses_the_evaluated_adaptive_profile():
    source = _page()
    quad = (Point(40, 40), Point(960, 40), Point(960, 680), Point(40, 680))
    default = preprocess_image(source, "image/png", document_quad_override=quad)
    explicit = preprocess_image(source, "image/png", document_quad_override=quad, preprocess_version="v3.4.1")
    assert default.template_image.jpeg_bytes == explicit.template_image.jpeg_bytes
    assert default.raw_to_template == explicit.raw_to_template


@pytest.mark.asyncio
async def test_service_default_forwards_promoted_profile_to_preprocessing(monkeypatch):
    from types import SimpleNamespace

    import app.services.medication_ocr_v3.service as service_module

    seen = []

    def stop_after_version_capture(content, mime, *, preprocess_version):
        seen.append(preprocess_version)
        raise RuntimeError("version captured before OCR")

    monkeypatch.setattr(service_module, "preprocess_image", stop_after_version_capture)
    service = service_module.MedicationOcrV3Service(provider=SimpleNamespace())
    with pytest.raises(RuntimeError, match="version captured before OCR"):
        await service.analyze(SimpleNamespace(content=_page(), media_type="image/png"))
    assert seen == ["v3.4.1"]


def _small_print(*, large=False, rules=False):
    rgb = np.full((480, 700, 3), 255, dtype=np.uint8)
    for y in range(60, 450, 40):
        if rules:
            for x in range(40, 650, 16):
                cv2.rectangle(rgb, (x, y), (x + 7, y + 2), (20, 20, 20), -1)
        else:
            cv2.putText(rgb, "MEDICINE 120mg  1  3  7", (40, y), 0, 0.7 if large else 0.3, (30, 30, 30), 1)
    return rgb


def test_small_print_enlargement_improves_sampling_and_supplies_exact_scale():
    from app.services.medication_ocr_v3.pipeline import adaptive

    rgb = _small_print()
    output, matrix, operation = adaptive.enlarge_small_print(rgb)
    assert output.shape[0] > rgb.shape[0]
    assert output.shape[1] > rgb.shape[1]
    assert max(output.shape[:2]) <= 2048
    assert matrix[0, 0] == pytest.approx(output.shape[1] / rgb.shape[1])
    assert matrix[1, 1] == pytest.approx(output.shape[0] / rgb.shape[0])
    assert matrix[0, 2] == matrix[1, 2] == 0
    assert operation.startswith("small_print_enlarged")
    assert rgb.shape == (480, 700, 3)


@pytest.mark.parametrize("kind", ["large", "rules", "blank", "wide", "tall"])
def test_small_print_enlargement_skips_unneeded_or_unreliable_evidence(kind):
    from app.services.medication_ocr_v3.pipeline import adaptive

    rgb = _small_print(large=kind == "large", rules=kind == "rules")
    if kind in {"blank", "wide", "tall"}:
        shape = {"blank": (480, 700, 3), "wide": (1, 4096, 3), "tall": (4096, 1, 3)}[kind]
        rgb = np.full(shape, 255, dtype=np.uint8)
    output, matrix, operation = adaptive.enlarge_small_print(rgb)
    assert np.array_equal(output, rgb)
    assert np.array_equal(matrix, np.eye(3))
    assert operation.startswith("small_print_skipped")


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_small_print_profile_composes_resize_rotation_and_privacy_mask(rotation):
    from app.services.medication_ocr_v3.pipeline.preprocess import apply_matrix
    from app.services.medication_ocr_v3.pipeline.privacy_artifact import build_privacy_safe_provider_image

    stream = io.BytesIO()
    Image.fromarray(_small_print()).save(stream, format="PNG")
    result = preprocess_image(stream.getvalue(), "image/png", manual_rotation=rotation, preprocess_version="v3.4.2")
    assert max(result.template_image.width, result.template_image.height) <= 4096
    assert result.raw_to_template.target_width == result.template_image.width
    assert result.raw_to_template.target_height == result.template_image.height
    for point in (Point(100, 100), Point(250, 200), Point(450, 300)):
        mapped = apply_matrix(result.raw_to_template.matrix, point)
        restored = apply_matrix(result.raw_to_template.inverse, mapped)
        assert restored.x == pytest.approx(point.x, abs=1e-6)
        assert restored.y == pytest.approx(point.y, abs=1e-6)
    if rotation == 0:
        assert any(op.startswith("small_print_enlarged") for op in result.operations)
    masked = build_privacy_safe_provider_image(result, ((0.2, 0.2, 0.7, 0.7),))
    pixels = np.array(Image.open(io.BytesIO(masked)))
    oriented = Point(result.oriented_dimensions.width * 0.4, result.oriented_dimensions.height * 0.4)
    raw = apply_matrix(result.raw_to_oriented.inverse, oriented)
    mapped = apply_matrix(result.raw_to_template.matrix, raw)
    assert pixels[round(mapped.y), round(mapped.x)].min() > 245


def test_illumination_selector_ignores_print_on_even_paper_but_detects_directional_shadow():
    from app.services.medication_ocr_v3.pipeline import adaptive

    rgb = _small_print(large=True)
    assert not adaptive.needs_illumination_correction(rgb)
    shade = np.linspace(0.55, 1.0, rgb.shape[1])[None, :, None]
    shadowed = (rgb * shade).astype(np.uint8)
    assert adaptive.needs_illumination_correction(shadowed)
    assert not adaptive.needs_illumination_correction(np.full((1, 4096, 3), 255, dtype=np.uint8))


def test_adaptive_illumination_preserves_uncorrected_uniform_page_pixels():
    from app.services.medication_ocr_v3.domain.image import CorrectionPreset

    rgb = _small_print(large=True)
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    reference = preprocess_image(stream.getvalue(), "image/png", correction_preset=CorrectionPreset.NONE)
    candidate = preprocess_image(stream.getvalue(), "image/png", preprocess_version="v3.4.3")
    assert candidate.template_image.jpeg_bytes == reference.template_image.jpeg_bytes
    assert candidate.raw_to_template == reference.raw_to_template


@pytest.mark.parametrize("transform", ["jpeg", "rotate"])
def test_small_print_rejects_compressed_or_interpolated_dot_leaders(transform):
    from app.services.medication_ocr_v3.pipeline.adaptive import enlarge_small_print

    rgb = np.full((480, 700, 3), 255, dtype=np.uint8)
    for y in range(50, 450, 30):
        for x in range(30, 660, 15):
            cv2.circle(rgb, (x, y), 2, (0, 0, 0), -1)
    if transform == "jpeg":
        stream = io.BytesIO()
        Image.fromarray(rgb).save(stream, format="JPEG", quality=75)
        rgb = np.array(Image.open(io.BytesIO(stream.getvalue())))
    else:
        matrix = cv2.getRotationMatrix2D((350, 240), 2, 1)
        rgb = cv2.warpAffine(rgb, matrix, (700, 480), borderValue=(255, 255, 255))
    output, _, operation = enlarge_small_print(rgb)
    assert output.shape == rgb.shape
    assert operation.startswith("small_print_skipped")


@pytest.mark.parametrize("count", [24, 60, 200, 1000])
def test_small_print_rejects_unstructured_speckles(count):
    from app.services.medication_ocr_v3.pipeline.adaptive import enlarge_small_print

    rgb = np.full((480, 700, 3), 255, dtype=np.uint8)
    rng = np.random.default_rng(17)
    for _ in range(count):
        x, y = int(rng.integers(10, 675)), int(rng.integers(10, 460))
        width, height = int(rng.integers(2, 10)), int(rng.integers(5, 12))
        cv2.rectangle(rgb, (x, y), (x + width - 1, y + height - 1), (40, 40, 40), -1)
    output, _, operation = enlarge_small_print(rgb)
    assert output.shape == rgb.shape
    assert operation.startswith("small_print_skipped")
