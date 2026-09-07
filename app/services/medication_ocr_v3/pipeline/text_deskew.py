"""Conservative, image-only residual text-line rotation (no OCR calls)."""

from __future__ import annotations

import math

import cv2
import numpy as np
from numpy.typing import NDArray

type Pixels = NDArray[np.uint8]


def estimate_text_angle(rgb: Pixels) -> tuple[float, str]:
    """Return clockwise text slope only when separate text bands agree."""
    height, width = rgb.shape[:2]
    scale = min(1.0, 960 / max(height, width))
    size = (round(width * scale), round(height * scale))
    if min(size) < 3:
        return 0.0, "insufficient_text"
    small = rgb if scale == 1.0 else cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    mask = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    # Require letter-height components; small dots and wide dashes are not text.
    # This deliberately ignores tiny print rather than rotating from table rules.
    keep = np.zeros(count, dtype=np.uint8)
    for index, (_, _, w, h, area) in enumerate(stats[1:], start=1):
        if 7 <= h <= 48 and 1 <= w <= 60 and 4 <= area <= 1100 and 0.08 <= w / h <= 1.6:
            keep[index] = 1
    if int(keep.sum()) < 40:
        return 0.0, "insufficient_text"
    ys, xs = np.nonzero(keep[labels])
    if len(xs) < 250:
        return 0.0, "insufficient_text"
    stride = max(1, math.ceil(len(xs) / 60000))
    xs = xs[::stride].astype(np.float64) - small.shape[1] / 2
    ys = ys[::stride].astype(np.float64)
    offset = small.shape[1]

    def score(angle: float, x: NDArray[np.float64], y: NDArray[np.float64]) -> float:
        rows = np.rint(y - math.tan(math.radians(angle)) * x + offset).astype(np.int32)
        profile = np.bincount(rows, minlength=small.shape[0] + 2 * offset).astype(np.float64)
        return float(np.dot(profile, profile))

    angles = np.arange(-20.0, 20.01, 0.5)
    scores = [score(float(angle), xs, ys) for angle in angles]
    best_index = int(np.argmax(scores))
    if best_index in (0, len(angles) - 1):
        return 0.0, "angle_out_of_range"
    coarse = float(angles[best_index])
    fine = np.arange(coarse - 0.4, coarse + 0.41, 0.1)
    best = float(max(fine, key=lambda angle: score(float(angle), xs, ys)))
    if abs(best) < 0.6:
        return 0.0, "already_level"
    best_score = score(best, xs, ys)
    if best_score < score(0, xs, ys) * 1.10:
        return 0.0, "weak_gain"
    competing = max(value for angle, value in zip(angles, scores, strict=True) if abs(angle - best) >= 1.5)
    if best_score < competing * 1.03:
        return 0.0, "ambiguous_angle"
    # Independent vertical regions prevent one rule or handwritten note dominating.
    agreeing = 0
    populated = 0
    for low, high in zip(
        np.linspace(ys.min(), ys.max() + 1, 4)[:-1], np.linspace(ys.min(), ys.max() + 1, 4)[1:], strict=True
    ):
        selected = (ys >= low) & (ys < high)
        if int(selected.sum()) < 250:
            continue
        populated += 1
        local = float(max(angles, key=lambda angle: score(float(angle), xs[selected], ys[selected])))
        if abs(local - best) <= 0.8:
            agreeing += 1
    if agreeing < 2 or agreeing < populated * 0.67:
        return 0.0, "inconsistent_lines"
    return best, "confident"


def deskew_text(rgb: Pixels, *, max_edge: int) -> tuple[Pixels, NDArray[np.float64], str]:
    angle, reason = estimate_text_angle(rgb)
    if angle == 0:
        return rgb, np.eye(3, dtype=np.float64), f"text_deskew_skipped_{reason}"
    height, width = rgb.shape[:2]
    radians = math.radians(angle)
    new_width = math.ceil(width * abs(math.cos(radians)) + height * abs(math.sin(radians)))
    new_height = math.ceil(height * abs(math.cos(radians)) + width * abs(math.sin(radians)))
    affine = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    affine[:, 2] += [(new_width - width) / 2, (new_height - height) / 2]
    scale = min(1.0, max_edge / max(new_width, new_height))
    affine *= scale
    output = cv2.warpAffine(
        rgb,
        affine,
        (math.ceil(new_width * scale), math.ceil(new_height * scale)),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(255, 255, 255),
    )
    matrix = np.vstack((affine, [0.0, 0.0, 1.0]))
    return output, matrix, f"text_deskew_applied_{angle:.2f}_degrees"

