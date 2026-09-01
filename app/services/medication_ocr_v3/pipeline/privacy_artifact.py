"""Build a privacy-safe provider artifact without changing quality analysis input."""

from __future__ import annotations

import io
import json
import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, UnidentifiedImageError

from app.services.medication_ocr_v3.domain.image import Matrix3, PreprocessResult

type PrivacyRectangle = tuple[float, float, float, float]

_MAX_PRIVACY_RECTANGLES = 16


class PrivacyArtifactError(ValueError):
    """A fail-closed privacy artifact validation or transformation failure."""


def parse_privacy_rectangles(value: str) -> tuple[PrivacyRectangle, ...]:
    """Parse a bounded JSON list of normalized oriented-space rectangles."""

    try:
        parsed: object = json.loads(value)
    except (json.JSONDecodeError, RecursionError):
        raise PrivacyArtifactError("Privacy redactions are invalid.") from None
    if (
        not isinstance(parsed, list)
        or len(parsed) > _MAX_PRIVACY_RECTANGLES
    ):
        raise PrivacyArtifactError("Privacy redactions are invalid.")
    return tuple(_validated_rectangle(item) for item in parsed)


def build_privacy_safe_provider_image(
    result: PreprocessResult,
    rectangles: Sequence[PrivacyRectangle],
) -> bytes:
    """Map oriented-space masks into the exact processed provider image."""

    if not rectangles:
        return result.template_image.jpeg_bytes
    oriented_to_template = _compose(
        result.raw_to_template.matrix,
        result.raw_to_oriented.inverse,
    )
    if not np.isfinite(oriented_to_template).all() or abs(
        float(np.linalg.det(oriented_to_template))
    ) < 1e-12:
        raise PrivacyArtifactError("Privacy transform is invalid.")

    try:
        with Image.open(io.BytesIO(result.template_image.jpeg_bytes)) as decoded:
            image = decoded.convert("RGB")
    except (OSError, UnidentifiedImageError):
        raise PrivacyArtifactError("Processed privacy image is invalid.") from None
    if image.size != (
        result.template_image.width,
        result.template_image.height,
    ):
        image.close()
        raise PrivacyArtifactError("Processed privacy image dimensions are invalid.")

    width, height = image.size
    oriented_width = result.oriented_dimensions.width
    oriented_height = result.oriented_dimensions.height
    polygons: list[list[tuple[float, float]]] = []
    for rectangle in rectangles:
        x_min, y_min, x_max, y_max = _validated_rectangle(rectangle)
        oriented_corners = (
            (x_min * oriented_width, y_min * oriented_height),
            (x_max * oriented_width, y_min * oriented_height),
            (x_max * oriented_width, y_max * oriented_height),
            (x_min * oriented_width, y_max * oriented_height),
        )
        polygon = [
            _apply_homography(oriented_to_template, x, y)
            for x, y in oriented_corners
        ]
        if _intersects_canvas(polygon, width, height):
            polygons.append(polygon)

    if not polygons:
        image.close()
        return result.template_image.jpeg_bytes
    margin = max(2, round(min(width, height) * 0.002))
    draw = ImageDraw.Draw(image)
    for polygon in polygons:
        draw.polygon(polygon, fill=(255, 255, 255))
        draw.line(polygon + [polygon[0]], fill=(255, 255, 255), width=margin * 2)
    output = io.BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=95,
        subsampling=0,
        optimize=True,
    )
    image.close()
    return output.getvalue()


def _validated_rectangle(value: object) -> PrivacyRectangle:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise PrivacyArtifactError("Privacy redactions are invalid.")
    numbers: list[float] = []
    for coordinate in value:
        if isinstance(coordinate, bool) or not isinstance(coordinate, (int, float)):
            raise PrivacyArtifactError("Privacy redactions are invalid.")
        number = float(coordinate)
        if not math.isfinite(number) or not 0.0 <= number <= 1.0:
            raise PrivacyArtifactError("Privacy redactions are invalid.")
        numbers.append(number)
    x_min, y_min, x_max, y_max = numbers
    if x_min >= x_max or y_min >= y_max:
        raise PrivacyArtifactError("Privacy redactions are invalid.")
    return x_min, y_min, x_max, y_max


def _compose(after: Matrix3, before: Matrix3) -> NDArray[np.float64]:
    return np.asarray(after, dtype=np.float64).reshape(3, 3) @ np.asarray(
        before, dtype=np.float64
    ).reshape(3, 3)


def _apply_homography(
    matrix: NDArray[np.float64],
    x: float,
    y: float,
) -> tuple[float, float]:
    transformed = matrix @ np.asarray((x, y, 1.0), dtype=np.float64)
    denominator = float(transformed[2])
    if not np.isfinite(transformed).all() or abs(denominator) < 1e-12:
        raise PrivacyArtifactError("Privacy transform is invalid.")
    return float(transformed[0] / denominator), float(transformed[1] / denominator)


def _intersects_canvas(
    polygon: Sequence[tuple[float, float]],
    width: int,
    height: int,
) -> bool:
    x_values = [point[0] for point in polygon]
    y_values = [point[1] for point in polygon]
    return not (
        max(x_values) < 0
        or min(x_values) > width - 1
        or max(y_values) < 0
        or min(y_values) > height - 1
    )

