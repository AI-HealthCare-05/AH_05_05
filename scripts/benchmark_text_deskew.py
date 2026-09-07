"""Compare the same eight references, with local timings separate from OCR latency."""

import asyncio
import hashlib
import json
import time
from pathlib import Path

from app.core.config import Config
from app.services.medication_ocr_v3.domain.image import QualityState
from app.services.medication_ocr_v3.pipeline.analyze import AnalyzePipelineResult, analyze_processed_image
from app.services.medication_ocr_v3.pipeline.preprocess import preprocess_image
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from scripts.compare_ocr_random8 import save

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT.parent / "ocr-text-deskew-random8-20260907"
VERSIONS = ("v3.1.3", "v3.3.1")


async def main():
    manifest = json.loads((ROOT.parent / "ocr-random8-20260907/manifest.json").read_text(encoding="utf-8"))
    identity = {
        "images": manifest["images"],
        "versions": list(VERSIONS),
        "localRepeats": 3,
        "ocrRepeats": 1,
        "codeHash": hashlib.sha256(
            b"".join(
                (ROOT / p).read_bytes()
                for p in (
                    "app/services/medication_ocr_v3/pipeline/preprocess.py",
                    "app/services/medication_ocr_v3/pipeline/text_deskew.py",
                )
            )
        ).hexdigest(),
    }
    OUTPUT.mkdir(exist_ok=True)
    identity_path = OUTPUT / "manifest.json"
    if identity_path.exists():
        assert json.loads(identity_path.read_text(encoding="utf-8")) == identity, "Stale experiment"
    save(identity_path, identity)
    config = Config()
    assert config.CLOVA_GENERAL_OCR_INVOKE_URL and config.CLOVA_GENERAL_OCR_SECRET
    all_runs = []
    async with ClovaGeneralOcrProvider(
        endpoint=config.CLOVA_GENERAL_OCR_INVOKE_URL, secret=config.CLOVA_GENERAL_OCR_SECRET.get_secret_value()
    ) as provider:
        for index, entry in enumerate(manifest["images"]):
            target = OUTPUT / f"{entry['id']}.json"
            if target.exists():
                cached = json.loads(target.read_text(encoding="utf-8"))
                assert len(cached) == 2 and {r["version"] for r in cached} == set(VERSIONS)
                assert all(r["sha256"] == entry["sha256"] for r in cached)
                all_runs.extend(cached)
                continue
            path = ROOT.parent.parent / "docs/문서 예시/복약안내" / entry["file"]
            content = path.read_bytes()
            assert hashlib.sha256(content).hexdigest() == entry["sha256"]
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            timings = {v: [] for v in VERSIONS}
            processed = {}
            for repeat in range(3):
                order = VERSIONS if (index + repeat) % 2 == 0 else VERSIONS[::-1]
                for version in order:
                    started = time.perf_counter()
                    result = preprocess_image(content, mime, preprocess_version=version)
                    timings[version].append((time.perf_counter() - started) * 1000)
                    processed[version] = result
            pair = []
            for version in VERSIONS if index % 2 == 0 else VERSIONS[::-1]:
                result = processed[version]
                recapture = result.quality_state is QualityState.RECAPTURE_REQUIRED
                review, stages = {}, []
                if not recapture:
                    analysis = await analyze_processed_image(provider, result.template_image.jpeg_bytes)
                    assert isinstance(analysis, AnalyzePipelineResult), "OCR comparison did not finish"
                    review = analysis.project_review
                    stages = [stage.as_dict() for stage in analysis.stages]
                run = {
                    **entry,
                    "version": version,
                    "preprocessMs": timings[version],
                    "operations": result.operations,
                    "recapture": recapture,
                    "review": review,
                    "stages": stages,
                }
                pair.append(run)
                print(
                    entry["id"],
                    version,
                    "rows",
                    len(review.get("medications", [])),
                    [op for op in result.operations if op.startswith("text_deskew")],
                    flush=True,
                )
                # This reference already has patient identifiers redacted by its source author.
                if entry["file"] == "output_188259254.jpg":
                    (OUTPUT / f"sample-04-{version}.jpg").write_bytes(result.template_image.jpeg_bytes)
            save(target, pair)
            all_runs.extend(pair)
    assert len(all_runs) == 16
    save(OUTPUT / "results.json", all_runs)


if __name__ == "__main__":
    asyncio.run(main())
