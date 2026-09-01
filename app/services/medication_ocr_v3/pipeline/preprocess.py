from __future__ import annotations

import hashlib
import io
import math
import struct
from dataclasses import dataclass, replace
from typing import Literal, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from app.services.medication_ocr_v3.domain.image import (
    CorrectionPreset,
    DocumentDetection,
    EncodedImage,
    ImageDimensions,
    ImageErrorCode,
    ImageQualityMetrics,
    ImageValidationError,
    Matrix3,
    MatrixTransform,
    Point,
    PreprocessingMode,
    PreprocessResult,
    PreviewImage,
    Quad,
    QualityState,
)
from app.services.medication_ocr_v3.pipeline.quality import build_metrics, measure_pixels, warp_quality_is_acceptable

MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_EDGE = 10_000
MAX_TEMPLATE_EDGE = 4096
MAX_PREVIEW_EDGE = 1600
MIN_SAFE_PERSPECTIVE_COVERAGE = 0.30
MAX_LOW_RESOLUTION_CROP_EVIDENCE_PIXELS = 200_000
MAX_PERSPECTIVE_GUARD_EDGE = 1280
PERSPECTIVE_OUTER_EDGE_EXCLUSION_FRACTION = 0.003
PERSPECTIVE_NEAR_OUTSIDE_BAND_FRACTION = 0.018
PERSPECTIVE_OUTSIDE_CONTENT_MIN_DENSITY = 0.006
PERSPECTIVE_OUTSIDE_CONTENT_MIN_PIXELS = 500
PERSPECTIVE_OUTSIDE_MIN_LOCAL_CONTRAST = 32
PERSPECTIVE_ADAPTIVE_TEXT_MIN_LOCAL_CONTRAST = 20
PERSPECTIVE_ADAPTIVE_TEXT_LINE_MIN_PIXELS = 80
PERSPECTIVE_ADAPTIVE_MAX_SURFACE_RESIDUAL_STD = 4.0
PERSPECTIVE_NEAR_SMALL_LINE_MIN_SUPPORT = 20
TRUSTED_OUTER_DOCUMENT_MIN_COVERAGE = 0.50
TRUSTED_OUTER_DOCUMENT_MIN_CONFIDENCE = 0.90
MAX_HOUGH_CLUSTERS_PER_AXIS = 12
MAX_HOUGH_PAIRS_PER_AXIS = 24
MAX_HOUGH_COMBINATIONS = 192
MULTIPLE_DOCUMENT_MIN_BOUNDARY_CONFIDENCE = 0.25
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_WHITE = (255, 255, 255)

type UInt8Image = NDArray[np.uint8]
type _CandidateProvenance = Literal["contour", "hough", "grabcut"]


@dataclass(frozen=True, slots=True)
class _QuadCandidate:
    quad: Quad
    confidence: float
    coverage: float
    crop_suspicion: bool
    boundary_confidence: float = 0.0
    provenance: _CandidateProvenance = "contour"


@dataclass(frozen=True, slots=True)
class _BuiltCandidate:
    rgb: UInt8Image
    oriented_to_candidate: MatrixTransform
    preprocessing_mode: PreprocessingMode
    rollback_reason: str | None


@dataclass(frozen=True, slots=True)
class _LineCluster:
    a: float
    b: float
    c: float
    position: float
    total_length: float
    longest_segment: float


@dataclass(frozen=True, slots=True)
class _DetectionColorBuffers:
    lab: UInt8Image
    hsv: UInt8Image
    lab_float: NDArray[np.float32]


def _matrix_tuple(matrix: NDArray[np.float64]) -> Matrix3:
    normalized = matrix / matrix[2, 2]
    return (
        float(normalized[0, 0]),
        float(normalized[0, 1]),
        float(normalized[0, 2]),
        float(normalized[1, 0]),
        float(normalized[1, 1]),
        float(normalized[1, 2]),
        float(normalized[2, 0]),
        float(normalized[2, 1]),
        float(normalized[2, 2]),
    )


def _as_array(matrix: Matrix3) -> NDArray[np.float64]:
    return np.asarray(matrix, dtype=np.float64).reshape(3, 3)


def _inverse(matrix: Matrix3) -> Matrix3:
    return _matrix_tuple(np.linalg.inv(_as_array(matrix)))


def _compose(after: Matrix3, before: Matrix3) -> Matrix3:
    return _matrix_tuple(_as_array(after) @ _as_array(before))


def apply_matrix(matrix: tuple[float, ...], point: Point) -> Point:
    if len(matrix) != 9:
        raise ValueError("A homogeneous transform must contain nine values.")
    values = np.asarray(matrix, dtype=np.float64).reshape(3, 3)
    mapped = values @ np.asarray((point.x, point.y, 1.0), dtype=np.float64)
    if abs(float(mapped[2])) < 1e-12:
        raise ValueError("The transform maps the point to infinity.")
    return Point(float(mapped[0] / mapped[2]), float(mapped[1] / mapped[2]))


def _transform(
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
    matrix: Matrix3,
) -> MatrixTransform:
    return MatrixTransform(
        source_width=source_width,
        source_height=source_height,
        target_width=target_width,
        target_height=target_height,
        matrix=matrix,
        inverse=_inverse(matrix),
    )


def exif_orientation_matrix(width: int, height: int, orientation: int) -> MatrixTransform:
    matrices: dict[int, tuple[Matrix3, tuple[int, int]]] = {
        1: ((1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), (width, height)),
        2: ((-1.0, 0.0, float(width), 0.0, 1.0, 0.0, 0.0, 0.0, 1.0), (width, height)),
        3: (
            (-1.0, 0.0, float(width), 0.0, -1.0, float(height), 0.0, 0.0, 1.0),
            (width, height),
        ),
        4: ((1.0, 0.0, 0.0, 0.0, -1.0, float(height), 0.0, 0.0, 1.0), (width, height)),
        5: ((0.0, 1.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0), (height, width)),
        6: (
            (0.0, -1.0, float(height), 1.0, 0.0, 0.0, 0.0, 0.0, 1.0),
            (height, width),
        ),
        7: (
            (0.0, -1.0, float(height), -1.0, 0.0, float(width), 0.0, 0.0, 1.0),
            (height, width),
        ),
        8: ((0.0, 1.0, 0.0, -1.0, 0.0, float(width), 0.0, 0.0, 1.0), (height, width)),
    }
    matrix, target = matrices.get(orientation, matrices[1])
    return _transform(width, height, target[0], target[1], matrix)


def rotation_matrix_clockwise(width: int, height: int, degrees: int) -> MatrixTransform:
    if degrees not in {0, 90, 180, 270}:
        raise ImageValidationError(
            ImageErrorCode.INVALID_ROTATION,
            "Rotation must be one of 0, 90, 180, or 270 degrees.",
        )
    return exif_orientation_matrix(width, height, {0: 1, 90: 6, 180: 3, 270: 8}[degrees])


def resize_matrix(
    source_width: int, source_height: int, target_width: int, target_height: int
) -> MatrixTransform:
    if min(source_width, source_height, target_width, target_height) <= 0:
        raise ValueError("Image dimensions must be positive.")
    matrix: Matrix3 = (
        target_width / source_width,
        0.0,
        0.0,
        0.0,
        target_height / source_height,
        0.0,
        0.0,
        0.0,
        1.0,
    )
    return _transform(source_width, source_height, target_width, target_height, matrix)


def _quad_array(quad: Quad) -> NDArray[np.float32]:
    return np.asarray([(point.x, point.y) for point in quad], dtype=np.float32)


def _signed_area(quad: Quad) -> float:
    points = _quad_array(quad).astype(np.float64)
    return float(
        0.5
        * np.sum(
            points[:, 0] * np.roll(points[:, 1], -1) - points[:, 1] * np.roll(points[:, 0], -1)
        )
    )


def _is_valid_quad(quad: Quad, *, minimum_area: float = 16.0) -> bool:
    points = _quad_array(quad)
    contour = points.reshape((-1, 1, 2))
    return bool(
        bool(np.isfinite(points).all())
        and cv2.isContourConvex(contour)
        and abs(_signed_area(quad)) >= minimum_area
    )


def perspective_matrix(
    quad: Quad, *, target_width: int, target_height: int, border: int = 0
) -> MatrixTransform:
    if not _is_valid_quad(quad) or min(target_width, target_height) < 2 or border < 0:
        raise ValueError("A non-degenerate convex quadrilateral is required.")
    destination = np.asarray(
        [
            (border, border),
            (border + target_width, border),
            (border + target_width, border + target_height),
            (border, border + target_height),
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(_quad_array(quad), destination)
    values = _matrix_tuple(matrix.astype(np.float64))
    source_width = max(1, math.ceil(max(point.x for point in quad)))
    source_height = max(1, math.ceil(max(point.y for point in quad)))
    return _transform(
        source_width,
        source_height,
        target_width + 2 * border,
        target_height + 2 * border,
        values,
    )


def _source_kind(data: bytes) -> str | None:
    if data.startswith(_PNG_SIGNATURE):
        return "PNG"
    if data.startswith(_JPEG_SIGNATURE):
        return "JPEG"
    return None


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 29 or data[8:12] != struct.pack(">I", 13) or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    position = 2
    sof_markers = {
        0xC0,
        0xC1,
        0xC2,
        0xC3,
        0xC5,
        0xC6,
        0xC7,
        0xC9,
        0xCA,
        0xCB,
        0xCD,
        0xCE,
        0xCF,
    }
    while position + 3 < len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            return None
        marker = data[position]
        position += 1
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > len(data):
            return None
        length = int.from_bytes(data[position : position + 2], "big")
        if length < 2 or position + length > len(data):
            return None
        if marker in sof_markers and length >= 7:
            height = int.from_bytes(data[position + 3 : position + 5], "big")
            width = int.from_bytes(data[position + 5 : position + 7], "big")
            return width, height
        position += length
    return None


def _metadata_dimensions(data: bytes, kind: str) -> tuple[int, int] | None:
    return _png_dimensions(data) if kind == "PNG" else _jpeg_dimensions(data)


def _enforce_dimensions(width: int, height: int) -> None:
    if max(width, height) > MAX_EDGE:
        raise ImageValidationError(
            ImageErrorCode.EDGE_LIMIT_EXCEEDED,
            "The image edge exceeds the supported limit.",
        )
    if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
        raise ImageValidationError(
            ImageErrorCode.PIXEL_LIMIT_EXCEEDED,
            "The decoded image exceeds the supported pixel limit.",
        )


def _decode_image(data: bytes, mime_type: str) -> tuple[Image.Image, str, int]:
    if len(data) > MAX_SOURCE_BYTES:
        raise ImageValidationError(
            ImageErrorCode.SOURCE_TOO_LARGE,
            "The image exceeds the supported byte limit.",
        )
    kind = _source_kind(data)
    if kind is None:
        raise ImageValidationError(
            ImageErrorCode.UNSUPPORTED_IMAGE,
            "Only a valid JPEG or PNG image is supported.",
        )
    expected_mime = "image/jpeg" if kind == "JPEG" else "image/png"
    if mime_type.strip().lower() != expected_mime:
        raise ImageValidationError(
            ImageErrorCode.MIME_MISMATCH,
            "The declared media type does not match the image data.",
        )
    dimensions = _metadata_dimensions(data, kind)
    if dimensions is not None:
        _enforce_dimensions(*dimensions)

    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format != kind:
                raise ImageValidationError(
                    ImageErrorCode.MIME_MISMATCH,
                    "The decoded format does not match the image data.",
                )
            if (
                bool(getattr(probe, "is_animated", False))
                or int(getattr(probe, "n_frames", 1)) != 1
            ):
                raise ImageValidationError(
                    ImageErrorCode.ANIMATED_IMAGE,
                    "Animated or multi-frame images are not supported.",
                )
            _enforce_dimensions(*probe.size)
        with Image.open(io.BytesIO(data)) as verifier:
            verifier.verify()
        with Image.open(io.BytesIO(data)) as decoded:
            orientation = int(decoded.getexif().get(274, 1))
            decoded.load()
            copied = decoded.copy()
    except ImageValidationError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
    ) as error:
        raise ImageValidationError(
            ImageErrorCode.CORRUPT_IMAGE,
            "The image could not be decoded safely.",
        ) from error
    return copied, kind, orientation if 1 <= orientation <= 8 else 1


def _order_quad(points: NDArray[np.float32]) -> Quad:
    center = np.mean(points, axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    ordered = points[np.argsort(angles)]
    start = int(np.argmin(ordered[:, 0] + ordered[:, 1]))
    ordered = np.roll(ordered, -start, axis=0)
    quad = cast(Quad, tuple(Point(float(x), float(y)) for x, y in ordered))
    if _signed_area(quad) < 0:
        quad = (quad[0], quad[3], quad[2], quad[1])
    return quad


def _angle_score(quad: Quad) -> float:
    points = _quad_array(quad).astype(np.float64)
    scores: list[float] = []
    for index in range(4):
        previous = points[(index - 1) % 4] - points[index]
        following = points[(index + 1) % 4] - points[index]
        denominator = np.linalg.norm(previous) * np.linalg.norm(following)
        if denominator <= 1e-9:
            return 0.0
        scores.append(1.0 - min(1.0, abs(float(np.dot(previous, following) / denominator))))
    return float(np.mean(scores))


def _detection_color_buffers(rgb: UInt8Image) -> _DetectionColorBuffers:
    lab = cast(UInt8Image, cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB))
    return _DetectionColorBuffers(
        lab=lab,
        hsv=cast(UInt8Image, cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)),
        lab_float=lab.astype(np.float32),
    )


def _boundary_contrast(lab: NDArray[np.float32], quad: Quad) -> tuple[float, float]:
    height, width = lab.shape[:2]
    offset = max(4.0, min(width, height) * 0.006)
    side_scores: list[float] = []
    for index in range(4):
        first = quad[index]
        second = quad[(index + 1) % 4]
        dx = second.x - first.x
        dy = second.y - first.y
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            return 0.0, 0.0
        inward_x = -dy / length
        inward_y = dx / length
        differences: list[NDArray[np.float32]] = []
        for ratio in np.linspace(0.08, 0.92, 28):
            x = first.x + float(ratio) * dx
            y = first.y + float(ratio) * dy
            inside_x = round(x + inward_x * offset)
            inside_y = round(y + inward_y * offset)
            outside_x = round(x - inward_x * offset)
            outside_y = round(y - inward_y * offset)
            if not (
                0 <= inside_x < width
                and 0 <= inside_y < height
                and 0 <= outside_x < width
                and 0 <= outside_y < height
            ):
                continue
            radius = 3
            inside_patch = lab[
                max(0, inside_y - radius) : min(height, inside_y + radius + 1),
                max(0, inside_x - radius) : min(width, inside_x + radius + 1),
            ]
            outside_patch = lab[
                max(0, outside_y - radius) : min(height, outside_y + radius + 1),
                max(0, outside_x - radius) : min(width, outside_x + radius + 1),
            ]
            delta = np.mean(inside_patch, axis=(0, 1)) - np.mean(outside_patch, axis=(0, 1))
            differences.append(delta.astype(np.float32))
        if differences:
            consistent_delta = np.mean(np.stack(differences), axis=0)
            side_scores.append(float(np.linalg.norm(consistent_delta) / 255.0))
        else:
            side_scores.append(0.0)
    return float(np.mean(side_scores)), min(side_scores)


def _crop_suspicion(quad: Quad, width: int, height: int) -> bool:
    margin = max(3.0, min(width, height) * 0.006)
    touching = sum(
        point.x <= margin
        or point.y <= margin
        or point.x >= width - margin
        or point.y >= height - margin
        for point in quad
    )
    return touching >= 2


def _stabilize_document_detection(
    detection: DocumentDetection,
    width: int,
    height: int,
) -> DocumentDetection:
    """Discard implausible auto-detected geometry before quality classification."""

    quad = detection.polygon
    if quad is None:
        return detection

    coverage = abs(_signed_area(quad)) / float(width * height)
    horizontal_span = (max(point.x for point in quad) - min(point.x for point in quad)) / width
    vertical_span = (max(point.y for point in quad) - min(point.y for point in quad)) / height
    if (
        detection.likely_document_count == 0
        and coverage < 0.075
        and min(horizontal_span, vertical_span) < 0.08
    ):
        return DocumentDetection(None, 0, 0.0, False)

    if not detection.crop_suspicion or detection.confidence >= 0.75:
        return detection

    def length(first: Point, second: Point) -> float:
        return math.hypot(second.x - first.x, second.y - first.y)

    top = length(quad[0], quad[1])
    right = length(quad[1], quad[2])
    bottom = length(quad[2], quad[3])
    left = length(quad[3], quad[0])
    opposing_edge_ratio = min(
        min(top, bottom) / max(top, bottom, 1.0),
        min(left, right) / max(left, right, 1.0),
    )
    if opposing_edge_ratio >= 0.35:
        return detection
    return DocumentDetection(None, detection.likely_document_count, 0.0, False)


def _candidate_from_contour(
    contour: NDArray[np.int32],
    rgb: UInt8Image,
    width: int,
    height: int,
    color_buffers: _DetectionColorBuffers | None = None,
) -> list[_QuadCandidate]:
    contour_area = float(cv2.contourArea(contour))
    image_area = float(width * height)
    if contour_area < image_area * 0.004:
        return []
    hull = cv2.convexHull(contour)
    perimeter = cv2.arcLength(hull, True)
    approximations: list[NDArray[np.float32]] = []
    for epsilon in (0.012, 0.018, 0.025, 0.035, 0.05, 0.07):
        approximation = cv2.approxPolyDP(hull, epsilon * perimeter, True)
        if len(approximation) == 4:
            approximations.append(approximation.reshape(4, 2).astype(np.float32))
    if not approximations:
        rectangle = cv2.minAreaRect(hull)
        box = cv2.boxPoints(rectangle)
        rectangle_area = float(cv2.contourArea(box))
        if rectangle_area > 0 and contour_area / rectangle_area >= 0.72:
            approximations.append(box.astype(np.float32))

    colors = color_buffers or _detection_color_buffers(rgb)
    results: list[_QuadCandidate] = []
    for approximation in approximations:
        quad = _order_quad(approximation)
        if not _is_valid_quad(quad, minimum_area=image_area * 0.003):
            continue
        area = abs(_signed_area(quad))
        coverage = area / image_area
        if coverage > 0.96:
            continue
        crop = _crop_suspicion(quad, width, height)
        mask = np.zeros((height, width), dtype=np.uint8)
        cv2.fillConvexPoly(mask, _quad_array(quad).astype(np.int32), 255)
        selected = mask > 0
        lightness = float(np.mean(colors.lab[..., 0][selected]) / 255.0)
        saturation = float(np.mean(colors.hsv[..., 1][selected]) / 255.0)
        page_score = float(np.clip(lightness - 0.45 * saturation, 0.0, 1.0))
        rectangularity = min(1.0, contour_area / max(area, 1.0))
        geometry = _angle_score(quad)
        area_score = min(1.0, coverage / 0.20)
        boundary_contrast, _ = _boundary_contrast(colors.lab_float, quad)
        boundary_score = min(1.0, boundary_contrast / 0.16)
        confidence = float(
            np.clip(
                0.28 * geometry
                + 0.20 * rectangularity
                + 0.18 * page_score
                + 0.12 * area_score
                + 0.22 * boundary_score
                - (0.18 if crop else 0.0),
                0.0,
                1.0,
            )
        )
        results.append(_QuadCandidate(quad, confidence, coverage, crop, boundary_score))
    return results


def _fit_line_clusters(
    segments: list[tuple[float, float, float, float, float, float]],
    tolerance: float,
) -> list[_LineCluster]:
    grouped: list[list[tuple[float, float, float, float, float, float]]] = []
    for segment in sorted(segments, key=lambda item: item[5]):
        if not grouped or segment[5] - grouped[-1][-1][5] > tolerance:
            grouped.append([segment])
        else:
            grouped[-1].append(segment)
    clusters: list[_LineCluster] = []
    for group in grouped:
        points = np.asarray(
            [(x1, y1) for x1, y1, _, _, _, _ in group] + [(x2, y2) for _, _, x2, y2, _, _ in group],
            dtype=np.float32,
        )
        fitted = np.asarray(cv2.fitLine(points, cv2.DIST_L2, 0, 0.01, 0.01)).reshape(-1)
        vx, vy, x0, y0 = (float(value) for value in fitted)
        a = vy
        b = -vx
        norm = math.hypot(a, b)
        if norm <= 1e-9:
            continue
        a /= norm
        b /= norm
        c = -(a * x0 + b * y0)
        total_length = sum(item[4] for item in group)
        clusters.append(
            _LineCluster(
                a=a,
                b=b,
                c=c,
                position=sum(item[5] * item[4] for item in group) / total_length,
                total_length=total_length,
                longest_segment=max(item[4] for item in group),
            )
        )
    return clusters


def _line_intersection(first: _LineCluster, second: _LineCluster) -> Point | None:
    determinant = first.a * second.b - second.a * first.b
    if abs(determinant) < 1e-6:
        return None
    x = (first.b * second.c - second.b * first.c) / determinant
    y = (first.c * second.a - second.c * first.a) / determinant
    if not math.isfinite(x) or not math.isfinite(y):
        return None
    return Point(x, y)


def _rank_line_pairs(
    clusters: list[_LineCluster], minimum_separation: float, axis_extent: int
) -> set[tuple[_LineCluster, _LineCluster]]:
    ranked: list[tuple[float, _LineCluster, _LineCluster]] = []
    for first in clusters:
        for second in clusters:
            separation = second.position - first.position
            if separation < minimum_separation:
                continue
            span_score = min(1.0, separation / max(1.0, axis_extent * 0.55))
            support = (
                first.longest_segment
                + second.longest_segment
                + 0.20 * (first.total_length + second.total_length)
            )
            ranked.append((support * (0.85 + 0.15 * span_score), first, second))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return {
        (first, second)
        for _, first, second in ranked[:MAX_HOUGH_PAIRS_PER_AXIS]
    }


def _expand_quad(quad: Quad, width: int, height: int) -> Quad:
    margin = max(width, height) * 0.01
    offset_lines: list[_LineCluster] = []
    for index in range(4):
        first = quad[index]
        second = quad[(index + 1) % 4]
        dx = second.x - first.x
        dy = second.y - first.y
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            return quad
        a = dy / length
        b = -dx / length
        c = -(a * first.x + b * first.y) - margin
        offset_lines.append(_LineCluster(a, b, c, 0.0, 0.0, 0.0))
    intersections = (
        _line_intersection(offset_lines[3], offset_lines[0]),
        _line_intersection(offset_lines[0], offset_lines[1]),
        _line_intersection(offset_lines[1], offset_lines[2]),
        _line_intersection(offset_lines[2], offset_lines[3]),
    )
    if any(point is None for point in intersections):
        return quad
    expanded = cast(
        Quad,
        tuple(
            Point(
                float(np.clip(point.x, 0.0, float(width))),
                float(np.clip(point.y, 0.0, float(height))),
            )
            for point in intersections
            if point is not None
        ),
    )
    original_area = abs(_signed_area(quad))
    expanded_area = abs(_signed_area(expanded))
    if (
        not _is_valid_quad(expanded, minimum_area=original_area)
        or expanded_area > width * height * 0.93
        or expanded_area > original_area * 1.28
    ):
        return quad
    return expanded


def _edge_side_support(edges: UInt8Image, first: Point, second: Point) -> float:
    length = math.hypot(second.x - first.x, second.y - first.y)
    samples = max(32, min(240, round(length / 5.0)))
    height, width = edges.shape[:2]
    supported = 0
    for ratio in np.linspace(0.0, 1.0, samples):
        x = round(first.x + float(ratio) * (second.x - first.x))
        y = round(first.y + float(ratio) * (second.y - first.y))
        x1 = max(0, x - 3)
        y1 = max(0, y - 3)
        x2 = min(width, x + 4)
        y2 = min(height, y + 4)
        if x1 < x2 and y1 < y2 and bool(np.any(edges[y1:y2, x1:x2] > 0)):
            supported += 1
    return supported / samples


def _hough_candidate(
    edges: UInt8Image,
    rgb: UInt8Image,
    width: int,
    height: int,
    color_buffers: _DetectionColorBuffers | None = None,
) -> _QuadCandidate | None:
    colors = color_buffers or _detection_color_buffers(rgb)
    minimum = max(60, int(min(width, height) * 0.24))
    raw_lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=max(45, minimum // 3),
        minLineLength=minimum,
        maxLineGap=max(12, min(width, height) // 25),
    )
    if raw_lines is None:
        return None
    horizontal: list[tuple[float, float, float, float, float, float]] = []
    vertical: list[tuple[float, float, float, float, float, float]] = []
    for x1, y1, x2, y2 in raw_lines.reshape((-1, 4)):
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        length = math.hypot(dx, dy)
        angle = abs(math.degrees(math.atan2(dy, dx))) % 180.0
        if min(angle, 180.0 - angle) <= 11.0 and abs(dx) > 1e-6:
            center_position = float(y1) + (width / 2.0 - float(x1)) * dy / dx
            horizontal.append((float(x1), float(y1), float(x2), float(y2), length, center_position))
        elif abs(angle - 90.0) <= 11.0 and abs(dy) > 1e-6:
            center_position = float(x1) + (height / 2.0 - float(y1)) * dx / dy
            vertical.append((float(x1), float(y1), float(x2), float(y2), length, center_position))
    h_clusters = sorted(
        _fit_line_clusters(horizontal, max(7.0, height * 0.012)),
        key=lambda cluster: (cluster.longest_segment, cluster.total_length),
        reverse=True,
    )[:MAX_HOUGH_CLUSTERS_PER_AXIS]
    v_clusters = sorted(
        _fit_line_clusters(vertical, max(7.0, width * 0.012)),
        key=lambda cluster: (cluster.longest_segment, cluster.total_length),
        reverse=True,
    )[:MAX_HOUGH_CLUSTERS_PER_AXIS]
    horizontal_pairs = _rank_line_pairs(h_clusters, height * 0.25, height)
    vertical_pairs = _rank_line_pairs(v_clusters, width * 0.25, width)
    best: tuple[float, _QuadCandidate] | None = None
    evaluated = 0
    for top in h_clusters:
        for bottom in h_clusters:
            if (top, bottom) not in horizontal_pairs:
                continue
            for left in v_clusters:
                for right in v_clusters:
                    if (left, right) not in vertical_pairs:
                        continue
                    if evaluated >= MAX_HOUGH_COMBINATIONS:
                        continue
                    evaluated += 1
                    intersections = (
                        _line_intersection(top, left),
                        _line_intersection(top, right),
                        _line_intersection(bottom, right),
                        _line_intersection(bottom, left),
                    )
                    if any(point is None for point in intersections):
                        continue
                    quad = cast(Quad, intersections)
                    if not _is_valid_quad(quad, minimum_area=width * height * 0.10):
                        continue
                    coverage = abs(_signed_area(quad)) / (width * height)
                    if not 0.12 <= coverage <= 0.82:
                        continue
                    xs = [point.x for point in quad]
                    ys = [point.y for point in quad]
                    if (
                        min(xs) < width * 0.04
                        or max(xs) > width * 0.96
                        or min(ys) < height * 0.04
                        or max(ys) > height * 0.98
                    ):
                        continue
                    side_lengths = (
                        math.hypot(quad[1].x - quad[0].x, quad[1].y - quad[0].y),
                        math.hypot(quad[2].x - quad[1].x, quad[2].y - quad[1].y),
                        math.hypot(quad[3].x - quad[2].x, quad[3].y - quad[2].y),
                        math.hypot(quad[0].x - quad[3].x, quad[0].y - quad[3].y),
                    )
                    edge_supports = tuple(
                        _edge_side_support(edges, quad[index], quad[(index + 1) % 4])
                        for index in range(4)
                    )
                    if min(edge_supports) < 0.42 or float(np.mean(edge_supports)) < 0.60:
                        continue
                    boundary_contrast, minimum_boundary_contrast = _boundary_contrast(
                        colors.lab_float,
                        quad,
                    )
                    if minimum_boundary_contrast < 0.012 or boundary_contrast < 0.025:
                        continue
                    span_support = min(
                        1.0,
                        min(
                            top.longest_segment / side_lengths[0],
                            right.longest_segment / side_lengths[1],
                            bottom.longest_segment / side_lengths[2],
                            left.longest_segment / side_lengths[3],
                        )
                        / 0.45,
                    )
                    coverage_prior = max(0.0, 1.0 - abs(coverage - 0.53) / 0.35)
                    boundary_score = min(1.0, boundary_contrast / 0.14)
                    maximum_width_ratio = max(side_lengths[0], side_lengths[2]) / width
                    wide_penalty = max(0.0, (maximum_width_ratio - 0.82) / 0.18)
                    horizontal_margin = min(min(xs), width - max(xs)) / width
                    border_penalty = max(0.0, (0.07 - horizontal_margin) / 0.07)
                    confidence = float(
                        np.clip(
                            0.35 * float(np.mean(edge_supports))
                            + 0.30 * boundary_score
                            + 0.15 * _angle_score(quad)
                            + 0.12 * span_support
                            + 0.08 * coverage_prior
                            - 0.16 * wide_penalty
                            - 0.12 * border_penalty,
                            0.0,
                            0.90,
                        )
                    )
                    score = confidence + 0.10 * coverage_prior
                    candidate = _QuadCandidate(
                        quad,
                        confidence,
                        coverage,
                        False,
                        boundary_score,
                        "hough",
                    )
                    if best is None or score > best[0]:
                        best = score, candidate
    return None if best is None else best[1]


def _quad_overlap(first: Quad, second: Quad) -> float:
    first_array = _quad_array(first)
    second_array = _quad_array(second)
    intersection, _ = cv2.intersectConvexConvex(first_array, second_array)
    smaller = min(abs(_signed_area(first)), abs(_signed_area(second)))
    return float(intersection / smaller) if smaller > 0 else 0.0


def _group_nested_candidates(
    candidates: list[_QuadCandidate],
) -> list[list[_QuadCandidate]]:
    groups: list[list[_QuadCandidate]] = []
    for candidate in candidates:
        matching = [
            index
            for index, group in enumerate(groups)
            if any(_quad_overlap(candidate.quad, existing.quad) >= 0.55 for existing in group)
        ]
        if not matching:
            groups.append([candidate])
            continue
        target = groups[matching[0]]
        target.append(candidate)
        for index in reversed(matching[1:]):
            target.extend(groups.pop(index))
    return groups


def _document_authority(group: list[_QuadCandidate]) -> _QuadCandidate:
    highest_confidence = max(candidate.confidence for candidate in group)
    enclosing = [
        candidate
        for candidate in group
        if candidate.confidence >= max(0.50, highest_confidence * 0.62)
        and candidate.boundary_confidence >= 0.12
        and 0.08 <= candidate.coverage <= 0.92
    ]
    if enclosing:
        return max(enclosing, key=lambda candidate: candidate.coverage)
    return max(
        group,
        key=lambda candidate: (
            0.76 * candidate.confidence
            + 0.18 * max(0.0, 1.0 - abs(candidate.coverage - 0.53) / 0.45)
            + 0.06 * min(1.0, candidate.coverage / 0.20)
        ),
    )


def _grabcut_document_candidates(
    rgb: UInt8Image,
    color_buffers: _DetectionColorBuffers | None = None,
) -> list[_QuadCandidate]:
    original_height, original_width = rgb.shape[:2]
    scale = min(1.0, 800.0 / max(original_width, original_height))
    if scale < 1.0:
        working = cast(
            UInt8Image,
            cv2.resize(
                rgb,
                (round(original_width * scale), round(original_height * scale)),
                interpolation=cv2.INTER_AREA,
            ),
        )
    else:
        working = rgb
    height, width = working.shape[:2]
    margin_x = max(3, round(width * 0.035))
    margin_y = max(3, round(height * 0.035))
    rectangle = (
        margin_x,
        margin_y,
        max(2, width - 2 * margin_x),
        max(2, height - 2 * margin_y),
    )
    mask = np.zeros((height, width), dtype=np.uint8)
    background_model = np.zeros((1, 65), dtype=np.float64)
    foreground_model = np.zeros((1, 65), dtype=np.float64)
    try:
        cv2.setRNGSeed(1337)
        cv2.grabCut(
            cv2.cvtColor(working, cv2.COLOR_RGB2BGR),
            mask,
            rectangle,
            background_model,
            foreground_model,
            4,
            cv2.GC_INIT_WITH_RECT,
        )
    except cv2.error:
        return []
    foreground = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    kernel_size = max(5, (min(width, height) // 90) | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    foreground = cast(
        UInt8Image,
        cv2.morphologyEx(foreground, cv2.MORPH_CLOSE, kernel, iterations=2),
    )
    foreground = cast(
        UInt8Image,
        cv2.morphologyEx(foreground, cv2.MORPH_OPEN, kernel),
    )
    contours, _ = cv2.findContours(foreground, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates: list[_QuadCandidate] = []
    colors = (
        color_buffers
        if working is rgb and color_buffers is not None
        else _detection_color_buffers(working)
    )
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:4]:
        if cv2.contourArea(contour) < width * height * 0.08:
            continue
        detected = _candidate_from_contour(
            cast(NDArray[np.int32], contour),
            working,
            width,
            height,
            colors,
        )
        for candidate in detected:
            factor = 1.0 / scale
            quad = cast(
                Quad,
                tuple(Point(point.x * factor, point.y * factor) for point in candidate.quad),
            )
            candidates.append(
                _QuadCandidate(
                    quad=quad,
                    confidence=min(0.97, candidate.confidence + 0.08),
                    coverage=candidate.coverage,
                    crop_suspicion=candidate.crop_suspicion,
                    boundary_confidence=candidate.boundary_confidence,
                    provenance="grabcut",
                )
            )
    return candidates


def _three_sided_flat_crop_evidence(gray: UInt8Image) -> list[Quad]:
    """Find a flat enclosing surface whose fourth side continues beyond one frame edge."""
    height, width = gray.shape
    gradient = cast(
        UInt8Image,
        cv2.morphologyEx(
            gray,
            cv2.MORPH_GRADIENT,
            cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
        ),
    )
    flat_mask = np.where(
        (gradient <= 10) & (gray >= 72) & (gray < 135),
        255,
        0,
    ).astype(np.uint8)
    close_size = max(9, (min(width, height) // 50) | 1)
    flat_mask = cast(
        UInt8Image,
        cv2.morphologyEx(
            flat_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (close_size, close_size)),
            iterations=2,
        ),
    )
    flat_mask = cast(
        UInt8Image,
        cv2.morphologyEx(
            flat_mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
        ),
    )
    boundary = cast(
        UInt8Image,
        cv2.morphologyEx(
            flat_mask,
            cv2.MORPH_GRADIENT,
            cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        ),
    )
    contours, _ = cv2.findContours(flat_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    evidence: list[Quad] = []
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:6]:
        x, y, component_width, component_height = cv2.boundingRect(contour)
        coverage = float(cv2.contourArea(contour)) / float(width * height)
        hull = cv2.convexHull(contour)
        approximation = cv2.approxPolyDP(hull, 0.02 * cv2.arcLength(hull, True), True)
        if len(approximation) == 4:
            quad = _order_quad(approximation.reshape(4, 2).astype(np.float32))
        else:
            quad = (
                Point(float(x), float(y)),
                Point(float(x + component_width), float(y)),
                Point(float(x + component_width), float(y + component_height)),
                Point(float(x), float(y + component_height)),
            )
        xs = [point.x for point in quad]
        ys = [point.y for point in quad]
        touches = (
            min(xs) <= 1,
            min(ys) <= 1,
            max(xs) >= width - 1,
            max(ys) >= height - 1,
        )
        if (
            sum(touches) != 1
            or not 0.15 <= coverage <= 0.90
            or component_width < width * 0.35
            or component_height < height * 0.35
        ):
            continue
        surface_luminance = float(
            np.percentile(
                gray[y : y + component_height, x : x + component_width],
                30,
            )
        )
        if surface_luminance >= 135.0:
            continue
        touched_side = (3, 0, 1, 2)[touches.index(True)]
        supported_sides = [
            _edge_side_support(boundary, quad[index], quad[(index + 1) % 4])
            for index in range(4)
            if index != touched_side
        ]
        if min(supported_sides) >= 0.60:
            evidence.append(quad)
    return evidence


def _detect_document(rgb: UInt8Image) -> DocumentDetection:
    original_height, original_width = rgb.shape[:2]
    scale = min(1.0, 1400.0 / max(original_width, original_height))
    working: UInt8Image
    if scale < 1.0:
        working = cast(
            UInt8Image,
            cv2.resize(
                rgb,
                (round(original_width * scale), round(original_height * scale)),
                interpolation=cv2.INTER_AREA,
            ),
        )
    else:
        working = rgb
    height, width = working.shape[:2]
    gray = cast(UInt8Image, cv2.cvtColor(working, cv2.COLOR_RGB2GRAY))
    colors = _detection_color_buffers(working)
    median = float(np.median(gray))
    canny = cast(
        UInt8Image,
        cv2.Canny(gray, int(max(20, median * 0.55)), int(min(245, median * 1.45))),
    )
    edge_mask = cast(
        UInt8Image,
        cv2.morphologyEx(
            canny,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
            iterations=2,
        ),
    )
    value_threshold = int(max(135.0, np.percentile(colors.hsv[..., 2], 62)))
    page_mask: UInt8Image = np.where(
        (colors.hsv[..., 2] >= value_threshold) & (colors.hsv[..., 1] <= 95), 255, 0
    ).astype(np.uint8)
    kernel_size = max(5, (min(width, height) // 70) | 1)
    page_mask = cast(
        UInt8Image,
        cv2.morphologyEx(
            page_mask,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size)),
            iterations=2,
        ),
    )
    page_mask = cast(
        UInt8Image,
        cv2.morphologyEx(
            page_mask,
            cv2.MORPH_OPEN,
            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)),
        ),
    )
    component_count = 0
    component_crop_quads: list[Quad] = []
    component_total, _, component_stats, _ = cv2.connectedComponentsWithStats(
        page_mask, connectivity=8
    )
    for component_index in range(1, component_total):
        x, y, component_width, component_height, component_area = component_stats[component_index]
        component_coverage = float(component_area) / float(width * height)
        touches_border = (
            x <= 1
            or y <= 1
            or x + component_width >= width - 1
            or y + component_height >= height - 1
        )
        if (
            touches_border
            and 0.15 <= component_coverage <= 0.88
            and component_width >= width * 0.30
            and component_height >= height * 0.30
        ):
            component_crop_quads.append(
                (
                    Point(float(x), float(y)),
                    Point(float(x + component_width), float(y)),
                    Point(float(x + component_width), float(y + component_height)),
                    Point(float(x), float(y + component_height)),
                )
            )
        if (
            0.06 <= component_coverage <= 0.85
            and component_width >= width * 0.18
            and component_height >= height * 0.18
            and not touches_border
        ):
            component_count += 1

    candidates: list[_QuadCandidate] = []
    for mask in (edge_mask, page_mask):
        contours, _ = cv2.findContours(mask, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            candidates.extend(
                _candidate_from_contour(
                    cast(NDArray[np.int32], contour),
                    working,
                    width,
                    height,
                    colors,
                )
            )
    hough = _hough_candidate(canny, working, width, height, colors)
    if hough is not None:
        candidates.append(hough)
    if not candidates or max(candidate.confidence for candidate in candidates) < 0.82:
        candidates.extend(_grabcut_document_candidates(working, colors))

    groups = _group_nested_candidates(candidates)
    authorities = [_document_authority(group) for group in groups]
    strong = [
        candidate
        for candidate in authorities
        if candidate.coverage >= 0.075
        and candidate.confidence >= 0.55
        and candidate.boundary_confidence
        >= MULTIPLE_DOCUMENT_MIN_BOUNDARY_CONFIDENCE
    ]
    likely_count = max(len(strong), component_count)
    plausible = [candidate for candidate in authorities if candidate.confidence >= 0.42]
    if not plausible:
        return DocumentDetection(None, 0, 0.0, False)
    best = max(
        plausible,
        key=lambda candidate: (
            0.76 * candidate.confidence
            + 0.18 * max(0.0, 1.0 - abs(candidate.coverage - 0.53) / 0.45)
            + 0.06 * min(1.0, candidate.coverage / 0.20)
        ),
    )
    best_group = next(group for group in groups if best in group)
    factor = 1.0 / scale
    quad = cast(
        Quad,
        tuple(Point(point.x * factor, point.y * factor) for point in best.quad),
    )
    quad = _expand_quad(quad, original_width, original_height)
    crop_evidence = [
        candidate.quad
        for candidate in best_group
        if candidate.crop_suspicion and candidate.coverage >= 0.15 and candidate.confidence >= 0.40
    ] + component_crop_quads
    matching_pre_expansion_crop = any(
        _quad_overlap(best.quad, evidence) >= 0.65
        and 0.60 <= abs(_signed_area(evidence)) / max(abs(_signed_area(best.quad)), 1.0) <= 1.50
        for evidence in crop_evidence
    )
    enclosing_component_crop = (
        original_width * original_height < MAX_LOW_RESOLUTION_CROP_EVIDENCE_PIXELS
        and (best.confidence < 0.90 or best.provenance == "grabcut")
    ) and any(
        _quad_overlap(best.quad, evidence) >= 0.90
        and 1.35
        <= abs(_signed_area(evidence)) / max(abs(_signed_area(best.quad)), 1.0)
        <= 6.0
        for evidence in component_crop_quads
    )
    enclosing_three_side_crop = (
        best.confidence < 0.90 or best.provenance == "hough"
    ) and any(
        _quad_overlap(best.quad, evidence) >= 0.90
        and 1.35
        <= abs(_signed_area(evidence)) / max(abs(_signed_area(best.quad)), 1.0)
        <= 6.0
        for evidence in _three_sided_flat_crop_evidence(gray)
    )
    if (
        original_width * original_height
        >= MAX_LOW_RESOLUTION_CROP_EVIDENCE_PIXELS
        and best.confidence < 0.70
        and matching_pre_expansion_crop
        and not best.crop_suspicion
        and not enclosing_three_side_crop
    ):
        return DocumentDetection(None, likely_count, 0.0, False)
    return DocumentDetection(
        quad,
        likely_count,
        best.confidence,
        best.crop_suspicion
        or enclosing_component_crop
        or enclosing_three_side_crop
        or (best.confidence < 0.70 and matching_pre_expansion_crop),
    )


def _quad_geometry(quad: Quad, width: int, height: int) -> tuple[float, float]:
    coverage = abs(_signed_area(quad)) / float(width * height)
    top = math.degrees(math.atan2(quad[1].y - quad[0].y, quad[1].x - quad[0].x))
    bottom = math.degrees(math.atan2(quad[2].y - quad[3].y, quad[2].x - quad[3].x))
    skew = min(abs(top), abs(bottom), abs(180.0 - abs(top)), abs(180.0 - abs(bottom)))
    return coverage, skew


def _full_frame_candidate(rgb: UInt8Image, reason: str | None) -> _BuiltCandidate:
    height, width = rgb.shape[:2]
    long_edge = max(width, height)
    border = max(3, min(12, round(min(width, height) * 0.008)))
    if long_edge + 2 * border <= MAX_TEMPLATE_EDGE:
        scale = 1.0
    else:
        scale = max(0.01, (MAX_TEMPLATE_EDGE - 2 * border) / long_edge)
    content_width = max(2, round(width * scale))
    content_height = max(2, round(height * scale))
    target_width = content_width + 2 * border
    target_height = content_height + 2 * border
    matrix: Matrix3 = (
        scale,
        0.0,
        float(border),
        0.0,
        scale,
        float(border),
        0.0,
        0.0,
        1.0,
    )
    resized = cast(
        UInt8Image,
        cv2.resize(
            rgb,
            (content_width, content_height),
            interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR,
        ),
    )
    warped = cast(
        UInt8Image,
        cv2.copyMakeBorder(
            resized,
            border,
            border,
            border,
            border,
            cv2.BORDER_CONSTANT,
            value=_WHITE,
        ),
    )
    transform = _transform(width, height, target_width, target_height, matrix)
    return _BuiltCandidate(
        warped,
        transform,
        PreprocessingMode.FULL_FRAME,
        reason,
    )


def _natural_size(quad: Quad, source_long: int, border: int) -> tuple[int, int]:
    points = _quad_array(quad).astype(np.float64)
    width = (np.linalg.norm(points[1] - points[0]) + np.linalg.norm(points[2] - points[3])) / 2
    height = (np.linalg.norm(points[3] - points[0]) + np.linalg.norm(points[2] - points[1])) / 2
    if min(width, height) < 8:
        raise ValueError("The document quadrilateral is degenerate.")
    cap = min(MAX_TEMPLATE_EDGE, source_long)
    scale = min(1.0, max(0.01, (cap - 2 * border) / max(width, height)))
    return max(2, round(width * scale)), max(2, round(height * scale))


def _rectified_candidate(rgb: UInt8Image, quad: Quad) -> _BuiltCandidate:
    height, width = rgb.shape[:2]
    if not _is_valid_quad(quad, minimum_area=width * height * 0.01):
        raise ValueError("The document quadrilateral is invalid.")
    border = max(4, min(14, round(min(width, height) * 0.009)))
    document_width, document_height = _natural_size(quad, max(width, height), border)
    transform = perspective_matrix(
        quad,
        target_width=document_width,
        target_height=document_height,
        border=border,
    )
    transform = MatrixTransform(
        source_width=width,
        source_height=height,
        target_width=transform.target_width,
        target_height=transform.target_height,
        matrix=transform.matrix,
        inverse=transform.inverse,
    )
    warped = cast(
        UInt8Image,
        cv2.warpPerspective(
            rgb,
            _as_array(transform.matrix),
            (transform.target_width, transform.target_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=_WHITE,
        ),
    )
    warped[:border, :] = 255
    warped[-border:, :] = 255
    warped[:, :border] = 255
    warped[:, -border:] = 255
    return _BuiltCandidate(
        warped,
        transform,
        PreprocessingMode.PERSPECTIVE,
        None,
    )


def _content_envelope_crop_deskew_candidate(
    rgb: UInt8Image,
) -> _BuiltCandidate | None:
    """Crop a single readable sheet by text evidence when its outer corners are weak."""
    source_height, source_width = rgb.shape[:2]
    scale = min(1.0, 1400.0 / max(source_width, source_height))
    if scale < 1.0:
        working = cast(
            UInt8Image,
            cv2.resize(
                rgb,
                (round(source_width * scale), round(source_height * scale)),
                interpolation=cv2.INTER_AREA,
            ),
        )
    else:
        working = rgb
    height, width = working.shape[:2]
    gray = cast(UInt8Image, cv2.cvtColor(working, cv2.COLOR_RGB2GRAY))
    median = float(np.median(gray))
    edges = cast(
        UInt8Image,
        cv2.Canny(gray, int(max(20, median * 0.55)), int(min(245, median * 1.45))),
    )
    blur_size = max(15, round(min(width, height) * 0.05) | 1)
    local_background = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)
    local_contrast = local_background.astype(np.int16) - gray.astype(np.int16)
    text_edges = np.where((local_contrast >= 20) & (edges > 0), 255, 0).astype(np.uint8)
    bridge_width = max(9, round(width * 0.012))
    bridge_height = max(3, round(height * 0.004))
    bridged = cast(
        UInt8Image,
        cv2.dilate(
            text_edges,
            cv2.getStructuringElement(
                cv2.MORPH_RECT,
                (bridge_width, bridge_height),
            ),
        ),
    )
    component_total, labels, stats, _ = cv2.connectedComponentsWithStats(
        bridged,
        connectivity=8,
    )
    minimum_width = max(18, round(width * 0.013))
    minimum_height = max(5, round(height * 0.004))
    minimum_area = max(80, round(width * height * 0.000055))
    maximum_height = min(90, max(18, round(height * 0.086)))
    selected_labels: list[int] = []
    component_centers: list[float] = []
    for label in range(1, component_total):
        x, _y, component_width, component_height, component_area = stats[label]
        if (
            component_width < minimum_width
            or component_height < minimum_height
            or component_height > maximum_height
            or component_area < minimum_area
            or component_width / max(component_height, 1) < 1.5
        ):
            continue
        selected_labels.append(label)
        component_centers.append(float(x) + float(component_width) / 2.0)
    if len(selected_labels) < 10:
        return None

    selected = np.where(np.isin(labels, selected_labels), 255, 0).astype(np.uint8)
    points = cv2.findNonZero(selected)
    if points is None:
        return None
    x, y, envelope_width, envelope_height = cv2.boundingRect(points)
    if envelope_width < width * 0.55 or envelope_height < height * 0.50:
        return None
    midpoint = float(x) + float(envelope_width) / 2.0
    if (
        sum(center < midpoint for center in component_centers) < 8
        or sum(center >= midpoint for center in component_centers) < 8
    ):
        return None

    rectangle = cv2.minAreaRect(points.astype(np.float32))
    working_box = cv2.boxPoints(rectangle).astype(np.float64)
    box = working_box / scale
    horizontal = max(
        (box[(index + 1) % 4] - box[index] for index in range(4)),
        key=lambda edge: abs(float(edge[0])),
    )
    angle = math.degrees(math.atan2(float(horizontal[1]), float(horizontal[0])))
    angle = (angle + 90.0) % 180.0 - 90.0
    if abs(angle) > 7.0:
        return None

    rotation_2d = cv2.getRotationMatrix2D(
        (source_width / 2.0, source_height / 2.0),
        angle,
        1.0,
    ).astype(np.float64)
    rotation = np.eye(3, dtype=np.float64)
    rotation[:2, :] = rotation_2d
    rotated_box = cv2.perspectiveTransform(
        box.astype(np.float32)[None, ...],
        rotation.astype(np.float32),
    )[0]
    padding = max(12, round(min(source_width, source_height) * 0.015))
    x1 = math.floor(float(np.min(rotated_box[:, 0])) - padding)
    y1 = math.floor(float(np.min(rotated_box[:, 1])) - padding)
    x2 = math.ceil(float(np.max(rotated_box[:, 0])) + padding)
    y2 = math.ceil(float(np.max(rotated_box[:, 1])) + padding)
    if x1 <= 0 or y1 <= 0 or x2 >= source_width or y2 >= source_height:
        return None
    crop_width = x2 - x1
    crop_height = y2 - y1
    crop_coverage = crop_width * crop_height / float(source_width * source_height)
    if not 0.40 <= crop_coverage <= 0.92:
        return None

    weak_text = np.where((local_contrast >= 12) & (edges > 0), 255, 0).astype(np.uint8)
    weak_points = cv2.findNonZero(weak_text)
    if weak_points is None:
        return None
    source_points = weak_points.reshape((-1, 2)).astype(np.float64) / scale
    homogeneous = np.column_stack((source_points, np.ones(len(source_points))))
    mapped = homogeneous @ rotation.T
    retained = (
        (mapped[:, 0] >= x1)
        & (mapped[:, 0] <= x2)
        & (mapped[:, 1] >= y1)
        & (mapped[:, 1] <= y2)
    )
    if float(np.mean(retained)) < 0.995:
        return None

    border = max(4, min(14, round(min(source_width, source_height) * 0.009)))
    cap = min(MAX_TEMPLATE_EDGE, max(source_width, source_height))
    output_scale = min(1.0, max(0.01, (cap - 2 * border) / max(crop_width, crop_height)))
    content_width = max(2, round(crop_width * output_scale))
    content_height = max(2, round(crop_height * output_scale))
    scale_x = content_width / crop_width
    scale_y = content_height / crop_height
    crop_and_scale = np.asarray(
        (
            (scale_x, 0.0, float(border) - scale_x * x1),
            (0.0, scale_y, float(border) - scale_y * y1),
            (0.0, 0.0, 1.0),
        ),
        dtype=np.float64,
    )
    matrix_array = crop_and_scale @ rotation
    target_width = content_width + 2 * border
    target_height = content_height + 2 * border
    candidate = cast(
        UInt8Image,
        cv2.warpAffine(
            rgb,
            matrix_array[:2, :],
            (target_width, target_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=_WHITE,
        ),
    )
    candidate[:border, :] = 255
    candidate[-border:, :] = 255
    candidate[:, :border] = 255
    candidate[:, -border:] = 255

    crop_translation = np.asarray(
        ((1.0, 0.0, -float(x1)), (0.0, 1.0, -float(y1)), (0.0, 0.0, 1.0)),
        dtype=np.float64,
    )
    baseline = cast(
        UInt8Image,
        cv2.warpAffine(
            rgb,
            (crop_translation @ rotation)[:2, :],
            (crop_width, crop_height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=_WHITE,
        ),
    )
    if (crop_width, crop_height) != (content_width, content_height):
        baseline = cast(
            UInt8Image,
            cv2.resize(
                baseline,
                (content_width, content_height),
                interpolation=cv2.INTER_AREA,
            ),
        )
    candidate_inner = candidate[border:-border, border:-border]
    base_blur, base_dark, base_bright, _, base_edges = measure_pixels(baseline)
    cand_blur, cand_dark, cand_bright, _, cand_edges = measure_pixels(candidate_inner)
    if not warp_quality_is_acceptable(
        baseline_blur=base_blur,
        baseline_dark_clip=base_dark,
        baseline_bright_clip=base_bright,
        baseline_edge_density=base_edges,
        candidate_blur=cand_blur,
        candidate_dark_clip=cand_dark,
        candidate_bright_clip=cand_bright,
        candidate_edge_density=cand_edges,
    ):
        return None
    matrix = _matrix_tuple(matrix_array)
    transform = _transform(
        source_width,
        source_height,
        target_width,
        target_height,
        matrix,
    )
    return _BuiltCandidate(
        candidate,
        transform,
        PreprocessingMode.CROP_DESKEW,
        None,
    )


def _roi_pixels(rgb: UInt8Image, quad: Quad) -> UInt8Image:
    height, width = rgb.shape[:2]
    xs = [point.x for point in quad]
    ys = [point.y for point in quad]
    x1 = max(0, math.floor(min(xs)))
    y1 = max(0, math.floor(min(ys)))
    x2 = min(width, math.ceil(max(xs)))
    y2 = min(height, math.ceil(max(ys)))
    return rgb[y1:y2, x1:x2]


def _inner_readability_roi(rgb: UInt8Image) -> UInt8Image:
    height, width = rgb.shape[:2]
    inset_x = min(width // 4, max(4, round(width * 0.035)))
    inset_y = min(height // 4, max(4, round(height * 0.035)))
    return rgb[inset_y : height - inset_y, inset_x : width - inset_x]


def _warp_is_acceptable(rgb: UInt8Image, quad: Quad, candidate: UInt8Image) -> bool:
    baseline = _roi_pixels(rgb, quad)
    if baseline.size == 0:
        return False
    candidate_height, candidate_width = candidate.shape[:2]
    if baseline.shape[:2] != (candidate_height, candidate_width):
        baseline = cast(
            UInt8Image,
            cv2.resize(
                baseline,
                (candidate_width, candidate_height),
                interpolation=cv2.INTER_LINEAR,
            ),
        )
    base_blur, base_dark, base_bright, _, base_edges = measure_pixels(baseline)
    cand_blur, cand_dark, cand_bright, _, cand_edges = measure_pixels(candidate)
    return warp_quality_is_acceptable(
        baseline_blur=base_blur,
        baseline_dark_clip=base_dark,
        baseline_bright_clip=base_bright,
        baseline_edge_density=base_edges,
        candidate_blur=cand_blur,
        candidate_dark_clip=cand_dark,
        candidate_bright_clip=cand_bright,
        candidate_edge_density=cand_edges,
    )


def _has_meaningful_content_outside_quad(rgb: UInt8Image, quad: Quad) -> bool:
    height, width = rgb.shape[:2]
    scale = min(1.0, MAX_PERSPECTIVE_GUARD_EDGE / max(width, height))
    if scale < 1.0:
        working_width = max(2, round(width * scale))
        working_height = max(2, round(height * scale))
        working = cast(
            UInt8Image,
            cv2.resize(rgb, (working_width, working_height), interpolation=cv2.INTER_AREA),
        )
    else:
        working = rgb
    working_height, working_width = working.shape[:2]
    working_quad = np.rint(_quad_array(quad) * scale).astype(np.int32)
    inside = np.zeros((working_height, working_width), dtype=np.uint8)
    cv2.fillConvexPoly(inside, working_quad, 255)
    boundary = np.zeros_like(inside)
    edge_exclusion = max(
        2,
        round(min(working_height, working_width) * PERSPECTIVE_OUTER_EDGE_EXCLUSION_FRACTION),
    )
    cv2.polylines(
        boundary,
        [working_quad],
        isClosed=True,
        color=255,
        thickness=2 * edge_exclusion + 1,
        lineType=cv2.LINE_AA,
    )
    outside = (inside == 0) & (boundary == 0)
    outside_pixels = int(np.count_nonzero(outside))
    if outside_pixels == 0:
        return False

    near_boundary = np.zeros_like(inside)
    near_band = max(
        edge_exclusion + 1,
        round(min(working_height, working_width) * PERSPECTIVE_NEAR_OUTSIDE_BAND_FRACTION),
    )
    cv2.polylines(
        near_boundary,
        [working_quad],
        isClosed=True,
        color=255,
        thickness=2 * near_band + 1,
        lineType=cv2.LINE_AA,
    )
    far_outside = outside & (near_boundary == 0)

    gray = cv2.cvtColor(working, cv2.COLOR_RGB2GRAY)
    blur_size = max(15, round(min(working_height, working_width) * 0.05) | 1)
    local_background = cv2.GaussianBlur(gray, (blur_size, blur_size), 0)
    local_contrast = local_background.astype(np.int16) - gray.astype(np.int16)
    dark_strokes = (
        local_contrast >= PERSPECTIVE_OUTSIDE_MIN_LOCAL_CONTRAST
    )
    text_edges = cv2.Canny(gray, 60, 160) > 0
    content_edges = far_outside & dark_strokes & text_edges
    content_pixels = int(np.count_nonzero(content_edges))
    minimum_content = max(
        PERSPECTIVE_OUTSIDE_CONTENT_MIN_PIXELS,
        math.ceil(outside_pixels * PERSPECTIVE_OUTSIDE_CONTENT_MIN_DENSITY),
    )
    if content_pixels >= minimum_content:
        return True

    near_content_edges = outside & (near_boundary > 0) & dark_strokes & text_edges
    bridged_edges = cv2.dilate(
        near_content_edges.astype(np.uint8),
        np.ones((3, 25), dtype=np.uint8),
    )
    _, labels, component_stats, _ = cv2.connectedComponentsWithStats(bridged_edges)
    text_regions = np.zeros_like(bridged_edges)
    for label, (_, _, component_width, component_height, _) in enumerate(
        component_stats[1:],
        start=1,
    ):
        if component_width >= 80 and 4 <= component_height <= 17:
            text_regions[labels == label] = 255
    text_line_pixels = int(np.count_nonzero(near_content_edges & (text_regions > 0)))
    if text_line_pixels >= PERSPECTIVE_NEAR_SMALL_LINE_MIN_SUPPORT:
        return True

    adaptive_strokes = (
        far_outside
        & (local_contrast >= PERSPECTIVE_ADAPTIVE_TEXT_MIN_LOCAL_CONTRAST)
    )
    bridged_strokes = cv2.dilate(
        adaptive_strokes.astype(np.uint8),
        np.ones((5, 9), dtype=np.uint8),
    )
    _, adaptive_labels, adaptive_stats, _ = cv2.connectedComponentsWithStats(bridged_strokes)
    adaptive_text_regions = np.zeros_like(bridged_strokes)
    for label, (component_x, component_y, component_width, component_height, _) in enumerate(
        adaptive_stats[1:],
        start=1,
    ):
        component_mask = adaptive_labels == label
        component_strokes = adaptive_strokes & component_mask
        component_pixels = int(np.count_nonzero(component_strokes))
        is_text_shaped = (
            20 <= component_width <= 300
            and 18 <= component_height <= 50
            and component_width >= component_height * 2
            and component_pixels >= PERSPECTIVE_ADAPTIVE_TEXT_LINE_MIN_PIXELS
        ) or (
            100 <= component_width <= 300
            and 6 <= component_height <= 17
            and component_width >= component_height * 4
            and component_pixels >= PERSPECTIVE_ADAPTIVE_TEXT_LINE_MIN_PIXELS
        )
        if not is_text_shaped:
            continue

        y_slice = slice(component_y, component_y + component_height)
        x_slice = slice(component_x, component_x + component_width)
        surface_mask = far_outside[y_slice, x_slice]
        surface_rows, surface_columns = np.nonzero(surface_mask)
        if surface_rows.size < 3:
            continue
        surface_values = local_background[y_slice, x_slice][surface_mask].astype(np.float64)
        surface_model = np.column_stack(
            (
                surface_columns.astype(np.float64),
                surface_rows.astype(np.float64),
                np.ones(surface_rows.size, dtype=np.float64),
            )
        )
        coefficients, *_ = np.linalg.lstsq(surface_model, surface_values, rcond=None)
        residual_std = float(np.std(surface_values - surface_model @ coefficients))
        if residual_std <= PERSPECTIVE_ADAPTIVE_MAX_SURFACE_RESIDUAL_STD:
            adaptive_text_regions[adaptive_labels == label] = 255
    adaptive_text_pixels = int(
        np.count_nonzero(adaptive_strokes & (adaptive_text_regions > 0))
    )
    if adaptive_text_pixels >= PERSPECTIVE_ADAPTIVE_TEXT_LINE_MIN_PIXELS:
        return True
    return False


def _encode_jpeg(rgb: UInt8Image) -> bytes:
    output = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(
        output,
        format="JPEG",
        quality=95,
        subsampling=0,
        optimize=True,
    )
    return output.getvalue()


def _profile_to_srgb(image: Image.Image, profile_bytes: bytes) -> Image.Image | None:
    try:
        source_profile = ImageCms.ImageCmsProfile(io.BytesIO(profile_bytes))
        return ImageCms.profileToProfile(
            image,
            source_profile,
            ImageCms.createProfile("sRGB"),
            outputMode="RGB",
        )
    except (ImageCms.PyCMSError, OSError, TypeError, ValueError):
        return None


def _to_srgb(image: Image.Image) -> Image.Image:
    embedded_profile = image.info.get("icc_profile")
    profile_bytes = embedded_profile if isinstance(embedded_profile, bytes) else None
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        rgb = rgba.convert("RGB")
        managed = _profile_to_srgb(rgb, profile_bytes) if profile_bytes else None
        color = managed or rgb
        white = Image.new("RGB", rgba.size, _WHITE)
        white.paste(color, mask=alpha)
        if managed is not None:
            managed.close()
        rgb.close()
        alpha.close()
        rgba.close()
        return white
    if profile_bytes:
        managed = _profile_to_srgb(image, profile_bytes)
        if managed is not None:
            return managed
    if image.mode == "RGB":
        return image
    return image.convert("RGB")


def _mild_luminance_normalize(rgb: UInt8Image) -> UInt8Image:
    return _luminance_background_correct(rgb, strength=0.16)


def _luminance_background_correct(
    rgb: UInt8Image,
    *,
    strength: float,
) -> UInt8Image:
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    luminance = lab[..., 0]
    height, width = luminance.shape
    scale = min(1.0, 1024 / max(width, height))
    if scale < 1.0:
        illumination_input = cv2.resize(
            luminance,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )
    else:
        illumination_input = luminance
    shorter = min(illumination_input.shape)
    kernel = min(63, max(9, (shorter // 12) | 1))
    background = cv2.GaussianBlur(illumination_input, (kernel, kernel), 0)
    median = float(np.median(background))
    if background.shape != luminance.shape:
        background = cv2.resize(background, (width, height), interpolation=cv2.INTER_LINEAR)
    lab[..., 0] = cv2.addWeighted(
        luminance,
        1.0,
        background,
        -strength,
        median * strength,
    )
    return cast(UInt8Image, cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))


def _illumination_equalize(rgb: UInt8Image) -> UInt8Image:
    return _luminance_background_correct(rgb, strength=0.55)


def _contrast_enhance(rgb: UInt8Image) -> UInt8Image:
    normalized = _mild_luminance_normalize(rgb)
    lab = cv2.cvtColor(normalized, cv2.COLOR_RGB2LAB)
    luminance = lab[..., 0]
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(luminance)
    lab[..., 0] = cv2.addWeighted(luminance, 0.25, enhanced, 0.75, 0.0)
    return cast(UInt8Image, cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))


def _apply_correction_preset(
    rgb: UInt8Image,
    preset: CorrectionPreset,
) -> tuple[UInt8Image, str]:
    if preset is CorrectionPreset.NONE:
        return rgb.copy(), "color_correction_skipped"
    if preset is CorrectionPreset.ILLUMINATION:
        return _illumination_equalize(rgb), "illumination_equalized"
    if preset is CorrectionPreset.CONTRAST:
        return _contrast_enhance(rgb), "luminance_contrast_enhanced"
    return _mild_luminance_normalize(rgb), "mild_luminance_normalized"


def _blend_grayscale(rgb: UInt8Image, level: int) -> UInt8Image:
    if level == 0:
        return rgb
    luminance = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    grayscale = cast(UInt8Image, cv2.cvtColor(luminance, cv2.COLOR_GRAY2RGB))
    if level == 100:
        return grayscale
    amount = level / 100.0
    return cast(
        UInt8Image,
        cv2.addWeighted(rgb, 1.0 - amount, grayscale, amount, 0.0),
    )


def _preview(
    image_id: str,
    rgb: UInt8Image,
    raw_dimensions: ImageDimensions,
    raw_to_image: Matrix3,
) -> PreviewImage:
    height, width = rgb.shape[:2]
    scale = min(1.0, MAX_PREVIEW_EDGE / max(width, height))
    preview_width = max(1, round(width * scale))
    preview_height = max(1, round(height * scale))
    if scale < 1.0:
        preview_rgb = cast(
            UInt8Image,
            cv2.resize(rgb, (preview_width, preview_height), interpolation=cv2.INTER_AREA),
        )
    else:
        preview_rgb = rgb
    image_to_preview = resize_matrix(width, height, preview_width, preview_height).matrix
    raw_to_preview = _compose(image_to_preview, raw_to_image)
    return PreviewImage(
        image_id=image_id,
        jpeg_bytes=_encode_jpeg(preview_rgb),
        mime_type="image/jpeg",
        width=preview_width,
        height=preview_height,
        source_dimensions=raw_dimensions,
        source_to_preview=raw_to_preview,
        preview_to_source=_inverse(raw_to_preview),
    )


def _classify(
    metrics: ImageQualityMetrics,
    document: DocumentDetection,
    preprocessing_mode: PreprocessingMode,
) -> tuple[QualityState, tuple[str, ...]]:
    reasons: list[str] = []
    severe_blank = (
        metrics.edge_density < 0.0015
        and metrics.blur_variance < 4.0
        and metrics.illumination_variation < 0.015
    )
    severe_blur = metrics.blur_variance < 9.0 and metrics.edge_density < 0.02
    tiny_document = (
        document.polygon is not None
        and metrics.page_coverage < 0.075
        and document.confidence >= 0.70
    )
    multiple = metrics.likely_document_count >= 2
    if severe_blank:
        reasons.append("blank_or_contentless")
    elif severe_blur:
        reasons.append("severe_blur")
    if tiny_document:
        reasons.append("document_too_small")
    if multiple:
        reasons.append("multiple_documents_suspected")
    if document.crop_suspicion:
        reasons.append("document_crop_suspected")
    if reasons:
        return QualityState.RECAPTURE_REQUIRED, tuple(reasons)
    if document.polygon is None:
        return QualityState.PROCESSED, ("document_geometry_uncertain",)
    if preprocessing_mode is PreprocessingMode.CROP_DESKEW:
        return QualityState.PROCESSED, ("crop_deskewed",)
    if (
        document.confidence < 0.60
        or preprocessing_mode is not PreprocessingMode.PERSPECTIVE
    ):
        return QualityState.PROCESSED, ("perspective_not_applied",)
    return QualityState.PROCESSED, ("perspective_rectified",)


def preprocess_image(
    source_bytes: bytes,
    mime_type: str,
    manual_rotation: int = 0,
    correction_preset: CorrectionPreset = CorrectionPreset.ILLUMINATION,
    grayscale_level: int = 0,
    *,
    document_quad_override: Quad | None = None,
) -> PreprocessResult:
    if manual_rotation not in {0, 90, 180, 270}:
        raise ImageValidationError(
            ImageErrorCode.INVALID_ROTATION,
            "Rotation must be one of 0, 90, 180, or 270 degrees.",
        )
    if type(grayscale_level) is not int or not 0 <= grayscale_level <= 100:
        raise ImageValidationError(
            ImageErrorCode.INVALID_GRAYSCALE_LEVEL,
            "Grayscale level must be an integer from 0 through 100.",
        )
    if len(source_bytes) > MAX_SOURCE_BYTES:
        raise ImageValidationError(
            ImageErrorCode.SOURCE_TOO_LARGE,
            "The image exceeds the supported byte limit.",
        )
    immutable_source = source_bytes
    decoded, source_format, orientation = _decode_image(immutable_source, mime_type)
    decoded_dimensions = ImageDimensions(*decoded.size)
    exif_transform = exif_orientation_matrix(*decoded.size, orientation)
    transposed = ImageOps.exif_transpose(decoded)
    if transposed is not decoded:
        decoded.close()
    oriented = _to_srgb(transposed)
    if oriented is not transposed:
        transposed.close()
    manual_transform = rotation_matrix_clockwise(*oriented.size, manual_rotation)
    transpose_methods = {
        90: Image.Transpose.ROTATE_270,
        180: Image.Transpose.ROTATE_180,
        270: Image.Transpose.ROTATE_90,
    }
    if manual_rotation:
        rotated = oriented.transpose(transpose_methods[manual_rotation])
        oriented.close()
        oriented = rotated
    rgb = np.asarray(oriented, dtype=np.uint8).copy()
    oriented.close()
    height, width = rgb.shape[:2]
    oriented_dimensions = ImageDimensions(width, height)
    raw_to_oriented_matrix = _compose(manual_transform.matrix, exif_transform.matrix)
    raw_to_oriented = _transform(
        decoded_dimensions.width,
        decoded_dimensions.height,
        width,
        height,
        raw_to_oriented_matrix,
    )

    if document_quad_override is None:
        document = _stabilize_document_detection(_detect_document(rgb), width, height)
    elif _is_valid_quad(document_quad_override, minimum_area=width * height * 0.01):
        coverage, _ = _quad_geometry(document_quad_override, width, height)
        document = DocumentDetection(
            document_quad_override,
            1,
            0.99,
            _crop_suspicion(document_quad_override, width, height),
        )
    else:
        document = DocumentDetection(document_quad_override, 1, 0.0, False)

    coverage = 0.0
    skew = 0.0
    if document.polygon is not None:
        coverage, skew = _quad_geometry(document.polygon, width, height)
    candidate: _BuiltCandidate | None = None
    operations: list[str] = ["exif_orientation_normalized"]
    if manual_rotation:
        operations.append(f"manual_rotate_{manual_rotation}_clockwise")
    if document_quad_override is None and document.polygon is not None:
        operations.append("document_quad_safety_expanded")
    can_warp = (
        document.polygon is not None
        and _is_valid_quad(document.polygon, minimum_area=width * height * 0.01)
        and MIN_SAFE_PERSPECTIVE_COVERAGE <= coverage <= 0.93
        and document.confidence >= 0.60
        and not document.crop_suspicion
        and document.likely_document_count < 2
    )
    meaningful_content_outside = False
    trusted_outer_document = (
        coverage >= TRUSTED_OUTER_DOCUMENT_MIN_COVERAGE
        and document.confidence >= TRUSTED_OUTER_DOCUMENT_MIN_CONFIDENCE
    )
    if (
        can_warp
        and document_quad_override is None
        and document.polygon is not None
        and not trusted_outer_document
    ):
        meaningful_content_outside = _has_meaningful_content_outside_quad(
            rgb,
            document.polygon,
        )
        if meaningful_content_outside:
            can_warp = False
    fallback_reason = "perspective_guard_rejected"
    if can_warp and document.polygon is not None:
        try:
            proposed = _rectified_candidate(rgb, document.polygon)
        except (ValueError, cv2.error, np.linalg.LinAlgError):
            fallback_reason = "invalid_perspective_geometry"
        else:
            if _warp_is_acceptable(rgb, document.polygon, proposed.rgb):
                candidate = proposed
                operations.append("perspective_rectified")
            else:
                fallback_reason = "quality_regression_rollback"
                operations.append("perspective_rollback")
    if candidate is None:
        crop_deskew: _BuiltCandidate | None = None
        crop_deskew_eligible = (
            document_quad_override is None
            and document.polygon is not None
            and document.confidence >= 0.60
            and not document.crop_suspicion
            and document.likely_document_count < 2
            and (
                coverage < MIN_SAFE_PERSPECTIVE_COVERAGE
                or meaningful_content_outside
                or fallback_reason == "quality_regression_rollback"
            )
        )
        if crop_deskew_eligible:
            crop_deskew = _content_envelope_crop_deskew_candidate(rgb)
        if crop_deskew is not None:
            candidate = crop_deskew
            operations.append("crop_deskewed")
        else:
            candidate = _full_frame_candidate(rgb, fallback_reason)
            operations.append("conservative_full_frame")

    readability_rgb = candidate.rgb
    metrics = build_metrics(
        _inner_readability_roi(readability_rgb),
        page_coverage=coverage,
        corner_confidence=document.confidence,
        skew_degrees=skew,
        likely_document_count=document.likely_document_count,
    )
    normalized_rgb, correction_operation = _apply_correction_preset(
        candidate.rgb,
        correction_preset,
    )
    normalized_rgb = _blend_grayscale(normalized_rgb, grayscale_level)
    border = min(8, max(3, round(min(normalized_rgb.shape[:2]) * 0.006)))
    normalized_rgb[:border, :] = 255
    normalized_rgb[-border:, :] = 255
    normalized_rgb[:, :border] = 255
    normalized_rgb[:, -border:] = 255
    candidate = replace(candidate, rgb=normalized_rgb)
    operations.extend((correction_operation, "srgb_color_preserved", "white_safety_border"))
    if grayscale_level:
        operations.append(f"grayscale_blended_{grayscale_level}_percent")

    quality_state, reasons = _classify(metrics, document, candidate.preprocessing_mode)
    preprocessing_mode = (
        PreprocessingMode.RECAPTURE
        if quality_state is QualityState.RECAPTURE_REQUIRED
        else candidate.preprocessing_mode
    )
    raw_to_template_matrix = _compose(
        candidate.oriented_to_candidate.matrix, raw_to_oriented.matrix
    )
    raw_to_template = _transform(
        decoded_dimensions.width,
        decoded_dimensions.height,
        candidate.oriented_to_candidate.target_width,
        candidate.oriented_to_candidate.target_height,
        raw_to_template_matrix,
    )
    template_bytes = _encode_jpeg(candidate.rgb)
    template_image = EncodedImage(
        jpeg_bytes=template_bytes,
        mime_type="image/jpeg",
        width=candidate.oriented_to_candidate.target_width,
        height=candidate.oriented_to_candidate.target_height,
        used_perspective=(candidate.preprocessing_mode is PreprocessingMode.PERSPECTIVE),
        rollback_reason=candidate.rollback_reason,
    )
    return PreprocessResult(
        source_bytes=immutable_source,
        source_sha256=hashlib.sha256(immutable_source).hexdigest(),
        source_format=source_format,
        decoded_dimensions=decoded_dimensions,
        oriented_dimensions=oriented_dimensions,
        raw_to_oriented=raw_to_oriented,
        raw_to_template=raw_to_template,
        document=document,
        metrics=metrics,
        quality_state=quality_state,
        preprocessing_mode=preprocessing_mode,
        correction_preset=correction_preset,
        grayscale_level=grayscale_level,
        reasons=reasons,
        operations=tuple(operations),
        template_image=template_image,
        oriented_preview=_preview(
            "oriented-original", rgb, decoded_dimensions, raw_to_oriented.matrix
        ),
    )

