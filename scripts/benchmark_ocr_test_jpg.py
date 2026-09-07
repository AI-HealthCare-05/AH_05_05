"""Six fresh end-to-end service calls on test.jpg; never replay OCR/LLM."""

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Config
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from app.services.medication_ocr_v3.providers.openai_grounded import OpenAIGroundedStructurer
from app.services.medication_ocr_v3.service import MedicationOcrV3Service
from app.services.ocr_image_input import ValidatedImage
from scripts.benchmark_ocr_llm_baseline import CORPUS, FIELDS, ROOT, SOURCE, STATUSES, RecordingStructurer, distribution
from scripts.benchmark_ocr_postprocess import code_hash, digest, save_checkpoint
from scripts.evaluate_ocr_v34 import score_sample

OUTPUT = ROOT / ".context/ocr-test-jpg-live-20260907"
ORDER = ("v3.1.3", "v3.4.1", "v3.4.1", "v3.1.3", "v3.1.3", "v3.4.1")


async def main():
    if OUTPUT.exists():
        raise ValueError("Preserve prior live measurements; select a new OUTPUT directory")
    config = Config()
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["images"] if item["file"] == "test.jpg")
    truth = next(
        item["rows"]
        for item in json.loads((CORPUS / "ground-truth.json").read_text(encoding="utf-8"))["samples"]
        if item["id"] == entry["id"]
    )
    statuses = next(
        item["rows"]
        for item in json.loads(STATUSES.read_text(encoding="utf-8"))["samples"]
        if item["id"] == entry["id"]
    )
    source = SOURCE / "test.jpg"
    frozen_code = code_hash(ROOT)
    provenance = {
        "input": entry,
        "codeSha256": frozen_code,
        "model": config.OPENAI_MODEL,
        "order": ORDER,
        "truthSha256": digest(truth),
        "statusesSha256": digest(statuses),
        "harnessSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "timing": "file-read through complete review JSON; excludes upload, queue, DB and browser",
        "providerReuse": False,
        "responseReplay": False,
    }
    identity = digest(provenance)
    save_checkpoint(OUTPUT / "manifest.json", {"identity": identity, **provenance})
    runs = []
    for ordinal, version in enumerate(ORDER, 1):
        # Connections are fresh in every run; construction is outside the timer.
        async with (
            ClovaGeneralOcrProvider(
                endpoint=config.CLOVA_GENERAL_OCR_INVOKE_URL, secret=config.CLOVA_GENERAL_OCR_SECRET.get_secret_value()
            ) as provider,
            OpenAIGroundedStructurer(
                api_key=config.OPENAI_API_KEY.get_secret_value(), model=config.OPENAI_MODEL
            ) as llm,
        ):
            recorder = RecordingStructurer(llm)
            start_utc = datetime.now(UTC).isoformat()
            print(f"START {ordinal} {version} {start_utc}", flush=True)
            started = time.perf_counter()
            content = source.read_bytes()
            if hashlib.sha256(content).hexdigest() != entry["sha256"]:
                raise ValueError("source changed")
            image = ValidatedImage(
                filename="reference.jpg", media_type="image/jpeg", provider_format="jpg", content=content
            )
            result = await MedicationOcrV3Service(
                provider=provider, structurer=recorder, preprocess_version=version
            ).analyze(image)
            final_json = json.dumps(result.project_review, ensure_ascii=False)
            elapsed_ms = (time.perf_counter() - started) * 1000
            end_utc = datetime.now(UTC).isoformat()
            stages = {stage["name"]: stage for stage in result.stages}
            if stages["ocr"]["callCount"] != 1 or stages["llm"]["callCount"] != 1 or len(recorder.calls) != 1:
                raise ValueError("expected one real OCR and one real LLM call")
            if any(stage["status"] != "succeeded" for stage in result.stages):
                raise ValueError("pipeline stage did not succeed")
            if code_hash(ROOT) != frozen_code:
                raise ValueError("pipeline changed during measurement")
            run = {
                "identity": identity,
                "ordinal": ordinal,
                "version": version,
                "startUtc": start_utc,
                "endUtc": end_utc,
                "wallMs": elapsed_ms,
                "stages": result.stages,
                "llmCalls": recorder.calls,
                "reviewSha256": hashlib.sha256(final_json.encode()).hexdigest(),
                "medications": [
                    {key: row[key] for key in FIELDS if key in row} for row in result.project_review["medications"]
                ],
                "score": score_sample(truth, result.project_review["medications"], statuses),
            }
            save_checkpoint(OUTPUT / f"run-{ordinal:02}-{version}.json", run)
            runs.append(run)
            print(
                "FINISH "
                + json.dumps(
                    {key: run[key] for key in ("ordinal", "version", "startUtc", "endUtc", "wallMs", "stages", "score")}
                ),
                flush=True,
            )
    summary = {}
    for version in sorted(set(ORDER)):
        selected = [run for run in runs if run["version"] == version]
        summary[version] = {
            "wallMs": distribution([run["wallMs"] for run in selected]),
            "stageMeanMs": {
                name: sum(
                    next(stage["elapsedMs"] for stage in run["stages"] if stage["name"] == name) for run in selected
                )
                / len(selected)
                for name in ("preprocess", "ocr", "candidate", "llm", "validate")
            },
            "correct": [run["score"]["legacyCorrect"] for run in selected],
            "total": [run["score"]["legacyTotal"] for run in selected],
            "rows": [run["score"]["predictedRows"] for run in selected],
        }
    save_checkpoint(OUTPUT / "summary.json", {"identity": identity, "versions": summary})
    print("SUMMARY " + json.dumps(summary), flush=True)


if __name__ == "__main__":
    asyncio.run(main())

