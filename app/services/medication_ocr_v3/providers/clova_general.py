from __future__ import annotations

import json
import logging
import math
import time
import unicodedata
import uuid
from collections.abc import Callable, Mapping
from typing import cast

import httpx2

from app.services.medication_ocr_v3.domain.image import Point, Quad
from app.services.medication_ocr_v3.domain.models import (
    OcrBlock,
    OcrBlockIssueCode,
    OcrErrorCode,
    OcrProviderError,
    OcrResult,
)

_IMAGE_NAME = "processed-image"
_FILE_NAME = "processed-image.jpg"
_TIMEOUT = httpx2.Timeout(connect=5.0, read=60.0, write=30.0, pool=5.0)
# Allow a dense page while bounding later pairwise layout work to roughly one million
# comparisons. Validate this provider-controlled count before normalizing any field.
_MAX_NORMALIZED_FIELDS = 1_000

# httpx2's default INFO request log includes the full endpoint. Provider URLs are
# operationally sensitive, so keep this library logger above its request-log level.
logging.getLogger("httpx2").setLevel(logging.WARNING)


class ClovaGeneralOcrProvider:
    """One concrete CLOVA General OCR V2 client with a deliberately narrow output."""

    def __init__(
        self,
        *,
        endpoint: str,
        secret: str,
        transport: httpx2.AsyncBaseTransport | None = None,
        request_id_factory: Callable[[], uuid.UUID] = uuid.uuid4,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._secret = secret
        self._request_id_factory = request_id_factory
        self._clock_ms = clock_ms or _epoch_milliseconds
        self._client = httpx2.AsyncClient(
            transport=transport,
            timeout=_TIMEOUT,
            follow_redirects=False,
            trust_env=False,
        )

    def __repr__(self) -> str:
        return "ClovaGeneralOcrProvider()"

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ClovaGeneralOcrProvider:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def recognize(self, processed_jpeg: bytes) -> OcrResult:
        request_id = self._request_id_factory()
        message = {
            "version": "V2",
            "requestId": str(request_id),
            "timestamp": self._clock_ms(),
            "lang": "ko",
            "images": [{"format": "jpg", "name": _IMAGE_NAME}],
        }
        try:
            response = await self._client.post(
                self._endpoint,
                headers={"X-OCR-SECRET": self._secret},
                data={"message": json.dumps(message, separators=(",", ":"))},
                files={"file": (_FILE_NAME, processed_jpeg, "image/jpeg")},
            )
        except httpx2.TimeoutException:
            raise OcrProviderError(OcrErrorCode.OCR_TIMEOUT, 504) from None
        except httpx2.ConnectError:
            raise OcrProviderError(OcrErrorCode.OCR_CONNECTION_FAILED, 502) from None
        except httpx2.TransportError:
            raise OcrProviderError(OcrErrorCode.OCR_UPSTREAM_FAILED, 502) from None

        if response.status_code in {401, 403}:
            raise OcrProviderError(OcrErrorCode.OCR_AUTH_REJECTED, 502)
        if not 200 <= response.status_code < 300:
            raise OcrProviderError(OcrErrorCode.OCR_UPSTREAM_FAILED, 502)
        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            raise OcrProviderError(OcrErrorCode.OCR_PROTOCOL_INVALID, 502) from None
        return _normalize_payload(payload)


def _epoch_milliseconds() -> int:
    return time.time_ns() // 1_000_000


def _normalize_payload(payload: object) -> OcrResult:
    root = _mapping_or_protocol_error(payload)
    if root.get("version") != "V2" or not isinstance(root.get("requestId"), str):
        raise _protocol_error()
    timestamp = root.get("timestamp")
    if not _is_finite_number(timestamp):
        raise _protocol_error()
    images = root.get("images")
    if not isinstance(images, list) or len(images) != 1:
        raise _protocol_error()
    image = _mapping_or_protocol_error(images[0])
    if image.get("inferResult") != "SUCCESS":
        raise _protocol_error()
    fields = image.get("fields")
    if not isinstance(fields, list):
        raise _protocol_error()
    if len(fields) > _MAX_NORMALIZED_FIELDS:
        raise _protocol_error()
    blocks = tuple(_normalize_block(field, index) for index, field in enumerate(fields, start=1))
    return OcrResult(blocks=blocks)


def _normalize_block(field_value: object, index: int) -> OcrBlock:
    field = _mapping_or_protocol_error(field_value)
    raw_text = field.get("inferText")
    line_break = field.get("lineBreak")
    if not isinstance(raw_text, str) or not isinstance(line_break, bool):
        raise _protocol_error()
    issues: list[OcrBlockIssueCode] = []
    confidence = _normalize_confidence(field.get("inferConfidence"), issues)
    bbox = _normalize_bbox(field.get("boundingPoly"), issues)
    return OcrBlock(
        block_id=f"block-{index:04d}",
        text=_normalize_text(raw_text),
        confidence=confidence,
        bbox=bbox,
        line_break=line_break,
        issues=tuple(issues),
    )


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    whitespace_safe = "".join(
        " " if character.isspace() or unicodedata.category(character) == "Cc" else character
        for character in normalized
    )
    return " ".join(whitespace_safe.split())


def _normalize_confidence(
    raw_confidence: object, issues: list[OcrBlockIssueCode]
) -> float | None:
    if not _is_finite_number(raw_confidence):
        issues.append(OcrBlockIssueCode.INVALID_BLOCK_CONFIDENCE)
        return None
    return float(cast(int | float, raw_confidence))


def _normalize_bbox(raw_bbox: object, issues: list[OcrBlockIssueCode]) -> Quad | None:
    if not isinstance(raw_bbox, Mapping):
        issues.append(OcrBlockIssueCode.INVALID_BLOCK_GEOMETRY)
        return None
    vertices = raw_bbox.get("vertices")
    if not isinstance(vertices, list) or len(vertices) != 4:
        issues.append(OcrBlockIssueCode.INVALID_BLOCK_GEOMETRY)
        return None
    points: list[Point] = []
    for vertex_value in vertices:
        if not isinstance(vertex_value, Mapping):
            issues.append(OcrBlockIssueCode.INVALID_BLOCK_GEOMETRY)
            return None
        x = vertex_value.get("x")
        y = vertex_value.get("y")
        if not _is_finite_number(x) or not _is_finite_number(y):
            issues.append(OcrBlockIssueCode.INVALID_BLOCK_GEOMETRY)
            return None
        points.append(
            Point(
                x=float(cast(int | float, x)),
                y=float(cast(int | float, y)),
            )
        )
    quad = cast(Quad, tuple(points))
    if not _is_valid_quad(quad):
        issues.append(OcrBlockIssueCode.INVALID_BLOCK_GEOMETRY)
        return None
    return quad


def _polygon_area(points: Quad) -> float:
    return abs(
        sum(
            point.x * points[(index + 1) % 4].y - points[(index + 1) % 4].x * point.y
            for index, point in enumerate(points)
        )
        / 2.0
    )


def _is_valid_quad(points: Quad) -> bool:
    if len({(point.x, point.y) for point in points}) != 4:
        return False
    if any(points[index] == points[(index + 1) % 4] for index in range(4)):
        return False
    area = _polygon_area(points)
    if not math.isfinite(area) or area == 0.0:
        return False
    return not (
        _segments_intersect(points[0], points[1], points[2], points[3])
        or _segments_intersect(points[1], points[2], points[3], points[0])
    )


def _segments_intersect(
    first_start: Point,
    first_end: Point,
    second_start: Point,
    second_end: Point,
) -> bool:
    first_start_side = _orientation(first_start, first_end, second_start)
    first_end_side = _orientation(first_start, first_end, second_end)
    second_start_side = _orientation(second_start, second_end, first_start)
    second_end_side = _orientation(second_start, second_end, first_end)
    if (
        first_start_side == 0.0 and _is_on_segment(first_start, first_end, second_start)
    ) or (
        first_end_side == 0.0 and _is_on_segment(first_start, first_end, second_end)
    ) or (
        second_start_side == 0.0 and _is_on_segment(second_start, second_end, first_start)
    ) or (
        second_end_side == 0.0 and _is_on_segment(second_start, second_end, first_end)
    ):
        return True
    return (first_start_side > 0.0) != (first_end_side > 0.0) and (
        second_start_side > 0.0
    ) != (second_end_side > 0.0)


def _orientation(first: Point, second: Point, third: Point) -> float:
    return (second.x - first.x) * (third.y - first.y) - (second.y - first.y) * (
        third.x - first.x
    )


def _is_on_segment(start: Point, end: Point, candidate: Point) -> bool:
    return (
        min(start.x, end.x) <= candidate.x <= max(start.x, end.x)
        and min(start.y, end.y) <= candidate.y <= max(start.y, end.y)
    )


def _is_finite_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except OverflowError:
        return False


def _mapping_or_protocol_error(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise _protocol_error()
    return cast(Mapping[str, object], value)


def _protocol_error() -> OcrProviderError:
    return OcrProviderError(OcrErrorCode.OCR_PROTOCOL_INVALID, 502)

