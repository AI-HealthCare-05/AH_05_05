"""Paired post-OCR benchmark. Raw images/OCR exist only in process memory.

Start with --serve, then send `measure <label>` or `quit` on stdin. Every
measurement runs frozen baseline and current code on identical OCR blocks in
fresh subprocesses. Persisted checkpoints contain scores/hashes, never text.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import mimetypes
import os
import statistics
import subprocess
import sys
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / ".context/compound-engineering/ce-optimize/ocr-postprocess-20260907"
SOURCE = ROOT.parent.parent / "docs/문서 예시/복약안내"
CORPUS = ROOT.parent / "ocr-16-three-versions-20260907"
STATUSES = ROOT.parent / "ocr-v34-adaptive-20260907/source-status.json"
REPEATS = 7


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def apply_adjudications(truth: dict, manifest: dict, adjudications: dict) -> dict:
    """Apply independently documented corrections to a copy, never the old gold."""
    if adjudications["baseTruthSha256"] != digest(truth):
        raise ValueError("adjudication truth identity mismatch")
    result = deepcopy(truth)
    samples = {sample["id"]: sample for sample in result["samples"]}
    hashes = {item["id"]: item["sha256"] for item in manifest["images"]}
    for correction in adjudications["replacements"]:
        if hashes[correction["id"]] != correction["sourceSha256"]:
            raise ValueError("adjudication source identity mismatch")
        row = samples[correction["id"]]["rows"][correction["row"]]
        if row[correction["field"]] != correction["old"]:
            raise ValueError("adjudication old value mismatch")
        row[correction["field"]] = correction["new"]
    return result


def code_hash(root: Path) -> str:
    package = root / "app/services/medication_ocr_v3"
    return digest(
        {
            path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(package.rglob("*"))
            if path.suffix in {".py", ".md"}
        }
    )


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps({"checksum": digest(payload), "payload": payload}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)
    load_checkpoint(path, payload["identity"])


def load_checkpoint(path: Path, identity: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value["checksum"] != digest(value["payload"]):
        raise ValueError("checkpoint checksum mismatch")
    if value["payload"]["identity"] != identity:
        raise ValueError("checkpoint identity mismatch")
    return value["payload"]


def summarize(cases: list[dict[str, Any]], runs: list[dict[str, Any]], truth: dict, statuses: dict) -> dict[str, Any]:
    from scripts.evaluate_ocr_v34 import score_sample

    truth_by_id = {sample["id"]: sample["rows"] for sample in truth["samples"]}
    status_by_id = {sample["id"]: sample["rows"] for sample in statuses["samples"]}
    case_by_id = {case["id"]: case for case in cases}
    details = []
    for run in runs:
        case = case_by_id[run["id"]]
        score = score_sample(truth_by_id[run["id"]], run["review"]["medications"], status_by_id[run["id"]])
        details.append(
            {
                "id": run["id"],
                "recapture": case["recapture"],
                "samplesMs": run["samplesMs"],
                "postOcrMs": statistics.median(run["samplesMs"]),
                "ocrMs": case["ocrMs"],
                "llmRequired": run["llmRequired"],
                "reviewSha256": digest(run["review"]),
                "score": score,
            }
        )
    correct = sum(item["score"]["legacyCorrect"] for item in details)
    total = sum(item["score"]["legacyTotal"] for item in details)
    counts = {
        key: sum(field[key] for item in details for field in item["score"]["fieldCounts"].values())
        for key in ("tp", "fp", "fn")
    }
    active = [item for item in details if not item["recapture"]]
    return {
        "post_ocr_ms": statistics.fmean(item["postOcrMs"] for item in active),
        "post_ocr_samples_ms": [
            statistics.fmean(item["samplesMs"][repeat] for item in active)
            for repeat in range(len(active[0]["samplesMs"]))
        ],
        "ocr_ms": statistics.fmean(item["ocrMs"] for item in active),
        "field_accuracy": correct / total,
        "correct_fields": correct,
        "assessable_fields": total,
        "false_positives": counts["fp"],
        "false_negatives": counts["fn"],
        "precision": counts["tp"] / (counts["tp"] + counts["fp"]),
        "recall": counts["tp"] / (counts["tp"] + counts["fn"]),
        "llm_required_count": sum(item["llmRequired"] for item in details),
        "cases": details,
    }


async def worker(code_root: Path) -> None:
    sys.path.insert(0, str(code_root))
    from app.services.medication_ocr_v3.domain.image import Point
    from app.services.medication_ocr_v3.domain.models import OcrBlock, OcrBlockIssueCode, OcrResult
    from app.services.medication_ocr_v3.pipeline.analyze import AnalyzePipelineResult, analyze_processed_image

    class ReplayProvider:
        def __init__(self, result: OcrResult) -> None:
            self.result = result

        async def recognize(self, _image: bytes) -> OcrResult:
            return self.result

    payload = json.load(sys.stdin)
    runs = []
    for case in payload["cases"]:
        if case["recapture"]:
            runs.append(
                {"id": case["id"], "samplesMs": [0] * REPEATS, "review": {"medications": []}, "llmRequired": False}
            )
            continue
        blocks = tuple(
            OcrBlock(
                block_id=block["blockId"],
                text=block["text"],
                confidence=block["confidence"],
                bbox=tuple(Point(**point) for point in block["bbox"]["points"]) if block["bbox"] else None,
                line_break=block["lineBreak"],
                issues=tuple(OcrBlockIssueCode(issue) for issue in block["issues"]),
            )
            for block in case["ocr"]["blocks"]
        )
        ocr = OcrResult(blocks)

        provider = ReplayProvider(ocr)
        samples = []
        reviews = []
        for repeat in range(REPEATS + 2):
            started = time.perf_counter()
            result = await analyze_processed_image(provider, b"in-memory-replay")
            elapsed = (time.perf_counter() - started) * 1000
            assert isinstance(result, AnalyzePipelineResult)
            if repeat >= 2:
                samples.append(elapsed)
                reviews.append(result.project_review)
        assert all(review == reviews[0] for review in reviews), "nondeterministic local output"
        runs.append(
            {
                "id": case["id"],
                "samplesMs": samples,
                "review": reviews[0],
                "llmRequired": result.diagnostics["llm"]["ambiguityRequired"],
            }
        )
    print(json.dumps({"runs": runs}, ensure_ascii=False), flush=True)


def replay(cases: list[dict[str, Any]], code_root: Path) -> list[dict[str, Any]]:
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--worker", "--code-root", str(code_root)],
        input=json.dumps({"cases": cases}, ensure_ascii=False),
        capture_output=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=180,
        check=False,
    )
    if result.returncode:
        # Do not echo subprocess input/output, which can contain OCR text.
        raise RuntimeError(f"replay subprocess failed ({result.returncode})")
    return json.loads(result.stdout)["runs"]


async def serve(run_root: Path, baseline_root: Path, adjudication_path: Path | None) -> None:  # noqa: C901
    from app.services.medication_ocr_v3.domain.image import QualityState
    from app.services.medication_ocr_v3.pipeline.preprocess import preprocess_image
    from app.services.medication_ocr_v3.pipeline.privacy_artifact import build_privacy_safe_provider_image
    from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
    from app.workers.medication_guide_ocr_worker import _general_ocr_config

    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
    original_truth = json.loads((CORPUS / "ground-truth.json").read_text(encoding="utf-8"))
    adjudications = json.loads(adjudication_path.read_text(encoding="utf-8")) if adjudication_path else None
    truth = apply_adjudications(original_truth, manifest, adjudications) if adjudications else original_truth
    statuses = json.loads(STATUSES.read_text(encoding="utf-8"))
    baseline_hash = code_hash(baseline_root)
    identity = digest(
        {
            "manifest": manifest,
            "truth": truth,
            "originalTruth": original_truth,
            "adjudications": adjudications,
            "statuses": statuses,
            "baseline": baseline_hash,
            "harness": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "version": "v3.4.1",
        }
    )
    cases = []
    endpoint, secret = _general_ocr_config()
    async with ClovaGeneralOcrProvider(endpoint=endpoint, secret=secret) as provider:
        for item in manifest["images"]:
            content = (SOURCE / item["file"]).read_bytes()
            if hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise ValueError(f"source identity changed: {item['id']}")
            processed = await asyncio.to_thread(
                preprocess_image, content, mimetypes.guess_type(item["file"])[0], preprocess_version="v3.4.1"
            )
            recapture = processed.quality_state is QualityState.RECAPTURE_REQUIRED
            case = {"id": item["id"], "recapture": recapture, "ocrMs": 0.0, "sourceSha256": item["sha256"]}
            if not recapture:
                jpeg = build_privacy_safe_provider_image(processed, ())
                started = time.perf_counter()
                ocr = await provider.recognize(jpeg)
                case.update(
                    ocrMs=(time.perf_counter() - started) * 1000, ocr=ocr.as_dict(), ocrSha256=digest(ocr.as_dict())
                )
            cases.append(case)
            save_checkpoint(
                run_root / "input-status" / f"{item['id']}.json",
                {"identity": identity, **{key: value for key, value in case.items() if key != "ocr"}},
            )
            print(f"INPUT {item['id']} ready recapture={recapture}", flush=True)
    initial = replay(cases, baseline_root)
    summary = summarize(cases, initial, truth, statuses)
    save_checkpoint(run_root / "baseline-result.json", {"identity": identity, "codeSha256": baseline_hash, **summary})
    print("BASELINE " + json.dumps({key: value for key, value in summary.items() if key != "cases"}), flush=True)
    print("READY (measure LABEL / inspect ID / quit)", flush=True)
    latest = initial
    for command in sys.stdin:
        parts = command.strip().split()
        if not parts:
            continue
        if parts[0] == "quit":
            break
        if parts[0] == "inspect" and len(parts) == 2:
            match = next(run for run in latest if run["id"] == parts[1])
            # Only medication review fields; never raw OCR or document fields.
            print(
                json.dumps({"id": match["id"], "medications": match["review"]["medications"]}, ensure_ascii=False),
                flush=True,
            )
            continue
        if len(parts) != 2 or parts[0] != "measure" or not parts[1].replace("-", "").isalnum():
            print("INVALID_COMMAND", flush=True)
            continue
        label = parts[1]
        if (run_root / label / "result.json").exists():
            print("LABEL_ALREADY_MEASURED", flush=True)
            continue
        if code_hash(baseline_root) != baseline_hash:
            raise ValueError("baseline source identity changed")
        current_hash = code_hash(ROOT)
        paired = {}
        run_pairs = {}
        roots = [("baseline", baseline_root), ("candidate", ROOT)]
        # Alternate order by experiment label to avoid always favoring warm code.
        if sum(ord(char) for char in label) % 2:
            roots.reverse()
        for name, root in roots:
            run_pairs[name] = replay(cases, root)
            paired[name] = summarize(cases, run_pairs[name], truth, statuses)
            raw_score = summarize(cases, run_pairs[name], original_truth, statuses)
            paired[name]["original_annotation"] = {
                key: raw_score[key] for key in ("correct_fields", "false_positives", "false_negatives")
            }
        if code_hash(ROOT) != current_hash:
            raise ValueError("candidate changed during measurement")
        baseline, candidate = paired["baseline"], paired["candidate"]
        candidate.update(
            regressions=sum(
                after["score"]["legacyCorrect"] < before["score"]["legacyCorrect"]
                for before, after in zip(baseline["cases"], candidate["cases"], strict=True)
            ),
            extra_false_positives=candidate["false_positives"] - baseline["false_positives"],
            extra_runtime_calls=max(0, candidate["llm_required_count"] - baseline["llm_required_count"]),
            changed_review_count=sum(
                after["reviewSha256"] != before["reviewSha256"]
                for before, after in zip(baseline["cases"], candidate["cases"], strict=True)
            ),
        )
        save_checkpoint(
            run_root / label / "result.json",
            {"identity": identity, "baselineCodeSha256": baseline_hash, "candidateCodeSha256": current_hash, **paired},
        )
        latest = run_pairs["candidate"]
        print(
            "RESULT "
            + label
            + " "
            + json.dumps(
                {name: {key: value for key, value in stats.items() if key != "cases"} for name, stats in paired.items()}
            ),
            flush=True,
        )
        print("READY", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--code-root", type=Path, default=ROOT)
    parser.add_argument("--run-root", type=Path, default=RUN_ROOT)
    parser.add_argument("--baseline-root", type=Path, default=RUN_ROOT / "baseline")
    parser.add_argument("--adjudications", type=Path)
    args = parser.parse_args()
    if args.worker:
        asyncio.run(worker(args.code_root))
    elif args.serve:
        if (args.run_root / "baseline-result.json").exists():
            parser.error("run already measured; use a new --run-root to preserve prior evidence")
        asyncio.run(serve(args.run_root, args.baseline_root, args.adjudications))
    else:
        parser.error("choose --serve or --worker")


if __name__ == "__main__":
    main()

