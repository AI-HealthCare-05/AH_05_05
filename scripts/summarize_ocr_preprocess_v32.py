from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import cv2
import numpy as np


def main() -> int:
    root_value = os.environ.get("OCR_V32_ARTIFACT_ROOT")
    if not root_value:
        print("OCR_V32_ARTIFACT_ROOT is required.", file=sys.stderr)
        return 2
    root = Path(root_value)
    control = cv2.imread(str(root / "v3.2.1" / "preprocessed.jpg"))
    if control is None:
        print("v3.2.1 control image is missing.", file=sys.stderr)
        return 1
    rows: list[dict[str, object]] = []
    for patch in range(1, 9):
        version = f"v3.2.{patch}"
        image = cv2.imread(str(root / version / "preprocessed.jpg"))
        if image is None:
            print(f"{version} image is missing.", file=sys.stderr)
            return 1
        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        rows.append(
            {
                "version": version,
                "laplacianVariance": round(float(cv2.Laplacian(grayscale, cv2.CV_64F).var()), 3),
                "luminanceStd": round(float(grayscale.std()), 3),
                "meanSaturation": round(float(hsv[..., 1].mean()), 3),
                "meanAbsDeltaFromControl": round(
                    float(np.abs(image.astype(np.int16) - control.astype(np.int16)).mean()),
                    3,
                ),
            }
        )
    (root / "output-quality-summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(rows, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
