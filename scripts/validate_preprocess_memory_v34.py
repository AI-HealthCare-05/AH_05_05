"""Measure the maximum accepted synthetic bitmap in fresh processes, without OCR."""

import argparse
import hashlib
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.services.medication_ocr_v3.domain.image import Point
from app.services.medication_ocr_v3.pipeline.preprocess import apply_matrix, preprocess_image
from scripts.benchmark_ocr_preprocess_v31 import _working_set_bytes
from scripts.benchmark_ocr_v34 import _atomic_json, _code_identity, digest


def child(version):
    rgb = np.full((4000, 10000, 3), 255, dtype=np.uint8)
    for y in range(450, 3650, 300):
        cv2.putText(rgb, "SYNTHETIC MEDICINE 120mg  1 tablet 3 times 7 days", (450, y), 0, 5.0, (30, 40, 50), 6)
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream, format="PNG")
    content = stream.getvalue()
    del rgb
    started = time.perf_counter()
    result = preprocess_image(
        content,
        "image/png",
        preprocess_version=version,
        document_quad_override=(Point(200, 150), Point(9800, 150), Point(9800, 3850), Point(200, 3850)),
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert result.decoded_dimensions.as_tuple() == (10000, 4000)
    assert max(result.template_image.width, result.template_image.height) <= 4096
    assert result.template_image.used_perspective
    for point in (Point(1000, 1000), Point(8000, 3000)):
        mapped = apply_matrix(result.raw_to_template.matrix, point)
        restored = apply_matrix(result.raw_to_template.inverse, mapped)
        assert abs(restored.x - point.x) < 1e-6 and abs(restored.y - point.y) < 1e-6
    return {
        "version": version,
        "syntheticSourceSha256": hashlib.sha256(content).hexdigest(),
        "sourcePixels": 40_000_000,
        "sourceLongEdge": 10000,
        "templateDimensions": [result.template_image.width, result.template_image.height],
        "usedPerspective": result.template_image.used_perspective,
        "peakWorkingSetBytes": _working_set_bytes(),
        "elapsedMs": elapsed_ms,
        "roundtripPassed": True,
        "ocrCalls": 0,
    }


def memory_gate(runs):
    assert [row["version"] for row in runs] == ["v3.1.3", "v3.4.1"], "Invalid memory comparison versions"
    assert all(row["roundtripPassed"] and row["ocrCalls"] == 0 for row in runs), "Invalid memory safety evidence"
    baseline, candidate = [row["peakWorkingSetBytes"] for row in runs]
    assert baseline > 0 and candidate > 0, "Missing memory measurement"
    return candidate <= baseline * 1.2 and candidate <= baseline + 64 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.child:
        print(json.dumps(child(args.child)))
        return
    if args.output is None:
        parser.error("--output is required")
    identity = {"code": _code_identity(), "harnessSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    if args.output.exists():
        saved = json.loads(args.output.read_text(encoding="utf-8"))
        assert saved["identity"] == digest(identity), "Stale memory boundary result"
        assert saved["checksum"] == digest(saved["runs"]), "Corrupt memory boundary result"
        assert memory_gate(saved["runs"]) and saved.get("memoryGatePassed") is True, "Cached memory gate failed"
        return
    runs = []
    for version in ("v3.1.3", "v3.4.1"):
        result = subprocess.run(
            [sys.executable, "-m", "scripts.validate_preprocess_memory_v34", "--child", version],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        runs.append(json.loads(result.stdout))
    gate = memory_gate(runs)
    payload = {
        "identity": digest(identity),
        "code": identity,
        "runs": runs,
        "checksum": digest(runs),
        "memoryGatePassed": gate,
    }
    _atomic_json(args.output, payload)
    print(json.dumps(payload))
    assert gate, "Candidate exceeds baseline +20% / +64MiB memory guard"


if __name__ == "__main__":
    main()
