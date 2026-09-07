"""Fixed 16-image, three-profile evaluation; no raw OCR or patient fields persisted."""

import argparse
import asyncio
import hashlib
import json
import time
from pathlib import Path

from app.core.config import Config
from app.services.medication_ocr_v3.pipeline.preprocess import preprocess_image
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from app.services.medication_ocr_v3.service import MedicationOcrV3Service
from app.services.ocr_image_input import ValidatedImage
from scripts.compare_ocr_random8 import save

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent.parent / "docs/문서 예시/복약안내"
OUTPUT = ROOT.parent / "ocr-16-three-versions-20260907"
VERSIONS = ("v3.1.3", "v3.2.7", "v3.3.1")
EXTRA = (
    "1.jpg",
    "2.jpeg",
    "20260828_145852.jpg",
    "4.jpeg",
    "IMG_5158.jpg",
    "다운로드 (1).jpg",
    "다운로드 (4).jpg",
    "새 폴더 (2)/20160319_113942.jpg",
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def prepare():
    old = json.loads((ROOT.parent / "ocr-random8-20260907/manifest.json").read_text(encoding="utf-8"))
    names = [entry["file"] for entry in old["images"]] + list(EXTRA)
    images = [
        {"id": f"sample-{i + 1:02}", "file": name, "sha256": hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()}
        for i, name in enumerate(names)
    ]
    assert images[:8] == old["images"]
    assert len({e["sha256"] for e in images}) == 16
    files = sorted((ROOT / "app/services/medication_ocr_v3").rglob("*.py"))
    identity = {
        "images": images,
        "versions": VERSIONS,
        "llm": False,
        "ocrRepeats": 1,
        "localRepeats": 3,
        "codeHash": hashlib.sha256(
            b"".join(str(p.relative_to(ROOT)).encode() + p.read_bytes() for p in files)
        ).hexdigest(),
    }
    identity = json.loads(json.dumps(identity))
    OUTPUT.mkdir(exist_ok=True)
    target = OUTPUT / "manifest.json"
    if target.exists():
        assert json.loads(target.read_text(encoding="utf-8")) == identity, "Stale benchmark"
    save(target, identity)
    return identity


async def run(identity):
    config = Config()
    assert config.CLOVA_GENERAL_OCR_INVOKE_URL and config.CLOVA_GENERAL_OCR_SECRET
    results = []
    async with ClovaGeneralOcrProvider(
        endpoint=config.CLOVA_GENERAL_OCR_INVOKE_URL, secret=config.CLOVA_GENERAL_OCR_SECRET.get_secret_value()
    ) as provider:
        for i, entry in enumerate(identity["images"]):
            content = (SOURCE / entry["file"]).read_bytes()
            assert hashlib.sha256(content).hexdigest() == entry["sha256"]
            png = Path(entry["file"]).suffix.lower() == ".png"
            image = ValidatedImage(
                filename="reference.png" if png else "reference.jpg",
                media_type="image/png" if png else "image/jpeg",
                provider_format="png" if png else "jpg",
                content=content,
            )
            for version in VERSIONS[i % 3 :] + VERSIONS[: i % 3]:
                target = OUTPUT / f"{entry['id']}-{version}.json"
                if target.exists():
                    wrapped = json.loads(target.read_text(encoding="utf-8"))
                    result = wrapped["result"]
                    assert wrapped["checksum"] == digest(result), "Corrupt checkpoint"
                    assert result["identity"] == digest(identity) and result["version"] == version
                    assert result["sha256"] == entry["sha256"] and result["id"] == entry["id"]
                else:
                    started = time.perf_counter()
                    analysis = await MedicationOcrV3Service(
                        provider=provider, structurer=None, preprocess_version=version
                    ).analyze(image)
                    result = {
                        **entry,
                        "version": version,
                        "identity": digest(identity),
                        "wallMs": (time.perf_counter() - started) * 1000,
                        "review": analysis.project_review,
                        "recapture": analysis.requires_recapture,
                        "stages": analysis.stages,
                    }
                    save(target, {"result": result, "checksum": digest(result)})
                results.append(result)
                print(
                    entry["id"],
                    version,
                    len(result["review"].get("medications", [])),
                    round(result["wallMs"]),
                    flush=True,
                )
    assert len(results) == 48
    save(OUTPUT / "results.json", results)


def timings(identity):
    results = []
    for i, entry in enumerate(identity["images"]):
        content = (SOURCE / entry["file"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
        values = {v: [] for v in VERSIONS}
        for repeat in range(3):
            offset = (i + repeat) % 3
            for version in VERSIONS[offset:] + VERSIONS[:offset]:
                started = time.perf_counter()
                preprocess_image(
                    content,
                    "image/png" if Path(entry["file"]).suffix == ".png" else "image/jpeg",
                    preprocess_version=version,
                )
                values[version].append((time.perf_counter() - started) * 1000)
        results.append({**entry, "times": values})
        print(entry["id"], "timed", flush=True)
    save(OUTPUT / "local-timings.json", {"identity": digest(identity), "runs": results})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "run", "timings"))
    args = parser.parse_args()
    manifest = prepare()
    if args.mode == "run":
        asyncio.run(run(manifest))
    elif args.mode == "timings":
        timings(manifest)

