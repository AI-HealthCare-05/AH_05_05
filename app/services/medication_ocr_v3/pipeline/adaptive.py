"""Bounded, image-only sampling decisions; never infer missing printed content."""

from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

type UInt8Image = NDArray[np.uint8]


def needs_illumination_correction(rgb: UInt8Image) -> bool:
    """Detect slow background variation without treating dark glyphs as shadow."""
    height, width = rgb.shape[:2]
    if min(height, width) < 16:
        return False
    scale = min(1.0, 512.0 / max(height, width))
    bounded = cv2.resize(
        rgb, (max(8, round(width * scale)), max(8, round(height * scale))), interpolation=cv2.INTER_AREA
    )
    gray = cv2.cvtColor(bounded, cv2.COLOR_RGB2GRAY)
    paper_levels = np.asarray(
        [np.percentile(tile, 90) for band in np.array_split(gray, 8) for tile in np.array_split(band, 8, axis=1)]
    )
    paper_levels = paper_levels[paper_levels >= 100]
    if len(paper_levels) < 16:
        return True  # An uncertain dark scene keeps the established correction.
    return bool(np.percentile(paper_levels, 90) - np.percentile(paper_levels, 10) >= 24)


def enlarge_small_print(rgb: UInt8Image) -> tuple[UInt8Image, NDArray[np.float64], str]:
    """Resample substantial tiny-print evidence, leaving uncertain images untouched.

    This is interpolation, not super-resolution: it cannot recover absent strokes.
    Native-size components avoid confusing a large document's analysis thumbnail
    with an actually low-resolution input. The scan never exceeds 1600px per edge.
    """
    height, width = rgb.shape[:2]
    identity = np.eye(3, dtype=np.float64)
    if min(height, width) < 32 or max(height, width) >= 1600:
        return rgb, identity, "small_print_skipped_dimensions"
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 12)
    _, _, stats, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    stats = stats[1:]
    widths, heights, areas = stats[:, 2], stats[:, 3], stats[:, 4]
    # Long rules and short dashes are not character evidence. Require varied
    # component shapes too, so repeated dot leaders alone cannot trigger a resize.
    keep = (
        (heights >= 5)
        & (heights <= 36)
        & (widths >= 2)
        & (widths <= 36)
        & (widths <= heights * 1.6)
        & (widths >= heights * 0.15)
        & (areas >= 7)
        & (areas <= 600)
        & (areas <= widths * heights * 0.85)
    )
    glyphs = stats[keep]
    if len(glyphs) < 24 or len(np.unique(glyphs[:, 2:5], axis=0)) < 3:
        return rgb, identity, "small_print_skipped_weak_evidence"
    median_height = float(np.median(glyphs[:, 3]))
    if median_height >= 12:
        return rgb, identity, "small_print_skipped_readable_sampling"
    fills = glyphs[:, 4] / (glyphs[:, 2] * glyphs[:, 3])
    widths_lo, widths_hi = np.percentile(glyphs[:, 2], (10, 90))
    heights_lo, heights_hi = np.percentile(glyphs[:, 3], (10, 90))
    if widths_hi < widths_lo * 1.4 and heights_hi < heights_lo * 1.4 and np.ptp(np.percentile(fills, (10, 90))) < 0.2:
        return rgb, identity, "small_print_skipped_repeated_shapes"
    # A page of random speckles can have varied component shapes. Demand several
    # populated line bands with a clear concentration above uniform background.
    centers = np.clip(np.rint(glyphs[:, 1] + glyphs[:, 3] * 0.5).astype(int), 0, height - 1)
    window = max(3, round(median_height * 0.6) | 1)
    counts = np.convolve(np.bincount(centers, minlength=height), np.ones(window), mode="same")
    dense = counts >= max(3, len(glyphs) * window / height * 3.0)
    bands = int(np.count_nonzero(np.diff(np.pad(dense.astype(np.int8), (1, 1))) == 1))
    if bands < 3 or float(np.mean(dense[centers])) < 0.65:
        return rgb, identity, "small_print_skipped_unstructured_components"
    scale = min(2.0, 14.0 / median_height, 2048.0 / max(width, height))
    if scale < 1.2:
        return rgb, identity, "small_print_skipped_small_gain"
    target_width, target_height = round(width * scale), round(height * scale)
    enlarged = cast(UInt8Image, cv2.resize(rgb, (target_width, target_height), interpolation=cv2.INTER_CUBIC))
    matrix = np.diag([target_width / width, target_height / height, 1.0])
    return enlarged, matrix, f"small_print_enlarged_{scale:.2f}x"
