"""Offline OCR preprocessing benchmark; persist hashes, never document content."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.medication_ocr_v3.pipeline.preprocess import preprocess_image  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.output.exists() or args.repeats < 1:
        parser.error("Use a new output path and a positive repeat count")
    results = []
    for path in args.input:
        content = path.read_bytes()
        mime = "image/png" if content.startswith(b"\x89PNG") else "image/jpeg"
        samples = []
        signatures = []
        for iteration in range(args.repeats + 1):
            cv2.setRNGSeed(0)
            started = time.perf_counter()
            result = preprocess_image(content, mime)
            elapsed = (time.perf_counter() - started) * 1000
            # Includes all decisions, quality metrics, transforms, and both JPEGs.
            signature = hashlib.sha256(repr(result).encode()).hexdigest()
            if iteration:
                samples.append(elapsed)
                signatures.append(signature)
        results.append(
            {
                "input_sha256": hashlib.sha256(content).hexdigest(),
                "samples_ms": samples,
                "median_ms": statistics.median(samples),
                "signatures": signatures,
                "stable": len(set(signatures)) == 1,
                "quality_state": result.quality_state.value,
            }
        )
    payload = {"results": results, "mean_median_ms": statistics.mean(r["median_ms"] for r in results)}
    if args.compare:
        before = json.loads(args.compare.read_text(encoding="utf-8"))
        payload["equivalent"] = len(before["results"]) == len(results) and all(
            old["input_sha256"] == new["input_sha256"]
            and old["stable"]
            and new["stable"]
            and old["signatures"][0] == new["signatures"][0]
            for old, new in zip(before["results"], results, strict=False)
        )
        payload["reduction_percent"] = 100 * (1 - payload["mean_median_ms"] / before["mean_median_ms"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
