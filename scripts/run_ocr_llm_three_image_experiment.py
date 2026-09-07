from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from app.core.config import Config
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from app.services.medication_ocr_v3.providers.openai_grounded import OpenAIGroundedStructurer
from app.services.medication_ocr_v3.service import MedicationOcrV3Service
from app.services.ocr_image_input import ValidatedImage
from scripts.evaluate_ocr_candidate_quality import score_review, summarize_runs

DEFAULT_CANDIDATES = ("v3.2.1", "v3.2.7")
DEFAULT_REPEATS = 3
DEFAULT_EXPERIMENT_VERSION = "ocr-v3.2-llm-three-image/v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "tests/ocr_v3/fixtures/v32_llm_three_image_ground_truth.json"
DEFAULT_OUTPUT = PROJECT_ROOT.parent / "ocr-v3.2-llm-three-image"


def _percentile(values: Iterable[float], fraction: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _distribution(values: Iterable[float]) -> dict[str, float | None]:
    collected = list(values)
    return {
        "p50": _percentile(collected, 0.50),
        "p95": _percentile(collected, 0.95),
        "max": max(collected) if collected else None,
    }


def _stage(run: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    stages = run.get("stages")
    if not isinstance(stages, list):
        return {}
    return next((stage for stage in stages if isinstance(stage, Mapping) and stage.get("name") == name), {})


def _timings(runs: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    result = {
        name: _distribution(float(_stage(run, name).get("elapsedMs", 0)) for run in runs)
        for name in ("preprocess", "ocr", "candidate", "llm", "validate")
    }
    result["total"] = _distribution(float(run["totalPipelineMs"]) for run in runs)
    return result


def _quality(scores: list[Mapping[str, Any]]) -> dict[str, object]:
    expected = sum(int(score["expectedFieldCount"]) for score in scores)
    extracted = sum(int(score["extractedFieldCount"]) for score in scores)
    correct = sum(int(score["correctFieldCount"]) for score in scores)
    expected_rows = sum(int(score["expectedMedicationRowCount"]) for score in scores)
    exact_rows = sum(int(score["fullRowExactCount"]) for score in scores)
    return {
        "expectedFieldCount": expected,
        "extractedFieldCount": extracted,
        "correctFieldCount": correct,
        "fieldExtractionRate": extracted / expected if expected else 1.0,
        "exactFieldAccuracy": correct / expected if expected else 1.0,
        "fullRowExactRate": exact_rows / expected_rows if expected_rows else 1.0,
    }


def _run_summary(runs: list[dict[str, Any]]) -> dict[str, object]:
    llm_stages = [_stage(run, "llm") for run in runs]
    low_counts = [int(run["projectReview"].get("lowConfidenceCount", 0)) for run in runs]
    confidence_values = [
        float(run["avgEvidenceConfidence"]) for run in runs if run["avgEvidenceConfidence"] is not None
    ]
    return {
        "timingMs": _timings(runs),
        "llm": {
            "enabled": True,
            "callCount": sum(int(stage.get("callCount", 0)) for stage in llm_stages),
            "statusCounts": dict(Counter(str(stage.get("status", "missing")) for stage in llm_stages)),
            "codeCounts": dict(Counter(str(stage["code"]) for stage in llm_stages if "code" in stage)),
        },
        "lowConfidenceCount": {
            "min": min(low_counts),
            "max": max(low_counts),
            "mean": statistics.fmean(low_counts),
        },
        "avgEvidenceConfidence": _distribution(confidence_values),
    }


def summarize_experiment(
    manifest: Mapping[str, Any],
    results: list[dict[str, Any]],
    *,
    model: str,
    candidates: tuple[str, ...] = DEFAULT_CANDIDATES,
    control: str | None = None,
    experiment_version: str = DEFAULT_EXPERIMENT_VERSION,
) -> dict[str, object]:
    if not candidates:
        raise ValueError("at least one candidate is required")
    if len(candidates) != len(set(candidates)):
        raise ValueError("candidates must be unique")
    control = control or candidates[0]
    if control not in candidates:
        raise ValueError("control must be one of candidates")

    image_entries = {str(image["id"]): image for image in manifest["images"]}
    candidate_summaries: dict[str, Any] = {}
    for candidate in candidates:
        candidate_runs = [run for run in results if run["preprocessVersion"] == candidate]
        image_summaries: dict[str, object] = {}
        all_scores: list[Mapping[str, Any]] = []
        for image_id, image in image_entries.items():
            image_runs = [run for run in candidate_runs if run["imageId"] == image_id]
            reviews = [run["projectReview"] for run in image_runs]
            quality = summarize_runs(reviews, image["groundTruth"])
            all_scores.extend(run["score"] for run in image_runs)
            image_summaries[image_id] = {**quality, **_run_summary(image_runs)}
        candidate_summaries[candidate] = {
            "runCount": len(candidate_runs),
            "quality": _quality(all_scores),
            **_run_summary(candidate_runs),
            "images": image_summaries,
        }
    control_summary = candidate_summaries[control]
    comparisons: dict[str, object] = {}
    for candidate in candidates:
        if candidate == control:
            continue
        candidate_summary = candidate_summaries[candidate]
        comparisons[candidate] = {
            "control": control,
            "candidate": candidate,
            "exactFieldAccuracyDelta": (
                candidate_summary["quality"]["exactFieldAccuracy"] - control_summary["quality"]["exactFieldAccuracy"]
            ),
            "fieldExtractionRateDelta": (
                candidate_summary["quality"]["fieldExtractionRate"] - control_summary["quality"]["fieldExtractionRate"]
            ),
            "fullRowExactRateDelta": (
                candidate_summary["quality"]["fullRowExactRate"] - control_summary["quality"]["fullRowExactRate"]
            ),
            "lowConfidenceMeanDelta": (
                candidate_summary["lowConfidenceCount"]["mean"] - control_summary["lowConfidenceCount"]["mean"]
            ),
            "totalP50MsDeltaByImage": {
                image_id: (
                    candidate_summary["images"][image_id]["timingMs"]["total"]["p50"]
                    - control_summary["images"][image_id]["timingMs"]["total"]["p50"]
                )
                for image_id in image_entries
            },
        }
    return {
        "experimentVersion": experiment_version,
        "groundTruthVersion": manifest["version"],
        "schemaVersion": "medication-guide-review/v3",
        "ocrModel": "clova-general-v2",
        "configuredLlmModel": model,
        "llmTemperature": 0,
        "serialExecution": True,
        "candidates": candidate_summaries,
        "comparisons": comparisons,
        **({"comparison": next(iter(comparisons.values()))} if len(comparisons) == 1 else {}),
    }


async def run(
    manifest_path: Path,
    output_root: Path,
    repeats: int,
    *,
    candidates: tuple[str, ...] = DEFAULT_CANDIDATES,
    control: str | None = None,
    experiment_version: str = DEFAULT_EXPERIMENT_VERSION,
) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    settings = Config()
    endpoint = settings.CLOVA_GENERAL_OCR_INVOKE_URL
    ocr_secret = settings.CLOVA_GENERAL_OCR_SECRET
    openai_key = settings.OPENAI_API_KEY
    if endpoint is None or ocr_secret is None or openai_key is None:
        print("CLOVA General OCR and OpenAI configuration are required.", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    output_root.mkdir(parents=True, exist_ok=True)
    async with (
        ClovaGeneralOcrProvider(endpoint=endpoint, secret=ocr_secret.get_secret_value()) as provider,
        OpenAIGroundedStructurer(
            api_key=openai_key.get_secret_value(),
            model=settings.OPENAI_MODEL,
        ) as structurer,
    ):
        for image_entry in manifest["images"]:
            image_id = str(image_entry["id"])
            source = (PROJECT_ROOT / str(image_entry["source"])).resolve()
            image = ValidatedImage(
                filename=f"{image_id}.jpg",
                media_type="image/jpeg",
                provider_format="jpg",
                content=source.read_bytes(),
            )
            for repeat in range(1, repeats + 1):
                order = candidates if repeat % 2 else tuple(reversed(candidates))
                for candidate in order:
                    run_dir = output_root / image_id / candidate
                    run_path = run_dir / f"run-{repeat}.json"
                    if run_path.exists():
                        payload = json.loads(run_path.read_text(encoding="utf-8"))
                        payload["score"] = score_review(payload["projectReview"], image_entry["groundTruth"])
                        run_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                        results.append(payload)
                        print(f"SKIP existing image={image_id} version={candidate} run={repeat}", flush=True)
                        continue
                    print(f"START image={image_id} version={candidate} run={repeat}", flush=True)
                    analysis = await MedicationOcrV3Service(
                        provider=provider,
                        structurer=structurer,
                        preprocess_version=candidate,
                    ).analyze(image)
                    total_ms = sum(int(stage["elapsedMs"]) for stage in analysis.stages)
                    review = analysis.project_review
                    payload: dict[str, Any] = {
                        "imageId": image_id,
                        "preprocessVersion": candidate,
                        "run": repeat,
                        "schemaVersion": analysis.schema_version,
                        "ocrModel": analysis.ocr_model,
                        "structuringModel": analysis.structuring_model,
                        "configuredLlmModel": settings.OPENAI_MODEL,
                        "llmEnabled": True,
                        "projectReview": review,
                        "stages": analysis.stages,
                        "totalPipelineMs": total_ms,
                        "avgEvidenceConfidence": (
                            statistics.fmean(analysis.confidence_values) if analysis.confidence_values else None
                        ),
                        "score": score_review(review, image_entry["groundTruth"]),
                        "privacy": {
                            "sourcePersisted": False,
                            "ocrRawTextPersisted": False,
                            "processedImagePersisted": True,
                        },
                    }
                    run_dir.mkdir(parents=True, exist_ok=True)
                    run_path.write_text(
                        json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    if repeat == 1:
                        (run_dir / "preprocessed.jpg").write_bytes(analysis.processed_image_bytes)
                    results.append(payload)
                    llm_stage = _stage(payload, "llm")
                    print(
                        f"DONE image={image_id} version={candidate} run={repeat} "
                        f"medications={len(review.get('medications', []))} totalMs={total_ms} "
                        f"llm={llm_stage.get('status')}/{llm_stage.get('callCount')}",
                        flush=True,
                    )

    summary = summarize_experiment(
        manifest,
        results,
        model=settings.OPENAI_MODEL,
        candidates=candidates,
        control=control,
        experiment_version=experiment_version,
    )
    (output_root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"SUMMARY {output_root / 'summary.json'}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    parser.add_argument("--candidates", nargs="+", default=list(DEFAULT_CANDIDATES))
    parser.add_argument("--control")
    parser.add_argument("--experiment-version", default=DEFAULT_EXPERIMENT_VERSION)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")
    candidates = tuple(args.candidates)
    if len(candidates) != len(set(candidates)):
        parser.error("--candidates must not contain duplicates")
    control = args.control or candidates[0]
    if control not in candidates:
        parser.error("--control must be one of --candidates")
    return asyncio.run(
        run(
            args.manifest,
            args.output,
            args.repeats,
            candidates=candidates,
            control=control,
            experiment_version=args.experiment_version,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

