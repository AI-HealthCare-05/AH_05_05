"""Current production LLM baseline with a same-OCR no-LLM control.

Persist only hashes, timing, and scores. Each image is an atomic resumable unit;
raw OCR and document values never leave process memory except through the
existing privacy-bounded production providers.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import mimetypes
import platform
import statistics
import time
from pathlib import Path

from app.core.config import Config
from app.services.medication_ocr_v3.pipeline.analyze import AnalyzePipelineResult, analyze_processed_image
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from app.services.medication_ocr_v3.providers.openai_grounded import OpenAIGroundedStructurer
from app.services.medication_ocr_v3.service import MedicationOcrV3Service
from app.services.ocr_image_input import ValidatedImage
from scripts.benchmark_ocr_postprocess import apply_adjudications, code_hash, digest, load_checkpoint, save_checkpoint
from scripts.evaluate_ocr_v34 import FIELDS, score_sample

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT.parent / "ocr-16-three-versions-20260907"
SOURCE = ROOT.parent.parent / "docs/문서 예시/복약안내"
STATUSES = ROOT.parent / "ocr-v34-adaptive-20260907/source-status.json"
DEFAULT_OUTPUT = ROOT / ".context/ocr-llm-baseline-20260907-validated"
REPEATS = 3


def distribution(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def safe_score(review: dict, expected: list[dict], statuses: list[dict]) -> dict:
    return score_sample(expected, review.get("medications", []), statuses)


def aggregate_scores(scores: list[dict]) -> dict:
    correct = sum(score["legacyCorrect"] for score in scores)
    total = sum(score["legacyTotal"] for score in scores)
    fields = {name: {key: 0 for key in ("tp", "fp", "fn")} for name in FIELDS}
    for score in scores:
        for name, counts in score["fieldCounts"].items():
            for key in ("tp", "fp", "fn"):
                fields[name][key] += counts[key]
    return {
        "correct": correct,
        "total": total,
        "accuracy": correct / total if total else None,
        "fp": sum(counts["fp"] for counts in fields.values()),
        "fn": sum(counts["fn"] for counts in fields.values()),
        "fields": fields,
        "predictedRows": sum(score["predictedRows"] for score in scores),
    }


def summarize(cases: list[dict]) -> dict:
    active = [case for case in cases if not case["recapture"]]
    llm_stages = [next(stage for stage in case["stages"] if stage["name"] == "llm") for case in cases]
    calls = [call for case in cases for call in case["llmCalls"]]
    repeats = len(cases[0]["llmScores"])
    accuracy = {
        "control": aggregate_scores([case["controlScore"] for case in cases]),
        "llmFirstRun": aggregate_scores([case["llmScores"][0] for case in cases]),
        "llmRepeated": [aggregate_scores([case["llmScores"][i] for case in cases]) for i in range(repeats)],
    }
    if all("controlAdjudicatedScore" in case for case in cases):
        accuracy["adjudicatedControl"] = aggregate_scores([case["controlAdjudicatedScore"] for case in cases])
        accuracy["adjudicatedLlmRepeated"] = [
            aggregate_scores([case["llmAdjudicatedScores"][i] for case in cases]) for i in range(repeats)
        ]
    return {
        "documents": len(cases),
        "activeDocuments": len(active),
        "recaptureDocuments": len(cases) - len(active),
        "llmInvokedDocuments": sum(stage["callCount"] > 0 for stage in llm_stages),
        "llmActualCallsIncludingRepeats": len(calls),
        "llmFailedCalls": sum(call["status"] != "succeeded" for call in calls),
        "llmCallLatencyMs": distribution([call["elapsedMs"] for call in calls]),
        "llmStageMsPerInput": statistics.fmean(stage["elapsedMs"] for stage in llm_stages),
        "serviceLatencyMs": distribution([case["serviceMs"] for case in cases]),
        "activeServiceLatencyMs": distribution([case["serviceMs"] for case in active]),
        "controlPostOcrMs": distribution([statistics.median(case["controlMs"]) for case in active]),
        "firstServiceStageMsPerInput": {
            name: statistics.fmean(
                next((stage["elapsedMs"] for stage in case["stages"] if stage["name"] == name), 0) for case in cases
            )
            for name in ("preprocess", "ocr", "candidate", "llm", "validate")
        },
        "accuracy": accuracy,
    }


def load_case(path: Path, identity: str, entry: dict) -> dict:
    case = load_checkpoint(path, identity)
    if case["id"] != entry["id"] or case["sourceSha256"] != entry["sha256"]:
        raise ValueError("checkpoint sample identity mismatch")
    return case


def validate_sources(entries: list[dict], source_root: Path) -> None:
    for entry in entries:
        if hashlib.sha256((source_root / entry["file"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"source identity changed: {entry['id']}")


class RecordingProvider:
    def __init__(self, provider) -> None:
        self.provider = provider
        self.result = None

    async def recognize(self, image: bytes):
        self.result = await self.provider.recognize(image)
        return self.result


class ReplayProvider:
    def __init__(self, result) -> None:
        self.result = result

    async def recognize(self, _image: bytes):
        return self.result


class RecordingStructurer:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.calls: list[dict] = []

    @property
    def model_version(self) -> str:
        return self.delegate.model_version

    async def select(self, catalog):
        payload = catalog.to_llm_payload()
        metadata = {
            "payloadSha256": digest(payload),
            "rows": len(payload["rows"]),
            "dateCandidates": len(payload["dateCandidates"]),
            "strengthBlocks": sum(len(row["blocks"]) for row in payload["rows"]),
        }
        started = time.perf_counter()
        try:
            result = await self.delegate.select(catalog)
        except Exception as error:
            metadata.update(status="failed", code=getattr(getattr(error, "code", None), "value", "UNEXPECTED"))
            raise
        else:
            metadata.update(status="succeeded", selectionSha256=digest(result.model_dump(by_alias=True)))
            return result
        finally:
            self.calls.append({**metadata, "elapsedMs": (time.perf_counter() - started) * 1000})


def date_hash(review: dict) -> str | None:
    field = review.get("fields", {}).get("dispensedDate")
    value = field.get("value") if isinstance(field, dict) else None
    return hashlib.sha256(str(value).encode()).hexdigest() if value else None


async def measure_case(entry: dict, config: Config, provider, structurer, expected, corrected, statuses) -> dict:
    content = (SOURCE / entry["file"]).read_bytes()
    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise ValueError("source identity changed")
    png = Path(entry["file"]).suffix.lower() == ".png"
    image = ValidatedImage(
        filename="reference.png" if png else "reference.jpg",
        media_type=mimetypes.guess_type(entry["file"])[0],
        provider_format="png" if png else "jpg",
        content=content,
    )
    recorded_provider = RecordingProvider(provider)
    recorder = RecordingStructurer(structurer)
    started = time.perf_counter()
    first = await MedicationOcrV3Service(
        provider=recorded_provider,
        structurer=recorder,
        preprocess_version=config.OCR_PREPROCESS_VERSION,
    ).analyze(image)
    service_ms = (time.perf_counter() - started) * 1000
    llm_reviews = [first.project_review]
    control_ms = []
    control = {"medications": []}
    if first.requires_recapture:
        llm_reviews *= REPEATS
    else:
        replay = ReplayProvider(recorded_provider.result)
        for repeat in range(REPEATS):
            started = time.perf_counter()
            result = await analyze_processed_image(replay, b"same-ocr-control")
            control_ms.append((time.perf_counter() - started) * 1000)
            if not isinstance(result, AnalyzePipelineResult):
                raise ValueError("control did not complete")
            if repeat and result.project_review != control:
                raise ValueError("nondeterministic control")
            control = result.project_review
            if repeat < REPEATS - 1:
                repeated = await analyze_processed_image(replay, b"same-ocr-llm", structurer=recorder)
                if not isinstance(repeated, AnalyzePipelineResult):
                    raise ValueError("LLM replay did not complete")
                llm_reviews.append(repeated.project_review)
    return {
        "id": entry["id"],
        "sourceSha256": entry["sha256"],
        "recapture": first.requires_recapture,
        "ocrSha256": digest(recorded_provider.result.as_dict()) if recorded_provider.result else None,
        "serviceMs": service_ms,
        "stages": first.stages,
        "controlMs": control_ms,
        "llmCalls": recorder.calls,
        "controlScore": safe_score(control, expected, statuses),
        "llmScores": [safe_score(review, expected, statuses) for review in llm_reviews],
        "controlAdjudicatedScore": safe_score(control, corrected, statuses),
        "llmAdjudicatedScores": [safe_score(review, corrected, statuses) for review in llm_reviews],
        "controlDateSha256": date_hash(control),
        "llmDateSha256": [date_hash(review) for review in llm_reviews],
        "controlReviewSha256": digest(control),
        "llmReviewSha256": [digest(review) for review in llm_reviews],
    }


async def run(output: Path, *, resume_only: bool = False) -> dict:
    config = Config()
    if not (config.OPENAI_API_KEY and config.CLOVA_GENERAL_OCR_SECRET and config.CLOVA_GENERAL_OCR_INVOKE_URL):
        raise ValueError("production provider configuration unavailable")
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    validate_sources(manifest["images"], SOURCE)
    truth = json.loads((CORPUS / "ground-truth.json").read_text(encoding="utf-8"))
    statuses = json.loads(STATUSES.read_text(encoding="utf-8"))
    adjudications = json.loads(
        (ROOT / "docs/ocr/postprocess-adjudications-20260907-v1.json").read_text(encoding="utf-8")
    )
    corrected = apply_adjudications(truth, manifest, adjudications)
    frozen_code = code_hash(ROOT)
    identity_data = {
        "images": manifest["images"],
        "truth": digest(truth),
        "statuses": digest(statuses),
        "adjudications": digest(adjudications),
        "codeSha256": frozen_code,
        "harnessSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "scorerSha256": hashlib.sha256((ROOT / "scripts/evaluate_ocr_v34.py").read_bytes()).hexdigest(),
        "model": config.OPENAI_MODEL,
        "preprocess": config.OCR_PREPROCESS_VERSION,
        "repeats": REPEATS,
        "temperature": 0,
        "maxOutputTokens": 4096,
        "python": platform.python_version(),
        "semantics": "one-live-service-run-and-three-same-OCR-LLM-runs; no-queue-or-DB",
    }
    identity = digest(identity_data)
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        load_checkpoint(manifest_path, identity)
    else:
        save_checkpoint(manifest_path, {"identity": identity, **identity_data})
    truth_by_id = {sample["id"]: sample["rows"] for sample in truth["samples"]}
    corrected_by_id = {sample["id"]: sample["rows"] for sample in corrected["samples"]}
    status_by_id = {sample["id"]: sample["rows"] for sample in statuses["samples"]}
    cases = []
    async with (
        ClovaGeneralOcrProvider(
            endpoint=config.CLOVA_GENERAL_OCR_INVOKE_URL, secret=config.CLOVA_GENERAL_OCR_SECRET.get_secret_value()
        ) as provider,
        OpenAIGroundedStructurer(
            api_key=config.OPENAI_API_KEY.get_secret_value(), model=config.OPENAI_MODEL
        ) as structurer,
    ):
        for entry in manifest["images"]:
            target = output / f"{entry['id']}.json"
            if target.exists():
                case = load_case(target, identity, entry)
            else:
                if resume_only:
                    raise ValueError("resume audit found missing checkpoint")
                case = await measure_case(
                    entry,
                    config,
                    provider,
                    structurer,
                    truth_by_id[entry["id"]],
                    corrected_by_id[entry["id"]],
                    status_by_id[entry["id"]],
                )
                if code_hash(ROOT) != frozen_code:
                    raise ValueError("source changed during benchmark")
                save_checkpoint(target, {"identity": identity, **case})
            cases.append(case)
            print(
                json.dumps(
                    {
                        "id": case["id"],
                        "recapture": case["recapture"],
                        "llmCalls": len(case["llmCalls"]),
                        "serviceMs": round(case["serviceMs"]),
                        "correct": case["llmScores"][0]["legacyCorrect"],
                    }
                ),
                flush=True,
            )
    if code_hash(ROOT) != frozen_code:
        raise ValueError("source changed during benchmark")
    validate_sources(manifest["images"], SOURCE)
    summary = summarize(cases)
    save_checkpoint(output / "summary.json", {"identity": identity, **summary})
    print("SUMMARY " + json.dumps(summary), flush=True)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resume-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.output, resume_only=args.resume_only))
