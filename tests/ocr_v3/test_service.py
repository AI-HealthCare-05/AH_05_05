from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.exceptions import (
    OcrProviderError as JobOcrProviderError,
)
from app.core.exceptions import (
    OcrProviderTimeoutError,
    OcrProviderTransientError,
)
from app.services.medication_ocr_v3.domain.image import QualityState
from app.services.medication_ocr_v3.domain.models import OcrErrorCode, OcrResult
from app.services.medication_ocr_v3.pipeline.analyze import (
    AnalyzePipelineFailure,
    AnalyzePipelineResult,
    StageResult,
)
from app.services.medication_ocr_v3.pipeline.grounding import (
    GroundedField,
    GroundedMedication,
    GroundedResult,
)
from app.services.medication_ocr_v3.pipeline.medication_rows import (
    MedicationField,
    MedicationFields,
    MedicationRow,
    MedicationRowsResult,
)
from app.services.medication_ocr_v3.pipeline.ocr_layout import AxisAlignedBBox, OcrLayoutResult
from app.services.medication_ocr_v3.service import MedicationOcrV3Service
from app.services.ocr_image_input import ValidatedImage


def _validated_image() -> ValidatedImage:
    return ValidatedImage(
        filename="guide.png",
        media_type="image/png",
        provider_format="png",
        content=b"project-owned-image-bytes",
    )


def _processed(*, quality_state: QualityState = QualityState.PROCESSED) -> object:
    return SimpleNamespace(
        quality_state=quality_state,
        reasons=("image_too_blurry",) if quality_state is QualityState.RECAPTURE_REQUIRED else (),
        template_image=SimpleNamespace(jpeg_bytes=b"processed-jpeg"),
    )


def _medication_field(
    value: str | int,
    confidence: float,
    block_id: str,
) -> MedicationField:
    return MedicationField(
        value=value,
        source_text=str(value),
        block_ids=(block_id,),
        bbox=AxisAlignedBBox(0, 0, 10, 10),
        confidence=confidence,
        issues=(),
    )


def _grounded_field(
    value: str | int,
    confidence: float,
    block_id: str,
) -> GroundedField:
    return GroundedField(
        value=value,
        source_text=str(value),
        block_ids=(block_id,),
        rejected_block_ids=(),
        bbox=AxisAlignedBBox(0, 0, 10, 10),
        confidence=confidence,
        issues=(),
    )


def _successful_pipeline_result(*, llm_stage: StageResult | None = None) -> AnalyzePipelineResult:
    fields = MedicationFields(
        name=_medication_field("테스트정", 0.91, "name"),
        dose_quantity=_medication_field("1정", 0.89, "dose"),
        times_per_day=_medication_field(2, 0.88, "times"),
        days=_medication_field(5, 0.87, "days"),
    )
    row = MedicationRow(
        name="테스트정",
        dose_quantity="1정",
        times_per_day=2,
        days=5,
        confidence=0.87,
        bbox=AxisAlignedBBox(0, 0, 100, 20),
        fields=fields,
        issues=(),
    )
    grounded = GroundedResult(
        dispensed_date=_grounded_field("2026-09-01", 0.95, "date"),
        medications=(
            GroundedMedication(
                row_id="row-0001",
                name=_grounded_field("테스트정", 0.91, "name"),
                strength=_grounded_field("10mg", 0.92, "strength"),
                dose_quantity=_grounded_field("1정", 0.89, "dose"),
                times_per_day=_grounded_field(2, 0.88, "times"),
                days=_grounded_field(5, 0.87, "days"),
            ),
        ),
        issues=(),
    )
    return AnalyzePipelineResult(
        ocr_result=OcrResult(()),
        layout=OcrLayoutResult((), (), ()),
        medication_rows=MedicationRowsResult(None, (row,), ()),
        grounded=grounded,
        project_review={
            "fields": {"dispensedDate": {"value": "2026-09-01", "confidence": "high"}},
            "medications": [
                {
                    "tempId": "med-1",
                    "name": "테스트정",
                    "strength": "10mg",
                    "doseQuantity": "1정",
                    "timesPerDay": 2,
                    "days": 5,
                    "confidence": "medium",
                }
            ],
            "lowConfidenceCount": 0,
        },
        stages=(
            StageResult("ocr", "succeeded", 20, 1),
            StageResult("candidate", "succeeded", 2, 0),
            llm_stage or StageResult("llm", "skipped", 0, 0),
            StageResult("validate", "succeeded", 1, 0),
        ),
    )


@pytest.mark.asyncio
async def test_analyze_preprocesses_off_loop_and_returns_project_projection(monkeypatch) -> None:
    from app.services.medication_ocr_v3 import service as service_module

    event_loop_thread = threading.get_ident()
    preprocess_thread: int | None = None
    provider = object()

    def fake_preprocess(content: bytes, media_type: str) -> object:
        nonlocal preprocess_thread
        preprocess_thread = threading.get_ident()
        assert content == b"project-owned-image-bytes"
        assert media_type == "image/png"
        return processed_result

    def fake_build_provider_image(processed: object, rectangles: object) -> bytes:
        assert processed is processed_result
        assert rectangles == ()
        return b"privacy-safe-jpeg"

    async def fake_analyze_pipeline(
        actual_provider: object,
        processed_jpeg: bytes,
        **_kwargs: object,
    ) -> AnalyzePipelineResult:
        assert actual_provider is provider
        assert processed_jpeg == b"privacy-safe-jpeg"
        return _successful_pipeline_result()

    processed_result = _processed()
    monkeypatch.setattr(service_module, "preprocess_image", fake_preprocess)
    monkeypatch.setattr(
        service_module,
        "build_privacy_safe_provider_image",
        fake_build_provider_image,
    )
    monkeypatch.setattr(
        service_module,
        "analyze_processed_image",
        fake_analyze_pipeline,
    )

    analysis = await MedicationOcrV3Service(provider=provider).analyze(_validated_image())

    assert preprocess_thread is not None and preprocess_thread != event_loop_thread
    assert analysis.project_review["medications"][0]["strength"] == "10mg"
    assert [stage["name"] for stage in analysis.stages] == [
        "preprocess",
        "ocr",
        "candidate",
        "llm",
        "validate",
    ]
    assert analysis.stages[0] == {
        "name": "preprocess",
        "status": "succeeded",
        "elapsedMs": analysis.stages[0]["elapsedMs"],
        "callCount": 0,
    }
    assert analysis.confidence_values == [0.91]
    assert analysis.ocr_model == "clova-general-v2"
    assert analysis.structuring_model == "deterministic-v3"
    assert analysis.prompt_version == "medication_grounding_v3"
    assert analysis.schema_version == "medication-guide-review/v3"
    assert analysis.requires_recapture is False
    assert analysis.processed_image_bytes == b"processed-jpeg"


@pytest.mark.asyncio
async def test_recapture_returns_typed_five_stage_result_without_provider_calls(monkeypatch) -> None:
    from app.services.medication_ocr_v3 import service as service_module

    monkeypatch.setattr(
        service_module,
        "preprocess_image",
        Mock(return_value=_processed(quality_state=QualityState.RECAPTURE_REQUIRED)),
    )
    build_provider_image = Mock(side_effect=AssertionError("provider image must not be built"))
    analyze_pipeline = AsyncMock(side_effect=AssertionError("providers must not run"))
    monkeypatch.setattr(service_module, "build_privacy_safe_provider_image", build_provider_image)
    monkeypatch.setattr(service_module, "analyze_processed_image", analyze_pipeline)

    analysis = await MedicationOcrV3Service(provider=object()).analyze(_validated_image())

    assert analysis.requires_recapture is True
    assert analysis.recapture_reasons == ("image_too_blurry",)
    assert analysis.project_review == {"fields": {}, "medications": [], "lowConfidenceCount": 0}
    assert analysis.confidence_values == []
    assert [stage["name"] for stage in analysis.stages] == [
        "preprocess",
        "ocr",
        "candidate",
        "llm",
        "validate",
    ]
    assert [stage["status"] for stage in analysis.stages] == [
        "succeeded",
        "skipped",
        "skipped",
        "skipped",
        "skipped",
    ]
    assert analysis.stages[0]["code"] == "RECAPTURE_REQUIRED"
    build_provider_image.assert_not_called()
    analyze_pipeline.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "expected_error"),
    [
        (OcrErrorCode.OCR_TIMEOUT, OcrProviderTimeoutError),
        (OcrErrorCode.OCR_CONNECTION_FAILED, OcrProviderTransientError),
        (OcrErrorCode.OCR_UPSTREAM_FAILED, OcrProviderTransientError),
        (OcrErrorCode.OCR_AUTH_REJECTED, JobOcrProviderError),
        (OcrErrorCode.OCR_PROTOCOL_INVALID, JobOcrProviderError),
    ],
)
async def test_provider_failures_preserve_five_stages_on_existing_job_error_classes(
    monkeypatch,
    code: OcrErrorCode,
    expected_error: type[Exception],
) -> None:
    from app.services.medication_ocr_v3 import service as service_module

    monkeypatch.setattr(service_module, "_elapsed_ms", Mock(return_value=4))
    monkeypatch.setattr(service_module, "preprocess_image", Mock(return_value=_processed()))
    monkeypatch.setattr(
        service_module,
        "build_privacy_safe_provider_image",
        Mock(return_value=b"privacy-safe-jpeg"),
    )
    monkeypatch.setattr(
        service_module,
        "analyze_processed_image",
        AsyncMock(
            return_value=AnalyzePipelineFailure(
                code=code,
                status_code=504 if code is OcrErrorCode.OCR_TIMEOUT else 502,
                stages=(
                    StageResult("ocr", "failed", 10, 1, code.value),
                    StageResult("candidate", "skipped", 0, 0),
                    StageResult("llm", "skipped", 0, 0),
                    StageResult("validate", "skipped", 0, 0),
                ),
            )
        ),
    )

    with pytest.raises(expected_error) as raised:
        await MedicationOcrV3Service(provider=object()).analyze(_validated_image())

    assert type(raised.value) is expected_error
    assert raised.value.stages == [
        {"name": "preprocess", "status": "succeeded", "elapsedMs": 4, "callCount": 0},
        {
            "name": "ocr",
            "status": "failed",
            "elapsedMs": 10,
            "callCount": 1,
            "code": code.value,
        },
        {"name": "candidate", "status": "skipped", "elapsedMs": 0, "callCount": 0},
        {"name": "llm", "status": "skipped", "elapsedMs": 0, "callCount": 0},
        {"name": "validate", "status": "skipped", "elapsedMs": 0, "callCount": 0},
    ]


@pytest.mark.asyncio
async def test_llm_failure_remains_a_successful_deterministic_fallback(monkeypatch) -> None:
    from app.services.medication_ocr_v3 import service as service_module

    monkeypatch.setattr(service_module, "preprocess_image", Mock(return_value=_processed()))
    monkeypatch.setattr(
        service_module,
        "build_privacy_safe_provider_image",
        Mock(return_value=b"privacy-safe-jpeg"),
    )
    pipeline_result = _successful_pipeline_result(llm_stage=StageResult("llm", "failed", 30, 1, "LLM_TIMEOUT"))
    monkeypatch.setattr(
        service_module,
        "analyze_processed_image",
        AsyncMock(return_value=pipeline_result),
    )
    structurer = SimpleNamespace(model_version="gpt-test")

    analysis = await MedicationOcrV3Service(
        provider=object(),
        structurer=structurer,
    ).analyze(_validated_image())

    assert analysis.project_review == pipeline_result.project_review
    assert analysis.stages[3] == {
        "name": "llm",
        "status": "failed",
        "elapsedMs": 30,
        "callCount": 1,
        "code": "LLM_TIMEOUT",
    }
    assert analysis.structuring_model == "gpt-test"
