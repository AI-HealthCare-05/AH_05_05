"""Bounded same-OCR benchmark for legacy and semantic medication review.

Each case makes one normal no-LLM service call to obtain OCR.  The resulting
OCR object remains in RAM and is replayed into no-LLM, legacy, and semantic
arms.  Checkpoints deliberately contain only scores, field-outcome labels,
hashes, timings, and safe provider metadata--never OCR or medication values.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import mimetypes
import platform
import statistics
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import Config
from app.services.medication_ocr_v3.pipeline.analyze import AnalyzePipelineResult, analyze_processed_image
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from app.services.medication_ocr_v3.providers.openai_grounded import OpenAIGroundedStructurer
from app.services.medication_ocr_v3.service import MedicationOcrV3Service
from app.services.ocr_image_input import ValidatedImage
from scripts.benchmark_ocr_postprocess import apply_adjudications, code_hash, digest, load_checkpoint, save_checkpoint
from scripts.evaluate_ocr_v34 import FIELDS, _claimed, _equal, match_rows, score_sample

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT.parent / "ocr-16-three-versions-20260907"
SOURCE = ROOT.parent.parent / "docs/문서 예시/복약안내"
STATUSES = ROOT.parent / "ocr-v34-adaptive-20260907/source-status.json"
ADJUDICATIONS = ROOT / "docs/ocr/postprocess-adjudications-20260907-v1.json"
DEFAULT_OUTPUT = ROOT / ".context/ocr-semantic-review-20260907"
DEFAULT_SAMPLES = "sample-08"
DEFAULT_REPEATS = 3
ARM_NAMES = ("noLLM", "legacy", "semantic")


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "count": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
    }


def _status_rows(statuses: Sequence[Mapping[str, str]], expected: Sequence[Mapping[str, Any]]) -> None:
    if len(statuses) != len(expected):
        raise ValueError("truth and status row counts differ")
    for row in statuses:
        if set(row) != set(FIELDS) or any(row[field] not in {"value", "absent", "unreadable"} for field in FIELDS):
            raise ValueError("status rows must contain valid five-field source statuses")


def field_outcomes(  # noqa: C901
    expected: Sequence[Mapping[str, Any]],
    predicted: Sequence[Mapping[str, Any]],
    statuses: Sequence[Mapping[str, str]],
) -> dict[str, str]:
    """Classify scorer-aligned field outcomes without retaining field values."""
    _status_rows(statuses, expected)
    mapping = match_rows(expected, predicted, statuses)
    outcomes: dict[str, str] = {}
    matched = {index for index in mapping if index is not None}
    for row_number, (gold, status_row, prediction_index) in enumerate(
        zip(expected, statuses, mapping, strict=True), start=1
    ):
        actual: Mapping[str, Any] = {} if prediction_index is None else predicted[prediction_index]
        for field in FIELDS:
            status = status_row[field]
            if status == "unreadable":
                continue
            key = f"row-{row_number:04d}:{field}"
            claimed = _claimed(actual.get(field))
            if status == "absent":
                outcomes[key] = "wrong" if claimed else "absent"
            elif _equal(field, gold[field], actual.get(field)):
                outcomes[key] = "correct"
            else:
                outcomes[key] = "wrong" if claimed else "missing"
    # The scorer charges every claimed field in an unmatched prediction as an
    # FP.  Preserve that fact with synthetic outcome keys, never field text.
    for prediction_index, actual in enumerate(predicted, start=1):
        if prediction_index - 1 in matched:
            continue
        for field in FIELDS:
            if _claimed(actual.get(field)):
                outcomes[f"extra-{prediction_index:04d}:{field}"] = "wrong"
    return outcomes


def compare_outcomes(before: Mapping[str, str], after: Mapping[str, str]) -> dict[str, list[str]]:
    """Report recoveries, regressions, and FP transitions separately."""
    keys = sorted(set(before) | set(after))
    return {
        "restored": [key for key in keys if before.get(key) != "correct" and after.get(key) == "correct"],
        "harmed": [key for key in keys if before.get(key) == "correct" and after.get(key) != "correct"],
        "newFalsePositives": [key for key in keys if before.get(key) != "wrong" and after.get(key) == "wrong"],
        "removedFalsePositives": [key for key in keys if before.get(key) == "wrong" and after.get(key) != "wrong"],
    }


def _validate_case(case: Mapping[str, Any], entry: Mapping[str, Any], identity: str) -> dict[str, Any]:
    if case.get("identity") != identity:
        raise ValueError("checkpoint case identity mismatch")
    if case.get("id") != entry.get("id") or case.get("sourceSha256") != entry.get("sha256"):
        raise ValueError("checkpoint sample identity mismatch")
    if case.get("complete") is not True:
        raise ValueError("checkpoint case is incomplete")
    return dict(case)


async def run_cached_cases(
    entries: Sequence[Mapping[str, Any]],
    output: Path,
    identity: str,
    measure_case: Callable[[Mapping[str, Any]], Awaitable[Mapping[str, Any]]],
    *,
    resume_only: bool = False,
) -> list[dict[str, Any]]:
    """Run atomic sample units, refusing invalid cached units before any call."""
    cases: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        sample_id = entry.get("id")
        source_hash = entry.get("sha256")
        if not isinstance(sample_id, str) or not sample_id or not isinstance(source_hash, str) or not source_hash:
            raise ValueError("manifest entry must have id and sha256")
        if sample_id in seen:
            raise ValueError(f"duplicate manifest sample: {sample_id}")
        seen.add(sample_id)
        checkpoint = output / f"{sample_id}.json"
        if checkpoint.exists():
            cases.append(_validate_case(load_checkpoint(checkpoint, identity), entry, identity))
            continue
        if resume_only:
            raise ValueError(f"resume audit found missing checkpoint: {sample_id}")
        measured = dict(await measure_case(entry))
        measured.update(identity=identity, complete=True)
        cases.append(_validate_case(measured, entry, identity))
        save_checkpoint(checkpoint, measured)
        print(
            "CASE " + json.dumps({"id": sample_id, "checkpointed": True, "recapture": bool(measured.get("recapture"))}),
            flush=True,
        )
    return cases


def validate_sources(entries: Sequence[Mapping[str, Any]], source_root: Path = SOURCE) -> None:
    for entry in entries:
        if _sha256_path(source_root / str(entry["file"])) != entry["sha256"]:
            raise ValueError(f"source identity changed: {entry['id']}")


class RecordingProvider:
    """Keep the one live OCR result in memory for short-lived replay only."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.result: Any | None = None

    async def recognize(self, image: bytes) -> Any:
        self.result = await self._delegate.recognize(image)
        return self.result


class ReplayProvider:
    def __init__(self, result: Any) -> None:
        self._result = result

    async def recognize(self, _image: bytes) -> Any:
        return self._result


class RecordingStructurer:
    """Proxy all semantic contract metadata while retaining only safe call facts."""

    def __init__(self, delegate: Any) -> None:
        self._delegate = delegate
        self.calls: list[dict[str, Any]] = []

    @property
    def review_mode(self) -> Literal["legacy", "semantic"]:
        return self._delegate.review_mode

    @property
    def prompt_version(self) -> str:
        return self._delegate.prompt_version

    @property
    def schema_version(self) -> str:
        return self._delegate.schema_version

    @property
    def selection_model(self) -> type[Any]:
        return self._delegate.selection_model

    @property
    def model_version(self) -> str:
        return self._delegate.model_version

    async def select(self, catalog: Any) -> Any:
        payload = catalog.to_semantic_payload() if self.review_mode == "semantic" else catalog.to_llm_payload()
        metadata: dict[str, Any] = {
            "mode": self.review_mode,
            "model": self.model_version,
            "promptVersion": self.prompt_version,
            "schemaVersion": self.schema_version,
            "selectionModel": self.selection_model.__name__,
            "payloadSha256": digest(payload),
            "rowCount": len(payload["rows"]),
            "blockCount": sum(len(row["blocks"]) for row in payload["rows"]),
        }
        started = time.perf_counter()
        try:
            result = await self._delegate.select(catalog)
        except Exception as error:
            metadata.update(status="failed", code=getattr(getattr(error, "code", None), "value", "UNEXPECTED"))
            raise
        else:
            metadata.update(status="succeeded", selectionSha256=digest(result.model_dump(by_alias=True)))
            return result
        finally:
            self.calls.append({**metadata, "elapsedMs": (time.perf_counter() - started) * 1000})


def _review(result: AnalyzePipelineResult) -> dict[str, Any]:
    review = result.project_review
    if not isinstance(review, dict) or not isinstance(review.get("medications"), list):
        raise ValueError("pipeline did not return a medication review")
    return review


def _score_review(
    review: Mapping[str, Any], truth: Sequence[Mapping[str, Any]], statuses: Sequence[Mapping[str, str]]
) -> dict[str, Any]:
    medications = review.get("medications")
    if not isinstance(medications, list) or not all(isinstance(row, Mapping) for row in medications):
        raise ValueError("review medications must be rows")
    rows = [dict(row) for row in medications]
    return {
        "score": score_sample(truth, rows, statuses),
        "outcomes": field_outcomes(truth, rows, statuses),
        "reviewSha256": digest(review),
    }


def _safe_issue_codes(result: AnalyzePipelineResult) -> list[str]:
    issues = result.issues or ()
    return sorted(
        {str(issue["code"]) for issue in issues if isinstance(issue, Mapping) and isinstance(issue.get("code"), str)}
    )


def _replay_stage_status(result: AnalyzePipelineResult) -> list[dict[str, object]]:
    """Mark replay OCR as in-memory so stage metadata cannot imply a new call."""
    stages = []
    for stage in result.stages:
        value = stage.as_dict()
        if stage.name == "ocr":
            value.update(replayed=True, callCount=0, actualExternalCallCount=0)
        stages.append(value)
    return stages


async def _replay_arm(
    provider: ReplayProvider,
    *,
    structurer: RecordingStructurer | None,
    truth: Sequence[Mapping[str, Any]],
    corrected: Sequence[Mapping[str, Any]],
    statuses: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    started = time.perf_counter()
    result = await analyze_processed_image(provider, b"same-ocr-benchmark", structurer=structurer)
    elapsed_ms = (time.perf_counter() - started) * 1000
    if not isinstance(result, AnalyzePipelineResult):
        raise ValueError("same-OCR replay did not complete")
    review = _review(result)
    return {
        "postOcrMs": elapsed_ms,
        "original": _score_review(review, truth, statuses),
        "corrected": _score_review(review, corrected, statuses),
        "stageStatus": _replay_stage_status(result),
        "issueCodes": _safe_issue_codes(result),
    }


async def measure_case(  # noqa: C901
    entry: Mapping[str, Any],
    *,
    config: Config,
    provider: Any,
    legacy: RecordingStructurer,
    semantic: RecordingStructurer,
    truth: Sequence[Mapping[str, Any]],
    corrected: Sequence[Mapping[str, Any]],
    statuses: Sequence[Mapping[str, str]],
    repeats: int,
) -> dict[str, Any]:
    """Make exactly one live no-LLM service call then replay that OCR in RAM."""
    started = time.perf_counter()
    content = (SOURCE / str(entry["file"])).read_bytes()
    if hashlib.sha256(content).hexdigest() != entry["sha256"]:
        raise ValueError(f"source identity changed: {entry['id']}")
    suffix = Path(str(entry["file"])).suffix.lower()
    image = ValidatedImage(
        filename=f"benchmark{suffix}",
        media_type=mimetypes.guess_type(str(entry["file"]))[0],
        provider_format="png" if suffix == ".png" else "jpg",
        content=content,
    )
    recording_provider = RecordingProvider(provider)
    service_result = await MedicationOcrV3Service(
        provider=recording_provider,
        structurer=None,
        preprocess_version=config.OCR_PREPROCESS_VERSION,
    ).analyze(image)
    # This serialization is intentionally in-memory.  It gives the service
    # timing the documented end boundary without emitting medication values.
    json.dumps(service_result.project_review, ensure_ascii=False, separators=(",", ":"))
    service_ms = (time.perf_counter() - started) * 1000
    recapture = service_result.requires_recapture
    arms: dict[str, list[dict[str, Any]]] = {name: [] for name in ARM_NAMES}
    if recapture:
        empty = {"medications": []}
        for arm in ARM_NAMES:
            arms[arm] = [
                {
                    "postOcrMs": 0.0,
                    "original": _score_review(empty, truth, statuses),
                    "corrected": _score_review(empty, corrected, statuses),
                    "stageStatus": [],
                    "issueCodes": ["RECAPTURE_REQUIRED"],
                }
                for _ in range(repeats)
            ]
    else:
        if recording_provider.result is None:
            raise ValueError("live service completed without OCR result")
        replay = ReplayProvider(recording_provider.result)
        for repeat in range(repeats):
            arms["noLLM"].append(
                await _replay_arm(replay, structurer=None, truth=truth, corrected=corrected, statuses=statuses)
            )
            ordered = (("legacy", legacy), ("semantic", semantic))
            if repeat % 2:
                ordered = tuple(reversed(ordered))
            for name, recorder in ordered:
                arms[name].append(
                    await _replay_arm(
                        replay,
                        structurer=recorder,
                        truth=truth,
                        corrected=corrected,
                        statuses=statuses,
                    )
                )
        service_review_hash = digest(service_result.project_review)
        if any(run["original"]["reviewSha256"] != service_review_hash for run in arms["noLLM"]):
            raise ValueError("same-OCR noLLM replay does not match the live noLLM service review")
    for arm in ("legacy", "semantic"):
        for repeat, run in enumerate(arms[arm]):
            for annotation in ("original", "corrected"):
                run[f"comparisonVsNoLlm{annotation.title()}"] = compare_outcomes(
                    arms["noLLM"][repeat][annotation]["outcomes"], run[annotation]["outcomes"]
                )
    for repeat, semantic_run in enumerate(arms["semantic"]):
        for annotation in ("original", "corrected"):
            semantic_run[f"comparisonVsLegacy{annotation.title()}"] = compare_outcomes(
                arms["legacy"][repeat][annotation]["outcomes"], semantic_run[annotation]["outcomes"]
            )
    return {
        "id": entry["id"],
        "sourceSha256": entry["sha256"],
        "complete": True,
        "recapture": recapture,
        "serviceNoLlmMs": service_ms,
        "serviceStages": service_result.stages,
        "serviceNoLlmReviewSha256": digest(service_result.project_review),
        "ocrSha256": digest(recording_provider.result.as_dict()) if recording_provider.result is not None else None,
        "arms": arms,
        "llmCalls": {"legacy": legacy.calls, "semantic": semantic.calls},
    }


def aggregate_scores(scores: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    fields = {field: {name: 0 for name in ("tp", "fp", "fn")} for field in FIELDS}
    totals = {
        name: 0 for name in ("legacyCorrect", "legacyTotal", "strictExact", "strictAssessable", "documentSuccess")
    }
    for score in scores:
        for name in totals:
            totals[name] += int(score[name])
        for field in FIELDS:
            for name in fields[field]:
                fields[field][name] += int(score["fieldCounts"][field][name])
    fp = sum(count["fp"] for count in fields.values())
    fn = sum(count["fn"] for count in fields.values())
    return {
        "correct": totals["legacyCorrect"],
        "total": totals["legacyTotal"],
        "accuracy": totals["legacyCorrect"] / totals["legacyTotal"] if totals["legacyTotal"] else None,
        "falsePositives": fp,
        "falseNegatives": fn,
        "strictExact": totals["strictExact"],
        "strictAssessable": totals["strictAssessable"],
        "strictAccuracy": totals["strictExact"] / totals["strictAssessable"] if totals["strictAssessable"] else None,
        "documentSuccesses": totals["documentSuccess"],
        "fieldCounts": fields,
    }


def _aggregate_comparisons(
    cases: Sequence[Mapping[str, Any]],
    arm: str,
    repeat: int,
    annotation: str,
    *,
    baseline: str = "NoLlm",
) -> dict[str, Any]:
    key = f"comparisonVs{baseline}{annotation.title()}"
    grouped = {name: [] for name in ("restored", "harmed", "newFalsePositives", "removedFalsePositives")}
    for case in cases:
        comparison = case["arms"][arm][repeat][key]
        for name in grouped:
            grouped[name].extend(f"{case['id']}:{outcome}" for outcome in comparison[name])
    return {name: {"count": len(items), "fields": sorted(items)} for name, items in grouped.items()}


def summarize(cases: Sequence[Mapping[str, Any]], repeats: int) -> dict[str, Any]:
    arms: dict[str, Any] = {}
    for arm in ARM_NAMES:
        per_repeat = []
        all_original = []
        all_corrected = []
        for repeat in range(repeats):
            runs = [case["arms"][arm][repeat] for case in cases]
            original = [run["original"]["score"] for run in runs]
            corrected = [run["corrected"]["score"] for run in runs]
            all_original.extend(original)
            all_corrected.extend(corrected)
            item: dict[str, Any] = {
                "repeat": repeat + 1,
                "original": aggregate_scores(original),
                "corrected": aggregate_scores(corrected),
                "postOcrReplayMs": distribution([float(run["postOcrMs"]) for run in runs]),
            }
            if arm != "noLLM":
                item["comparisonVsNoLlm"] = {
                    "original": _aggregate_comparisons(cases, arm, repeat, "original"),
                    "corrected": _aggregate_comparisons(cases, arm, repeat, "corrected"),
                }
            if arm == "semantic":
                item["comparisonVsLegacy"] = {
                    "original": _aggregate_comparisons(cases, arm, repeat, "original", baseline="Legacy"),
                    "corrected": _aggregate_comparisons(cases, arm, repeat, "corrected", baseline="Legacy"),
                }
            per_repeat.append(item)
        call_records = [call for case in cases for call in case["llmCalls"].get(arm, [])] if arm != "noLLM" else []
        arms[arm] = {
            "repeats": per_repeat,
            "allRepeats": {"original": aggregate_scores(all_original), "corrected": aggregate_scores(all_corrected)},
            "llmActualCalls": len(call_records),
            "llmFailedCalls": sum(call.get("status") != "succeeded" for call in call_records),
            "llmCallMs": distribution([float(call["elapsedMs"]) for call in call_records]),
        }
    active = [case for case in cases if not case["recapture"]]
    return {
        "documents": len(cases),
        "activeDocuments": len(active),
        "recaptureDocuments": len(cases) - len(active),
        "serviceNoLlm": {
            "oneLiveServiceCallPerCase": True,
            "serviceMs": distribution([float(case["serviceNoLlmMs"]) for case in cases]),
            "activeServiceMs": distribution([float(case["serviceNoLlmMs"]) for case in active]),
        },
        "postOcrReplay": {"replayedOcr": True, "arms": arms},
    }


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _select_entries(manifest: Mapping[str, Any], sample_csv: str) -> list[dict[str, Any]]:
    requested = [sample.strip() for sample in sample_csv.split(",") if sample.strip()]
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("--samples must be a non-empty comma-separated unique sample list")
    entries = {entry["id"]: entry for entry in manifest["images"]}
    unknown = [sample for sample in requested if sample not in entries]
    if unknown:
        raise ValueError(f"unknown samples: {', '.join(unknown)}")
    return [dict(entries[sample]) for sample in requested]


def _identity_data(
    *,
    entries: Sequence[Mapping[str, Any]],
    manifest: Mapping[str, Any],
    truth: Mapping[str, Any],
    statuses: Mapping[str, Any],
    adjudications: Mapping[str, Any],
    model: str,
    preprocess: str,
    repeats: int,
) -> dict[str, Any]:
    prompts = ROOT / "app/services/medication_ocr_v3/prompts"
    dependencies = {
        "harness": _sha256_path(Path(__file__)),
        "scorer": _sha256_path(ROOT / "scripts/evaluate_ocr_v34.py"),
        "checkpoint": _sha256_path(ROOT / "scripts/benchmark_ocr_postprocess.py"),
        "legacyPrompt": _sha256_path(prompts / "medication_grounding_v3.md"),
        "semanticPrompt": _sha256_path(prompts / "medication_semantic_review_v1.md"),
    }
    inputs = {
        "manifest": _sha256_path(CORPUS / "manifest.json"),
        "truth": _sha256_path(CORPUS / "ground-truth.json"),
        "statuses": _sha256_path(STATUSES),
        "adjudications": _sha256_path(ADJUDICATIONS),
    }
    return {
        "protocol": "one-live-noLLM-service-call; RAM replay noLLM/legacy/semantic; alternating LLM order",
        "entries": list(entries),
        "manifestSha256": digest(manifest),
        "truthSha256": digest(truth),
        "statusesSha256": digest(statuses),
        "correctedTruthSha256": digest(apply_adjudications(dict(truth), dict(manifest), dict(adjudications))),
        "inputFiles": inputs,
        "dependencies": dependencies,
        "ocrPackageSha256": code_hash(ROOT),
        "model": model,
        "preprocess": preprocess,
        "reviewModes": list(ARM_NAMES),
        "repeats": repeats,
        "temperature": 0,
        "maxOutputTokens": {"legacy": 4096, "semantic": 16384},
        "python": platform.python_version(),
    }


def _assert_frozen(identity_data: Mapping[str, Any], expected_identity: str) -> None:
    current = _identity_data(
        entries=identity_data["entries"],
        manifest=_load_json(CORPUS / "manifest.json"),
        truth=_load_json(CORPUS / "ground-truth.json"),
        statuses=_load_json(STATUSES),
        adjudications=_load_json(ADJUDICATIONS),
        model=str(identity_data["model"]),
        preprocess=str(identity_data["preprocess"]),
        repeats=int(identity_data["repeats"]),
    )
    if digest(current) != expected_identity:
        raise ValueError("benchmark inputs, code, prompt, or dependency changed during run")


async def run(
    output: Path,
    *,
    samples: str = DEFAULT_SAMPLES,
    repeats: int = DEFAULT_REPEATS,
    model: str | None = None,
    resume_only: bool = False,
) -> dict[str, Any]:
    if not 1 <= repeats <= 5:
        raise ValueError("--repeats must be between 1 and 5")
    config = Config()
    manifest = _load_json(CORPUS / "manifest.json")
    truth = _load_json(CORPUS / "ground-truth.json")
    statuses = _load_json(STATUSES)
    adjudications = _load_json(ADJUDICATIONS)
    entries = _select_entries(manifest, samples)
    validate_sources(entries)
    selected_model = model or config.OPENAI_MODEL
    identity_data = _identity_data(
        entries=entries,
        manifest=manifest,
        truth=truth,
        statuses=statuses,
        adjudications=adjudications,
        model=selected_model,
        preprocess=config.OCR_PREPROCESS_VERSION,
        repeats=repeats,
    )
    identity = digest(identity_data)
    manifest_path = output / "manifest.json"
    if manifest_path.exists():
        load_checkpoint(manifest_path, identity)
    else:
        save_checkpoint(manifest_path, {"identity": identity, **identity_data})
    truth_by_id = {sample["id"]: sample["rows"] for sample in truth["samples"]}
    corrected = apply_adjudications(truth, manifest, adjudications)
    corrected_by_id = {sample["id"]: sample["rows"] for sample in corrected["samples"]}
    status_by_id = {sample["id"]: sample["rows"] for sample in statuses["samples"]}

    async def forbidden(_entry: Mapping[str, Any]) -> Mapping[str, Any]:
        raise AssertionError("resume-only mode must not call an external provider")

    if resume_only:
        cases = await run_cached_cases(entries, output, identity, forbidden, resume_only=True)
    else:
        if not (config.OPENAI_API_KEY and config.CLOVA_GENERAL_OCR_SECRET and config.CLOVA_GENERAL_OCR_INVOKE_URL):
            raise ValueError("production provider configuration unavailable")
        async with (
            ClovaGeneralOcrProvider(
                endpoint=config.CLOVA_GENERAL_OCR_INVOKE_URL,
                secret=config.CLOVA_GENERAL_OCR_SECRET.get_secret_value(),
            ) as provider,
            OpenAIGroundedStructurer(
                api_key=config.OPENAI_API_KEY.get_secret_value(),
                model=selected_model,
                review_mode="legacy",
                legacy_prompt_version="medication_grounding_v3",
            ) as legacy_delegate,
            OpenAIGroundedStructurer(
                api_key=config.OPENAI_API_KEY.get_secret_value(), model=selected_model, review_mode="semantic"
            ) as semantic_delegate,
        ):

            async def measure(entry: Mapping[str, Any]) -> Mapping[str, Any]:
                validate_sources(entries)
                _assert_frozen(identity_data, identity)
                legacy = RecordingStructurer(legacy_delegate)
                semantic = RecordingStructurer(semantic_delegate)
                case = await measure_case(
                    entry,
                    config=config,
                    provider=provider,
                    legacy=legacy,
                    semantic=semantic,
                    truth=truth_by_id[entry["id"]],
                    corrected=corrected_by_id[entry["id"]],
                    statuses=status_by_id[entry["id"]],
                    repeats=repeats,
                )
                _assert_frozen(identity_data, identity)
                return case

            cases = await run_cached_cases(entries, output, identity, measure)
    _assert_frozen(identity_data, identity)
    validate_sources(entries)
    summary = summarize(cases, repeats)
    save_checkpoint(output / "summary.json", {"identity": identity, **summary})
    print("SUMMARY " + json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", default=DEFAULT_SAMPLES, help="comma-separated manifest IDs (default: sample-08)")
    parser.add_argument("--repeats", default=DEFAULT_REPEATS, type=int, help="same-OCR repeats per arm (1..5)")
    parser.add_argument("--model", help="OpenAI model for both LLM arms (default: configured model)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--resume-only", action="store_true", help="audit and summarize checkpoints without provider calls"
    )
    args = parser.parse_args(argv)
    try:
        asyncio.run(
            run(
                args.output,
                samples=args.samples,
                repeats=args.repeats,
                model=args.model,
                resume_only=args.resume_only,
            )
        )
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

