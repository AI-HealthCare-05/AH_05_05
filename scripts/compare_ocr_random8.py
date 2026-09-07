"""One-shot, seeded comparison; retains structured output, never raw OCR text."""

import asyncio
import hashlib
import json
import random
from pathlib import Path

from app.core.config import Config
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from app.services.medication_ocr_v3.service import MedicationOcrV3Service
from app.services.ocr_image_input import ValidatedImage

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent.parent / "docs/문서 예시/복약안내"
OUTPUT = ROOT.parent / "ocr-random8-20260907"
VERSIONS = ("v3.1.3", "v3.2.7")
SEED = 20260907


def save(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


async def main():
    eligible = sorted(
        p
        for p in SOURCE.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png"}
        and p.name != "기준점.png"
        and not p.name.startswith("Codex 이미지")
    )
    selected = random.Random(SEED).sample(eligible, 8)
    manifest = {
        "seed": SEED,
        "versions": VERSIONS,
        "llm": False,
        "repeats": 1,
        "eligible": [p.name for p in eligible],
        "images": [
            {"id": f"sample-{i + 1:02}", "file": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for i, p in enumerate(selected)
        ],
    }
    OUTPUT.mkdir(exist_ok=True)
    manifest_path = OUTPUT / "manifest.json"
    canonical = json.loads(json.dumps(manifest))
    if manifest_path.exists() and json.loads(manifest_path.read_text(encoding="utf-8")) != canonical:
        raise ValueError("Existing experiment identity differs")
    save(manifest_path, manifest)
    config = Config()
    assert config.CLOVA_GENERAL_OCR_INVOKE_URL and config.CLOVA_GENERAL_OCR_SECRET
    results = []
    async with ClovaGeneralOcrProvider(
        endpoint=config.CLOVA_GENERAL_OCR_INVOKE_URL, secret=config.CLOVA_GENERAL_OCR_SECRET.get_secret_value()
    ) as provider:
        for index, (entry, path) in enumerate(zip(manifest["images"], selected, strict=True)):
            kind = "png" if path.suffix.lower() == ".png" else "jpg"
            image = ValidatedImage(
                filename=f"reference.{kind}",
                media_type="image/png" if kind == "png" else "image/jpeg",
                provider_format=kind,
                content=path.read_bytes(),
            )
            for version in VERSIONS if index % 2 == 0 else VERSIONS[::-1]:
                target = OUTPUT / f"{entry['id']}-{version}.json"
                if target.exists():
                    run = json.loads(target.read_text(encoding="utf-8"))
                    assert run["sha256"] == entry["sha256"] and run["version"] == version
                else:
                    analysis = await MedicationOcrV3Service(
                        provider=provider, structurer=None, preprocess_version=version
                    ).analyze(image)
                    run = {
                        **entry,
                        "version": version,
                        "review": analysis.project_review,
                        "recapture": analysis.requires_recapture,
                        "reasons": analysis.recapture_reasons,
                        "stages": analysis.stages,
                    }
                    save(target, run)
                results.append(run)
                print(
                    entry["id"],
                    entry["file"],
                    version,
                    "rows=",
                    len(run["review"].get("medications", [])),
                    "recapture=",
                    run["recapture"],
                    flush=True,
                )
    assert len(results) == 16
    save(OUTPUT / "results.json", results)


if __name__ == "__main__":
    asyncio.run(main())

