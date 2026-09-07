"""Strict integrity and completeness audit for v3.4 OCR experiment artifacts.

This promotion gate validates persisted evidence and reports latency aggregates.
It intentionally does not rerun OCR or recompute evaluation scores.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "ocr-v34-artifact-audit/1"
EXPECTED_LOCAL_REPEATS = 3


class AuditError(ValueError):
    """Raised when persisted experiment evidence is not promotion-safe."""


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _file_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise AuditError(f"cannot read required file: {path}") from error


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except AuditError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AuditError(f"invalid JSON file: {path}") from error


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AuditError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise AuditError(f"{label} must be a list")
    return value


def _unique_strings(value: Any, label: str) -> list[str]:
    items = _list(value, label)
    if not items or any(not isinstance(item, str) or not item for item in items):
        raise AuditError(f"{label} must contain non-empty strings")
    if len(items) != len(set(items)):
        raise AuditError(f"{label} contains duplicates")
    return items


def _sha256(value: Any, label: str) -> str:
    invalid_character = isinstance(value, str) and any(character not in "0123456789abcdef" for character in value)
    if not isinstance(value, str) or len(value) != 64 or invalid_character:
        raise AuditError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _finite_nonnegative(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AuditError(f"{label} must be a finite nonnegative number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise AuditError(f"{label} must be a finite nonnegative number")
    return number


def _safe_component(value: str, label: str) -> None:
    if Path(value).name != value or value in {".", ".."} or "/" in value or "\\" in value:
        raise AuditError(f"{label} is not safe for a checkpoint filename")


def _format_cells(cells: set[tuple[str, ...]]) -> str:
    return ",".join("/".join(cell) for cell in sorted(cells)) or "none"


def _validate_grid(
    records: list[Any],
    *,
    expected: set[tuple[str, ...]],
    fields: tuple[str, ...],
    label: str,
) -> dict[tuple[str, ...], Mapping[str, Any]]:
    indexed: dict[tuple[str, ...], Mapping[str, Any]] = {}
    duplicates: set[tuple[str, ...]] = set()
    for index, raw in enumerate(records):
        record = _mapping(raw, f"{label} record {index}")
        key_values = tuple(record.get(field) for field in fields)
        if any(not isinstance(value, str) for value in key_values):
            raise AuditError(f"{label} record {index} has invalid grid identity")
        key = tuple(str(value) for value in key_values)
        if key in indexed:
            duplicates.add(key)
        indexed[key] = record
    actual = set(indexed)
    missing, extra = expected - actual, actual - expected
    if missing or extra or duplicates:
        raise AuditError(
            f"{label} grid mismatch: missing={_format_cells(missing)}; "
            f"extra={_format_cells(extra)}; duplicates={_format_cells(duplicates)}"
        )
    return indexed


def _validate_transform(record: Mapping[str, Any], *, image_hash: str, variant: str, label: str) -> Mapping[str, Any]:
    transform = _mapping(record.get("transform"), f"{label} transform")
    if transform.get("sourceSha256") != image_hash:
        raise AuditError(f"{label} transform sourceSha256 does not match manifest")
    transformed = _sha256(transform.get("transformedSha256"), f"{label} transformedSha256")
    parameters = _mapping(transform.get("parameters"), f"{label} transform parameters")
    if parameters.get("name") != variant:
        raise AuditError(f"{label} transform name does not match variant")
    if variant == "identity" and transformed != image_hash:
        raise AuditError(f"{label} identity transform changed the source hash")
    return transform


def _validate_checkpoint(path: Path, expected_result: Mapping[str, Any], label: str) -> None:
    envelope = _mapping(_load_json(path), f"{label} checkpoint")
    if set(envelope) != {"result", "checksum"}:
        raise AuditError(f"{label} checkpoint envelope must contain exactly result and checksum")
    result = _mapping(envelope.get("result"), f"{label} checkpoint result")
    if envelope.get("checksum") != digest(result):
        raise AuditError(f"{label} checkpoint checksum mismatch")
    if result != expected_result:
        raise AuditError(f"{label} checkpoint payload does not equal aggregate payload")


def _validate_checkpoint_directory(
    path: Path,
    expected_records: Mapping[tuple[str, ...], Mapping[str, Any]],
    filename,
    label: str,
) -> None:
    expected_names = {filename(key) for key in expected_records}
    try:
        actual_names = {item.name for item in path.glob("*.json") if item.is_file()}
    except OSError as error:
        raise AuditError(f"cannot inspect {label} checkpoint directory: {path}") from error
    missing, extra = expected_names - actual_names, actual_names - expected_names
    if missing or extra:
        raise AuditError(
            f"{label} checkpoint files mismatch: missing={','.join(sorted(missing)) or 'none'}; "
            f"extra={','.join(sorted(extra)) or 'none'}"
        )
    for key, record in expected_records.items():
        _validate_checkpoint(path / filename(key), record, label)


def _percentile_linear(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _statistics(values: list[float]) -> dict[str, int | float]:
    if not values:
        raise AuditError("cannot aggregate an empty latency series")
    return {
        "count": len(values),
        "mean": round(statistics.fmean(values), 6),
        "median": round(statistics.median(values), 6),
        "p95": round(_percentile_linear(values, 0.95), 6),
    }


def _verify_source_files(source_directory: Path | None, images: list[Mapping[str, Any]]) -> dict[str, Any]:
    if source_directory is None:
        raise AuditError("source directory is required for promotion audit")
    root = source_directory.resolve()
    for image in images:
        relative = image["file"]
        if not isinstance(relative, str) or not relative:
            raise AuditError(f"manifest image file is invalid: {image['id']}")
        source = (root / relative).resolve()
        if source != root and root not in source.parents:
            raise AuditError(f"manifest image file escapes source directory: {image['id']}")
        if _file_hash(source) != image["sha256"]:
            raise AuditError(f"source file hash does not match manifest: {image['id']}")
    return {"status": "verified", "verified": len(images)}


def _verify_current_code(code_root: Path, manifest: Mapping[str, Any]) -> dict[str, int | str]:
    root = code_root.resolve()
    code = _mapping(manifest.get("code"), "manifest code")
    raw_file_map = _list(code.get("fileMap"), "manifest code fileMap")
    expected_files: dict[str, str] = {}
    for index, raw_entry in enumerate(raw_file_map):
        entry = _mapping(raw_entry, f"manifest code fileMap entry {index}")
        relative = entry.get("path")
        if not isinstance(relative, str) or not relative:
            raise AuditError(f"manifest code fileMap entry {index} has invalid path")
        if relative in expected_files:
            raise AuditError(f"manifest code fileMap contains duplicate path: {relative}")
        expected_files[relative] = _sha256(entry.get("sha256"), f"manifest code file hash {relative}")

    app_root = root / "app" / "services" / "medication_ocr_v3"
    current_paths = sorted(app_root.rglob("*.py"))
    current_names = [str(path.relative_to(root)).replace("\\", "/") for path in current_paths]
    if set(current_names) != set(expected_files):
        missing = set(expected_files) - set(current_names)
        extra = set(current_names) - set(expected_files)
        raise AuditError(
            f"manifest code fileMap does not match current app: missing={','.join(sorted(missing)) or 'none'}; "
            f"extra={','.join(sorted(extra)) or 'none'}"
        )
    code_digest = hashlib.sha256()
    for name, path in zip(current_names, current_paths, strict=True):
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != expected_files[name]:
            raise AuditError(f"current code file hash does not match manifest: {name}")
        code_digest.update(name.encode() + content)
    if code.get("codeHash") != code_digest.hexdigest():
        raise AuditError("current aggregate codeHash does not match manifest")
    harness = root / "scripts" / "benchmark_ocr_v34.py"
    if code.get("harnessSha256") != _file_hash(harness):
        raise AuditError("current benchmark harness hash does not match manifest")
    runtime = _mapping(manifest.get("runtime"), "manifest runtime")
    if runtime.get("configPySha256") != _file_hash(root / "app" / "core" / "config.py"):
        raise AuditError("current config.py hash does not match manifest runtime")
    return {"status": "verified", "files": len(current_paths)}


def audit_artifacts(  # noqa: C901 - Keep this ordered, fail-closed evidence-validation sequence together.
    *,
    directory: Path,
    truth_path: Path,
    statuses_path: Path,
    evaluator_path: Path,
    scores_path: Path | None = None,
    timings_path: Path | None = None,
    without_timings: bool = False,
    code_root: Path | None = None,
    source_directory: Path | None = None,
) -> dict[str, Any]:
    directory = directory.resolve()
    code_root = (code_root or Path(__file__).resolve().parents[1]).resolve()
    source_directory = source_directory or code_root.parent.parent / "docs" / "문서 예시" / "복약안내"
    manifest_path = directory / "manifest.json"
    results_path = directory / "results.json"
    scores_path = scores_path or directory / "scores.json"
    if without_timings and timings_path is not None:
        raise AuditError("timings_path and without_timings are mutually exclusive")
    if not without_timings:
        timings_path = timings_path or directory / "local-timings.json"
    inflight = sorted(path.relative_to(directory) for path in directory.rglob("*.inflight") if path.is_file())
    if inflight:
        raise AuditError(f"residual inflight checkpoints found: {','.join(map(str, inflight))}")

    manifest = _mapping(_load_json(manifest_path), "manifest")
    identity = digest(manifest)
    config = _mapping(manifest.get("config"), "manifest config")
    if manifest.get("configHash") != digest(config):
        raise AuditError("manifest configHash does not match config")
    if config.get("llm") is not False:
        raise AuditError("manifest llm must be false")
    ocr_repeats = config.get("ocrRepeats")
    if isinstance(ocr_repeats, bool) or ocr_repeats != 1:
        raise AuditError("manifest ocrRepeats must be exactly 1")
    local_repeats = config.get("localRepeats")
    if isinstance(local_repeats, bool) or local_repeats != EXPECTED_LOCAL_REPEATS:
        raise AuditError(f"manifest localRepeats must be exactly {EXPECTED_LOCAL_REPEATS}")
    versions = _unique_strings(manifest.get("versions"), "manifest versions")
    variants = _unique_strings(config.get("variants"), "manifest variants")
    for value in (*versions, *variants):
        _safe_component(value, "manifest version/variant")

    raw_images = _list(manifest.get("images"), "manifest images")
    images: list[Mapping[str, Any]] = []
    image_by_id: dict[str, Mapping[str, Any]] = {}
    for index, raw_image in enumerate(raw_images):
        image = _mapping(raw_image, f"manifest image {index}")
        sample_id = image.get("id")
        if not isinstance(sample_id, str) or not sample_id:
            raise AuditError(f"manifest image {index} has invalid id")
        _safe_component(sample_id, "manifest image id")
        if sample_id in image_by_id:
            raise AuditError("manifest images contains duplicate ids")
        _sha256(image.get("sha256"), f"manifest image {sample_id} sha256")
        if not isinstance(image.get("file"), str) or not image["file"]:
            raise AuditError(f"manifest image {sample_id} has invalid file")
        images.append(image)
        image_by_id[sample_id] = image
    if not images:
        raise AuditError("manifest images must not be empty")
    truth_sha256 = _file_hash(truth_path)
    if manifest.get("truthSha256") != truth_sha256:
        raise AuditError("manifest truthSha256 does not match truth file")
    source_check = _verify_source_files(source_directory, images)
    code_check = _verify_current_code(code_root, manifest)

    results = _mapping(_load_json(results_path), "results")
    if results.get("identity") != identity:
        raise AuditError("results identity does not match manifest digest")
    expected_result_grid = {
        (sample_id, version, variant) for sample_id in image_by_id for version in versions for variant in variants
    }
    result_records = _validate_grid(
        _list(results.get("runs"), "results runs"),
        expected=expected_result_grid,
        fields=("id", "version", "variant"),
        label="result",
    )
    wall_by_version = {version: [] for version in versions}
    transform_by_image_variant: dict[tuple[str, str], Mapping[str, Any]] = {}
    for (sample_id, version, variant), record in result_records.items():
        image_hash = str(image_by_id[sample_id]["sha256"])
        label = f"result {sample_id}/{version}/{variant}"
        if record.get("identity") != identity or record.get("sha256") != image_hash:
            raise AuditError(f"{label} identity/source metadata does not match manifest")
        provider_calls = record.get("providerCallCount")
        if isinstance(provider_calls, bool) or not isinstance(provider_calls, int) or not 0 <= provider_calls <= 1:
            raise AuditError(f"{label} providerCallCount must be an integer between 0 and 1")
        transform = _validate_transform(record, image_hash=image_hash, variant=variant, label=label)
        transform_key = (sample_id, variant)
        prior_transform = transform_by_image_variant.setdefault(transform_key, transform)
        if transform != prior_transform:
            raise AuditError(f"{label} transform metadata differs across versions")
        wall_by_version[version].append(_finite_nonnegative(record.get("wallMs"), f"{label} wallMs"))
    _validate_checkpoint_directory(
        directory / "runs",
        result_records,
        lambda key: f"{key[0]}-{key[1]}-{key[2]}.json",
        "result",
    )

    timing_stats: dict[str, dict[str, int | float]] | None = None
    timing_count: int | None = None
    timings_sha256: str | None = None
    if timings_path is not None:
        timings = _mapping(_load_json(timings_path), "timings")
        timings_sha256 = _file_hash(timings_path)
        if timings.get("identity") != identity:
            raise AuditError("timings identity does not match manifest digest")
        expected_timing_grid = {(sample_id, variant) for sample_id in image_by_id for variant in variants}
        timing_records = _validate_grid(
            _list(timings.get("runs"), "timings runs"),
            expected=expected_timing_grid,
            fields=("id", "variant"),
            label="timing",
        )
        medians_by_version = {version: [] for version in versions}
        for (sample_id, variant), record in timing_records.items():
            image_hash = str(image_by_id[sample_id]["sha256"])
            label = f"timing {sample_id}/{variant}"
            if (
                record.get("version") != "timings"
                or record.get("identity") != identity
                or record.get("sha256") != image_hash
            ):
                raise AuditError(f"{label} identity/source metadata does not match manifest")
            transform = _validate_transform(record, image_hash=image_hash, variant=variant, label=label)
            if transform != transform_by_image_variant[(sample_id, variant)]:
                raise AuditError(f"{label} transform metadata does not match result runs")
            times = _mapping(record.get("timesMs"), f"{label} timesMs")
            if set(times) != set(versions):
                raise AuditError(f"{label} timing version keys must exactly match manifest versions")
            for version in versions:
                values = _list(times[version], f"{label} timing values for {version}")
                if len(values) != EXPECTED_LOCAL_REPEATS:
                    raise AuditError(
                        f"{label} timing values for {version} must contain exactly {EXPECTED_LOCAL_REPEATS} repeats"
                    )
                normalized = [_finite_nonnegative(value, f"{label} timing values for {version}") for value in values]
                medians_by_version[version].append(float(statistics.median(normalized)))
        _validate_checkpoint_directory(
            directory / "timings",
            timing_records,
            lambda key: f"{key[0]}-{key[1]}.json",
            "timing",
        )
        timing_stats = {version: _statistics(values) for version, values in medians_by_version.items()}
        timing_count = len(timing_records)

    results_sha256 = _file_hash(results_path)
    statuses_sha256 = _file_hash(statuses_path)
    evaluator_sha256 = _file_hash(evaluator_path)
    scores = _mapping(_load_json(scores_path), "scores")
    if scores.get("identity") != identity:
        raise AuditError("scores report identity does not match manifest digest")
    provenance = _mapping(scores.get("provenance"), "scores provenance")
    expected_provenance: dict[str, str | None] = {
        "resultsSha256": results_sha256,
        "truthSha256": truth_sha256,
        "statusesSha256": statuses_sha256,
        "evaluatorSha256": evaluator_sha256,
        "timingsSha256": timings_sha256,
    }
    for key, expected_value in expected_provenance.items():
        if provenance.get(key) != expected_value:
            raise AuditError(f"scores provenance {key} does not match audited file")

    return {
        "schemaVersion": SCHEMA_VERSION,
        "valid": True,
        "identity": identity,
        "mode": "results-and-scores-only" if without_timings else "promotion",
        "grid": {
            "images": len(images),
            "versions": len(versions),
            "variants": len(variants),
            "resultRuns": len(result_records),
            "timingRuns": timing_count,
            "localRepeats": EXPECTED_LOCAL_REPEATS,
        },
        "checks": {
            "manifest": "verified",
            "truth": "verified",
            "sourceFiles": source_check,
            "currentCode": code_check,
            "results": "grid and checkpoints verified",
            "timings": "explicitly omitted" if without_timings else "grid, repeats, and checkpoints verified",
            "scores": "identity and provenance verified",
        },
        "latencyMs": {
            "aggregation": "mean/median/p95(linear) across per-image-variant observations",
            "localThreeRepeatMedianByVersion": timing_stats,
            "fullWallByVersion": {version: _statistics(values) for version, values in wall_by_version.items()},
        },
        "provenance": {
            "manifestSha256": _file_hash(manifest_path),
            "resultsSha256": results_sha256,
            "truthSha256": truth_sha256,
            "statusesSha256": statuses_sha256,
            "scoresSha256": _file_hash(scores_path),
            "evaluatorSha256": evaluator_sha256,
            "timingsSha256": timings_sha256,
        },
    }


def _atomic_write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as output:
            temporary_path = Path(output.name)
            json.dump(value, output, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary_path.replace(path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--statuses", type=Path, required=True)
    parser.add_argument("--evaluator", type=Path, default=Path(__file__).with_name("evaluate_ocr_v34.py"))
    parser.add_argument("--scores", type=Path)
    timing_group = parser.add_mutually_exclusive_group()
    timing_group.add_argument("--timings", type=Path)
    timing_group.add_argument("--without-timings", action="store_true")
    parser.add_argument("--source-directory", type=Path)
    parser.add_argument("--code-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = audit_artifacts(
        directory=args.directory,
        truth_path=args.truth,
        statuses_path=args.statuses,
        evaluator_path=args.evaluator,
        scores_path=args.scores,
        timings_path=args.timings,
        without_timings=args.without_timings,
        code_root=args.code_root,
        source_directory=args.source_directory,
    )
    _atomic_write_json(args.output, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

