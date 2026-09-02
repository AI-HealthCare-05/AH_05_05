"""Typed project adapter for the vendored medication OCR v3 pipeline."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Never

from app.core.exceptions import (
    OcrProviderError as JobOcrProviderError,
)
from app.core.exceptions import (
    OcrProviderTimeoutError,
    OcrProviderTransientError,
)
from app.services.medication_ocr_v3.domain.image import QualityState
from app.services.medication_ocr_v3.domain.models import OcrErrorCode
from app.services.medication_ocr_v3.pipeline.analyze import (
    AnalyzePipelineCancellation,
    AnalyzePipelineFailure,
    AnalyzePipelineResult,
    GeneralOcrProvider,
    StageResult,
    analyze_processed_image,
)
from app.services.medication_ocr_v3.pipeline.medication_rows import (
    MedicationField,
    MedicationIssueCode,
)
from app.services.medication_ocr_v3.pipeline.preprocess import preprocess_image
from app.services.medication_ocr_v3.pipeline.privacy_artifact import (
    build_privacy_safe_provider_image,
)
from app.services.medication_ocr_v3.providers.openai_grounded import (
    PROMPT_VERSION,
    GroundedStructurer,
)
from app.services.ocr_image_input import ValidatedImage

OCR_MODEL_VERSION = "clova-general-v2"
DETERMINISTIC_MODEL_VERSION = "deterministic-v3"
PROJECT_SCHEMA_VERSION = "medication-guide-review/v3"

_VALIDATION_ISSUES = frozenset(
    {
        MedicationIssueCode.INVALID_FIELD_VALUE,
        MedicationIssueCode.INVALID_POSITIVE_INTEGER,
        MedicationIssueCode.UNREPRESENTABLE_POSITIVE_INTEGER,
        MedicationIssueCode.INVALID_BLOCK_GEOMETRY,
    }
)


@dataclass(frozen=True, slots=True)
class MedicationOcrV3Analysis:
    """Worker-safe OCR result; recapture is an explicit typed success variant.

    A recapture result has ``requires_recapture=True``, an omission-based empty
    review, and all five operational stages. No OCR or LLM provider is called.
    This lets the job layer persist or route the outcome without recovering
    partial provider state from an exception.
    """

    project_review: dict[str, object]
    stages: list[dict[str, object]]
    confidence_values: list[float]
    ocr_model: str
    structuring_model: str
    prompt_version: str
    schema_version: str
    processed_image_bytes: bytes = b""
    requires_recapture: bool = False
    recapture_reasons: tuple[str, ...] = ()


class MedicationOcrV3CancelledError(RuntimeError):
    """Internal cancellation that preserves completed operational stages."""

    def __init__(self, stages: list[dict[str, object]]) -> None:
        super().__init__("Medication OCR analysis was cancelled.")
        self.stages = stages


class MedicationOcrV3Service:
    """Run CPU preprocessing off-loop and adapt the v3 core to job semantics."""

    def __init__(
        self,
        *,
        provider: GeneralOcrProvider,
        structurer: GroundedStructurer | None = None,
        is_cancelled: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        self._provider = provider
        self._structurer = structurer
        self._is_cancelled = is_cancelled

    async def analyze(self, image: ValidatedImage) -> MedicationOcrV3Analysis:
        preprocess_started = time.perf_counter()
        processed = await asyncio.to_thread(
            preprocess_image,
            image.content,
            image.media_type,
        )
        preprocess_elapsed_ms = _elapsed_ms(preprocess_started)
        if processed.quality_state is QualityState.RECAPTURE_REQUIRED:
            return MedicationOcrV3Analysis(
                project_review=_empty_project_review(),
                stages=_recapture_stages(preprocess_elapsed_ms),
                confidence_values=[],
                ocr_model=OCR_MODEL_VERSION,
                structuring_model=DETERMINISTIC_MODEL_VERSION,
                prompt_version=PROMPT_VERSION,
                schema_version=PROJECT_SCHEMA_VERSION,
                requires_recapture=True,
                recapture_reasons=processed.reasons,
            )

        provider_jpeg = await asyncio.to_thread(
            build_privacy_safe_provider_image,
            processed,
            (),
        )
        pipeline_result = await analyze_processed_image(
            self._provider,
            provider_jpeg,
            structurer=self._structurer,
            is_cancelled=self._is_cancelled,
        )
        preprocess_stage = _stage(
            name="preprocess",
            status="succeeded",
            elapsed_ms=preprocess_elapsed_ms,
            call_count=0,
        )
        if isinstance(pipeline_result, AnalyzePipelineFailure):
            _raise_job_provider_error(
                pipeline_result,
                [
                    preprocess_stage,
                    *(_stage_from_core(stage) for stage in pipeline_result.stages),
                ],
            )
        if isinstance(pipeline_result, AnalyzePipelineCancellation):
            raise MedicationOcrV3CancelledError(
                [preprocess_stage, *(_stage_from_core(stage) for stage in pipeline_result.stages)]
            )

        stages = [
            preprocess_stage,
            *(_stage_from_core(stage) for stage in pipeline_result.stages),
        ]
        return MedicationOcrV3Analysis(
            project_review=_project_review(pipeline_result),
            stages=stages,
            confidence_values=_confidence_values(pipeline_result),
            ocr_model=OCR_MODEL_VERSION,
            structuring_model=_structuring_model(pipeline_result, self._structurer),
            prompt_version=PROMPT_VERSION,
            schema_version=PROJECT_SCHEMA_VERSION,
            processed_image_bytes=processed.template_image.jpeg_bytes,
        )


def _project_review(result: AnalyzePipelineResult) -> dict[str, object]:
    if result.project_review is not None:
        return result.project_review
    payload = result.result_payload().get("projectReview")
    if isinstance(payload, dict):
        return payload
    return _empty_project_review()


def _empty_project_review() -> dict[str, object]:
    return {"fields": {}, "medications": [], "lowConfidenceCount": 0}


def _recapture_stages(preprocess_elapsed_ms: int) -> list[dict[str, object]]:
    return [
        _stage(
            name="preprocess",
            status="succeeded",
            elapsed_ms=preprocess_elapsed_ms,
            call_count=0,
            code="RECAPTURE_REQUIRED",
        ),
        *(
            _stage(name=name, status="skipped", elapsed_ms=0, call_count=0)
            for name in ("ocr", "candidate", "llm", "validate")
        ),
    ]


def _stage_from_core(stage: StageResult) -> dict[str, object]:
    return _stage(
        name=stage.name,
        status=stage.status,
        elapsed_ms=stage.elapsed_ms,
        call_count=stage.call_count,
        code=stage.code,
    )


def _stage(
    *,
    name: str,
    status: str,
    elapsed_ms: int,
    call_count: int,
    code: str | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "name": name,
        "status": status,
        "elapsedMs": elapsed_ms,
        "callCount": call_count,
    }
    if code is not None:
        value["code"] = code
    return value


def _raise_job_provider_error(
    failure: AnalyzePipelineFailure,
    stages: list[dict[str, object]],
) -> Never:
    if failure.code is OcrErrorCode.OCR_TIMEOUT:
        error = OcrProviderTimeoutError()
    elif failure.code in {
        OcrErrorCode.OCR_CONNECTION_FAILED,
        OcrErrorCode.OCR_UPSTREAM_FAILED,
    }:
        error = OcrProviderTransientError()
    else:
        error = JobOcrProviderError()
    error.stages = stages  # type: ignore[attr-defined]
    raise error


def _confidence_values(result: AnalyzePipelineResult) -> list[float]:
    review = _project_review(result)
    values: list[float] = []
    public_medications = review.get("medications")
    if not isinstance(public_medications, list):
        return values
    for medication in public_medications:
        if not isinstance(medication, dict):
            continue
        source_index = _source_index(medication.get("tempId"))
        if source_index is None or not 1 <= source_index <= len(result.medication_rows.medications):
            continue
        row = result.medication_rows.medications[source_index - 1]
        _append_medication_confidence(values, row.fields.name)
    return values


def _source_index(value: object) -> int | None:
    if not isinstance(value, str) or not value.startswith("med-"):
        return None
    try:
        return int(value.removeprefix("med-"))
    except ValueError:
        return None


def _append_medication_confidence(values: list[float], field: MedicationField) -> None:
    if _VALIDATION_ISSUES.intersection(field.issues):
        return
    _append_numeric_confidence(values, field.confidence)


def _append_numeric_confidence(values: list[float], value: object) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return
    numeric = float(value)
    if math.isfinite(numeric) and 0.0 <= numeric <= 1.0:
        values.append(numeric)


def _structuring_model(
    result: AnalyzePipelineResult,
    structurer: GroundedStructurer | None,
) -> str:
    llm_called = any(stage.name == "llm" and stage.call_count > 0 for stage in result.stages)
    if llm_called and structurer is not None:
        model_version = getattr(structurer, "model_version", None)
        if isinstance(model_version, str) and model_version:
            return model_version
    return DETERMINISTIC_MODEL_VERSION


def _elapsed_ms(started: float) -> int:
    return max(0, round((time.perf_counter() - started) * 1000))
