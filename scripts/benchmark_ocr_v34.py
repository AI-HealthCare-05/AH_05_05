"""Resumable, privacy-minimal v3.4 preprocessing benchmark.

The harness persists only frozen identities, timing/geometry metadata, and the
five medication fields used by the scorer.  It never writes source images,
processed images, or raw provider OCR payloads.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import mimetypes
import os
import platform
import time
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import cv2
import numpy as np
import PIL
from PIL import Image, ImageOps

from app.core.config import Config
from app.services.medication_ocr_v3.providers.clova_general import ClovaGeneralOcrProvider
from app.services.medication_ocr_v3.service import MedicationOcrV3Service
from app.services.ocr_image_input import ValidatedImage

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = ROOT.parent
SOURCE = ROOT.parent.parent / "docs/문서 예시/복약안내"
FROZEN_MANIFEST = EXPERIMENT_ROOT / "ocr-16-three-versions-20260907/manifest.json"
TRUTH = EXPERIMENT_ROOT / "ocr-16-three-versions-20260907/ground-truth.json"
DEFAULT_OUTPUT = EXPERIMENT_ROOT / "ocr-v34-adaptive-20260907"
DEFAULT_VERSIONS = ("v3.1.3", "v3.2.7", "v3.3.1", "v3.4.1")
DEFAULT_VARIANTS = ("identity", "rotate", "perspective", "shadow", "blur", "downscale")
LOCAL_REPEATS = 3
SCHEMA_VERSION = "ocr-v34-adaptive/1"
_MEDICATION_FIELDS = ("name", "strength", "doseQuantity", "timesPerDay", "days")
_STAGE_FIELDS = ("name", "status", "elapsedMs", "callCount")


@dataclass(frozen=True, slots=True)
class VariantImage:
    content: bytes
    source_sha256: str
    transformed_sha256: str
    parameters: dict[str, float | int | str]

    def as_manifest(self) -> dict[str, object]:
        return {
            "sourceSha256": self.source_sha256,
            "transformedSha256": self.transformed_sha256,
            "parameters": self.parameters,
        }


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temp.open("w", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.flush()
        os.fsync(output.fileno())
    temp.replace(path)


def write_checkpoint(path: Path, result: dict[str, object]) -> None:
    _atomic_json(path, {"result": result, "checksum": digest(result)})


def load_checkpoint(
    path: Path,
    *,
    identity: dict[str, object],
    entry: dict[str, object],
    version: str,
    variant: str,
    transform: dict[str, object] | None = None,
) -> dict[str, object] | None:
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        result = envelope["result"]
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise ValueError(f"Corrupt checkpoint: {path.name}") from error
    if not isinstance(result, dict) or envelope.get("checksum") != digest(result):
        raise ValueError(f"Corrupt checkpoint: {path.name}")
    expected = {
        "id": entry["id"],
        "sha256": entry["sha256"],
        "version": version,
        "variant": variant,
        "identity": digest(identity),
    }
    if any(result.get(key) != value for key, value in expected.items()):
        raise ValueError(f"Stale checkpoint: {path.name}")
    if transform is not None and result.get("transform") != transform:
        raise ValueError(f"Stale checkpoint: {path.name}")
    return cast(dict[str, object], result)


def _inflight_path(checkpoint: Path) -> Path:
    return checkpoint.with_suffix(".inflight")


def _assert_no_unfinished_attempt(checkpoint: Path) -> None:
    marker = _inflight_path(checkpoint)
    if marker.exists() and not checkpoint.exists():
        raise RuntimeError(f"Unfinished OCR attempt requires manual review: {marker.name}")


def _write_inflight(checkpoint: Path, *, identity: dict[str, object]) -> Path:
    marker = _inflight_path(checkpoint)
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise RuntimeError(f"Unfinished OCR attempt requires manual review: {marker.name}") from error
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump({"identity": digest(identity), "state": "provider-call-started"}, output, ensure_ascii=False)
    return marker


def _remove_inflight(checkpoint: Path) -> None:
    _inflight_path(checkpoint).unlink(missing_ok=True)


def _inside_experiment_root(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(EXPERIMENT_ROOT.resolve())
    except ValueError as error:
        raise ValueError("--output must stay under the 906 experiment directory") from error
    return resolved


def _split_values(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    values = tuple(item.strip() for item in value.split(",") if item.strip())
    if not values:
        raise ValueError("At least one value is required.")
    return values


def validate_versions(versions: tuple[str, ...]) -> tuple[str, ...]:
    if not versions:
        raise ValueError("Version registry is empty")
    if len(set(versions)) != len(versions):
        raise ValueError("Version registry contains duplicates")
    from app.services.medication_ocr_v3.pipeline.preprocess import _preprocess_profile

    for version in versions:
        _preprocess_profile(version)
    return versions


def _code_identity() -> dict[str, object]:
    files = sorted((ROOT / "app/services/medication_ocr_v3").rglob("*.py"))
    file_map = []
    code_digest = hashlib.sha256()
    for path in files:
        name = str(path.relative_to(ROOT)).replace("\\", "/")
        content = path.read_bytes()
        file_map.append({"path": name, "sha256": hashlib.sha256(content).hexdigest()})
        code_digest.update(name.encode() + content)
    code_hash = code_digest.hexdigest()
    return {"fileMap": file_map, "codeHash": code_hash, "harnessSha256": _file_hash(Path(__file__))}


def _frozen_images(ids: tuple[str, ...] | None) -> list[dict[str, object]]:
    frozen = json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8"))
    images = cast(list[dict[str, object]], frozen["images"])
    selected = [dict(item) for item in images if ids is None or item["id"] in ids]
    if not selected or (ids is not None and {item["id"] for item in selected} != set(ids)):
        raise ValueError("--ids must name entries from the frozen 16-image manifest")
    for item in selected:
        item["documentGroup"] = "document-08-11" if item["id"] in {"sample-08", "sample-11"} else item["id"]
        source = SOURCE / cast(str, item["file"])
        if _file_hash(source) != item["sha256"]:
            raise ValueError(f"Source hash changed: {item['id']}")
    return selected


def prepare_experiment(
    output: Path,
    *,
    versions: tuple[str, ...] = DEFAULT_VERSIONS,
    ids: tuple[str, ...] | None = None,
    variants: tuple[str, ...] = ("identity",),
) -> dict[str, object]:
    output = _inside_experiment_root(output)
    versions = validate_versions(versions)
    if not TRUTH.is_file():
        raise ValueError("Frozen ground-truth checksum reference is missing")
    if any(variant not in DEFAULT_VARIANTS for variant in variants):
        raise ValueError("Unsupported image variant")
    config = {"llm": False, "ocrRepeats": 1, "localRepeats": LOCAL_REPEATS, "variants": list(variants)}
    identity: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "images": _frozen_images(ids),
        "versions": list(versions),
        "truthSha256": _file_hash(TRUTH),
        "config": config,
        "configHash": digest(config),
        "code": _code_identity(),
        "runtime": {
            "python": platform.python_version(),
            "opencv": cv2.__version__,
            "numpy": np.__version__,
            "pillow": PIL.__version__,
            "configPySha256": _file_hash(ROOT / "app/core/config.py"),
        },
    }
    manifest = output / "manifest.json"
    if manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")) != identity:
        raise ValueError("Stale benchmark manifest")
    _atomic_json(manifest, identity)
    return identity


def _encode_jpeg(rgb: np.ndarray) -> bytes:
    output = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(output, format="JPEG", quality=95, subsampling=0, optimize=True)
    return output.getvalue()


def make_variant(source: bytes, variant: str) -> VariantImage:
    if variant not in DEFAULT_VARIANTS:
        raise ValueError(f"Unsupported image variant: {variant}")
    source_hash = hashlib.sha256(source).hexdigest()
    if variant == "identity":
        return VariantImage(source, source_hash, source_hash, {"name": "identity"})
    with Image.open(io.BytesIO(source)) as decoded:
        rgb = np.asarray(ImageOps.exif_transpose(decoded).convert("RGB"), dtype=np.uint8).copy()
    height, width = rgb.shape[:2]
    if variant == "rotate":
        angle = 4.0
        radians = np.deg2rad(angle)
        target_w = int(np.ceil(width * abs(np.cos(radians)) + height * abs(np.sin(radians))))
        target_h = int(np.ceil(height * abs(np.cos(radians)) + width * abs(np.sin(radians))))
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
        matrix[:, 2] += ((target_w - width) / 2, (target_h - height) / 2)
        transformed = cv2.warpAffine(rgb, matrix, (target_w, target_h), borderValue=(255, 255, 255))
        parameters: dict[str, float | int | str] = {"name": variant, "degrees": angle, "expanded": 1}
    elif variant == "perspective":
        inset_x, inset_y = width * 0.03, height * 0.03
        source_corners = np.float32(((0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)))
        target_corners = np.float32(
            ((inset_x, inset_y), (width - 1 - inset_x, 0), (width - 1, height - 1 - inset_y), (0, height - 1))
        )
        transformed = cv2.warpPerspective(
            rgb,
            cv2.getPerspectiveTransform(source_corners, target_corners),
            (width, height),
            borderValue=(255, 255, 255),
        )
        parameters = {"name": variant, "cornerFraction": 0.03}
    elif variant == "shadow":
        multiplier = np.linspace(0.65, 1.0, width, dtype=np.float32)[None, :, None]
        transformed = np.clip(rgb.astype(np.float32) * multiplier, 0, 255).astype(np.uint8)
        parameters = {"name": variant, "leftMultiplier": 0.65, "rightMultiplier": 1.0}
    elif variant == "blur":
        transformed = cv2.GaussianBlur(rgb, (0, 0), 0.65)
        parameters = {"name": variant, "sigma": 0.65}
    else:
        target = (max(1, round(width * 0.7)), max(1, round(height * 0.7)))
        transformed = cv2.resize(rgb, target, interpolation=cv2.INTER_AREA)
        parameters = {"name": variant, "scale": 0.7}
    content = _encode_jpeg(transformed)
    return VariantImage(content, source_hash, hashlib.sha256(content).hexdigest(), parameters)


def _safe_value(value: object) -> object:
    return value if isinstance(value, (str, int, float, bool)) or value is None else None


def _stage_value(stage: object, field: str) -> object:
    if isinstance(stage, dict):
        return stage.get(field)
    return getattr(stage, field, None)


def safe_preprocess_metadata(result: object) -> dict[str, object]:
    metrics = getattr(result, "metrics", None)
    raw_to_template = getattr(getattr(result, "raw_to_template", None), "matrix", None)
    return {
        "quality": getattr(getattr(result, "quality_state", None), "value", None),
        "mode": getattr(getattr(result, "preprocessing_mode", None), "value", None),
        "reasons": list(getattr(result, "reasons", ())),
        "operations": list(getattr(result, "operations", ())),
        "dimensions": {
            "width": getattr(getattr(result, "template_image", None), "width", None),
            "height": getattr(getattr(result, "template_image", None), "height", None),
        },
        "metrics": metrics.as_dict() if metrics is not None else {},
        "rawToTemplateMatrix": list(raw_to_template) if isinstance(raw_to_template, tuple) else None,
    }


def safe_analysis_result(analysis: object, *, preprocess_metadata: dict[str, object]) -> dict[str, object]:
    review = getattr(analysis, "project_review", {})
    medications = review.get("medications", []) if isinstance(review, dict) else []
    safe_rows = [
        {field: _safe_value(row.get(field)) for field in _MEDICATION_FIELDS}
        for row in medications
        if isinstance(row, dict)
    ]
    return {
        "review": {"medications": safe_rows},
        "recapture": bool(getattr(analysis, "requires_recapture", False)),
        "recaptureReasons": list(getattr(analysis, "recapture_reasons", ()) or ()),
        "stages": [
            {field: _safe_value(_stage_value(stage, field)) for field in _STAGE_FIELDS}
            for stage in getattr(analysis, "stages", ())
        ],
        "preprocess": preprocess_metadata,
    }


class _CountedProvider:
    def __init__(self, provider: ClovaGeneralOcrProvider, checkpoint: Path, identity: dict[str, object]) -> None:
        self._provider = provider
        self._checkpoint = checkpoint
        self._identity = identity
        self.calls = 0

    async def recognize(self, processed_jpeg: bytes):  # type: ignore[no-untyped-def]
        if self.calls >= 1:
            raise RuntimeError("Benchmark forbids more than one OCR call per image/version/variant")
        self.calls += 1
        _write_inflight(self._checkpoint, identity=self._identity)
        return await self._provider.recognize(processed_jpeg)


async def _native_analysis(
    image: ValidatedImage,
    *,
    version: str,
    checkpoint: Path,
    identity: dict[str, object],
) -> tuple[object, dict[str, object], int]:
    import app.services.medication_ocr_v3.service as service_module

    captured: dict[str, object] = {}
    original = service_module.preprocess_image

    def capture(*args: object, **kwargs: object) -> object:
        result = original(*args, **kwargs)
        captured.update(safe_preprocess_metadata(result))
        return result

    config = Config()
    if not config.CLOVA_GENERAL_OCR_INVOKE_URL or not config.CLOVA_GENERAL_OCR_SECRET:
        raise RuntimeError("CLOVA General OCR configuration is required for run mode")
    service_module.preprocess_image = capture
    try:
        async with ClovaGeneralOcrProvider(
            endpoint=config.CLOVA_GENERAL_OCR_INVOKE_URL,
            secret=config.CLOVA_GENERAL_OCR_SECRET.get_secret_value(),
        ) as provider:
            counted = _CountedProvider(provider, checkpoint, identity)
            analysis = await MedicationOcrV3Service(
                provider=counted, structurer=None, preprocess_version=version
            ).analyze(image)
            return analysis, captured, counted.calls
    finally:
        service_module.preprocess_image = original


def _checkpoint_path(output: Path, entry: dict[str, object], version: str, variant: str) -> Path:
    return output / "runs" / f"{entry['id']}-{version}-{variant}.json"


def _variant_mime(entry: dict[str, object], variant: str) -> str:
    if variant == "identity":
        return mimetypes.guess_type(cast(str, entry["file"]))[0] or "image/jpeg"
    return "image/jpeg"


def _variant_image(entry: dict[str, object], variant: str) -> tuple[VariantImage, ValidatedImage]:
    source = (SOURCE / cast(str, entry["file"])).read_bytes()
    if hashlib.sha256(source).hexdigest() != entry["sha256"]:
        raise ValueError(f"Source hash changed: {entry['id']}")
    mime_type = _variant_mime(entry, variant)
    transformed = make_variant(source, variant)
    is_png = mime_type == "image/png"
    image = ValidatedImage(
        filename="benchmark.png" if is_png else "benchmark.jpg",
        media_type=mime_type,
        provider_format="png" if is_png else "jpg",
        content=transformed.content,
    )
    return transformed, image


async def run(identity: dict[str, object], output: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    variants = cast(list[str], cast(dict[str, object], identity["config"])["variants"])
    for index, entry_obj in enumerate(cast(list[dict[str, object]], identity["images"])):
        entry = dict(entry_obj)
        for variant in variants:
            transformed, image = _variant_image(entry, variant)
            versions = cast(list[str], identity["versions"])
            ordered = versions[index % len(versions) :] + versions[: index % len(versions)]
            for version in ordered:
                checkpoint = _checkpoint_path(output, entry, version, variant)
                existing = load_checkpoint(
                    checkpoint,
                    identity=identity,
                    entry=entry,
                    version=version,
                    variant=variant,
                    transform=transformed.as_manifest(),
                )
                if existing is not None:
                    results.append(existing)
                    continue
                _assert_no_unfinished_attempt(checkpoint)
                started = time.perf_counter()
                analysis, pre, calls = await _native_analysis(
                    image, version=version, checkpoint=checkpoint, identity=identity
                )
                result: dict[str, object] = {
                    "id": entry["id"],
                    "sha256": entry["sha256"],
                    "version": version,
                    "variant": variant,
                    "identity": digest(identity),
                    "wallMs": round((time.perf_counter() - started) * 1000, 3),
                    "providerCallCount": calls,
                    "transform": transformed.as_manifest(),
                    **safe_analysis_result(analysis, preprocess_metadata=pre),
                }
                if calls > 1:
                    raise RuntimeError("Benchmark provider-call count exceeded one")
                write_checkpoint(checkpoint, result)
                _remove_inflight(checkpoint)
                results.append(result)
                print(
                    entry["id"],
                    version,
                    variant,
                    f"rows={len(cast(dict[str, object], result['review'])['medications'])}",
                    f"calls={calls}",
                    f"ms={result['wallMs']}",
                    flush=True,
                )
    _atomic_json(output / "results.json", {"identity": digest(identity), "runs": results})
    return results


def timings(identity: dict[str, object], output: Path) -> list[dict[str, object]]:
    from app.services.medication_ocr_v3.pipeline.preprocess import preprocess_image

    records: list[dict[str, object]] = []
    variants = cast(list[str], cast(dict[str, object], identity["config"])["variants"])
    for index, entry_obj in enumerate(cast(list[dict[str, object]], identity["images"])):
        entry = dict(entry_obj)
        for variant in variants:
            path = output / "timings" / f"{entry['id']}-{variant}.json"
            transformed, _ = _variant_image(entry, variant)
            transform = transformed.as_manifest()
            existing = load_checkpoint(
                path,
                identity=identity,
                entry=entry,
                version="timings",
                variant=variant,
                transform=transform,
            )
            if existing is not None:
                records.append(existing)
                continue
            values = {version: [] for version in cast(list[str], identity["versions"])}
            versions = list(values)
            for repeat in range(LOCAL_REPEATS):
                ordered = versions[(index + repeat) % len(versions) :] + versions[: (index + repeat) % len(versions)]
                for version in ordered:
                    started = time.perf_counter()
                    preprocess_image(
                        transformed.content,
                        _variant_mime(entry, variant),
                        preprocess_version=version,
                    )
                    values[version].append(round((time.perf_counter() - started) * 1000, 3))
            record: dict[str, object] = {
                "id": entry["id"],
                "sha256": entry["sha256"],
                "version": "timings",
                "variant": variant,
                "identity": digest(identity),
                "transform": transform,
                "timesMs": values,
            }
            write_checkpoint(path, record)
            records.append(record)
    _atomic_json(output / "local-timings.json", {"identity": digest(identity), "runs": records})
    return records


def features(identity: dict[str, object], output: Path) -> list[dict[str, object]]:
    from app.services.medication_ocr_v3.pipeline.preprocess import preprocess_image

    records: list[dict[str, object]] = []
    variants = cast(list[str], cast(dict[str, object], identity["config"])["variants"])
    version = (
        "v3.4.3" if "v3.4.3" in cast(list[str], identity["versions"]) else cast(list[str], identity["versions"])[0]
    )
    for entry_obj in cast(list[dict[str, object]], identity["images"]):
        entry = dict(entry_obj)
        for variant in variants:
            path = output / "features" / f"{entry['id']}-{variant}.json"
            transformed, _ = _variant_image(entry, variant)
            transform = transformed.as_manifest()
            existing = load_checkpoint(
                path,
                identity=identity,
                entry=entry,
                version="features",
                variant=variant,
                transform=transform,
            )
            if existing is not None:
                records.append(existing)
                continue
            pre = safe_preprocess_metadata(
                preprocess_image(
                    transformed.content,
                    _variant_mime(entry, variant),
                    preprocess_version=version,
                )
            )
            dimensions = cast(dict[str, object], pre["dimensions"])
            record: dict[str, object] = {
                "id": entry["id"],
                "sha256": entry["sha256"],
                "version": "features",
                "variant": variant,
                "identity": digest(identity),
                "transform": transform,
                "features": {
                    "mode": pre["mode"],
                    "reasons": pre["reasons"],
                    "metrics": pre["metrics"],
                    "imageDimensions": dimensions,
                },
            }
            write_checkpoint(path, record)
            records.append(record)
    _atomic_json(output / "features.json", {"identity": digest(identity), "runs": records})
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "run", "timings", "features"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--versions")
    parser.add_argument("--ids")
    parser.add_argument("--variants", default="identity")
    args = parser.parse_args(argv)
    identity = prepare_experiment(
        args.output,
        versions=_split_values(args.versions, DEFAULT_VERSIONS),
        ids=_split_values(args.ids, ()) if args.ids else None,
        variants=_split_values(args.variants, ("identity",)),
    )
    if args.mode == "run":
        asyncio.run(run(identity, _inside_experiment_root(args.output)))
    elif args.mode == "timings":
        timings(identity, _inside_experiment_root(args.output))
    elif args.mode == "features":
        features(identity, _inside_experiment_root(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
