from __future__ import annotations

import threading
from dataclasses import replace
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
        operations=("output_saturate_unsharp_mild",),
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
            StageResult("resolve", "succeeded", 3, 0),
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

    def fake_preprocess(content: bytes, media_type: str, *, preprocess_version: str) -> object:
        nonlocal preprocess_thread
        preprocess_thread = threading.get_ident()
        assert content == b"project-owned-image-bytes"
        assert media_type == "image/png"
        assert preprocess_version == "v3.1.8"
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

    analysis = await MedicationOcrV3Service(
        provider=provider,
        preprocess_version="v3.1.8",
    ).analyze(_validated_image())

    assert preprocess_thread is not None and preprocess_thread != event_loop_thread
    assert analysis.project_review["medications"][0]["strength"] == "10mg"
    assert [stage["name"] for stage in analysis.stages] == [
        "preprocess",
        "ocr",
        "candidate",
        "resolve",
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
    assert analysis.prompt_version == "medication_grounding_v4"
    assert analysis.schema_version == "medication-guide-review/v3"
    assert analysis.preprocess_version == "v3.1.8"
    assert analysis.requires_recapture is False
    assert analysis.processed_image_bytes == b"processed-jpeg"


@pytest.mark.asyncio
@pytest.mark.parametrize("recapture", [False, True])
async def test_service_reports_pinned_prompt_version_instead_of_default(monkeypatch, recapture):
    from app.services.medication_ocr_v3 import service as service_module

    state = QualityState.RECAPTURE_REQUIRED if recapture else QualityState.PROCESSED
    monkeypatch.setattr(service_module, "preprocess_image", Mock(return_value=_processed(quality_state=state)))
    monkeypatch.setattr(service_module, "build_privacy_safe_provider_image", Mock(return_value=b"safe"))
    monkeypatch.setattr(
        service_module, "analyze_processed_image", AsyncMock(return_value=_successful_pipeline_result())
    )
    analysis = await MedicationOcrV3Service(
        provider=object(), structurer=SimpleNamespace(prompt_version="medication_grounding_v3")
    ).analyze(_validated_image())
    assert analysis.prompt_version == "medication_grounding_v3"


@pytest.mark.asyncio
async def test_recapture_returns_typed_six_stage_result_without_provider_calls(monkeypatch) -> None:
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
        "resolve",
        "llm",
        "validate",
    ]
    assert [stage["status"] for stage in analysis.stages] == [
        "failed",
        "skipped",
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
async def test_provider_failures_preserve_six_stages_on_existing_job_error_classes(
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
                    StageResult("resolve", "skipped", 0, 0),
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
        {"name": "resolve", "status": "skipped", "elapsedMs": 0, "callCount": 0},
        {"name": "llm", "status": "skipped", "elapsedMs": 0, "callCount": 0},
        {"name": "validate", "status": "skipped", "elapsedMs": 0, "callCount": 0},
    ]


@pytest.mark.asyncio
async def test_preprocess_stage_includes_privacy_safe_provider_image_time(monkeypatch) -> None:
    from app.services.medication_ocr_v3 import service as service_module

    class Clock:
        value = 0.0

        def perf_counter(self) -> float:
            return self.value

        def advance(self, seconds: float) -> None:
            self.value += seconds

    clock = Clock()

    def fake_preprocess(*_args: object, **_kwargs: object) -> object:
        clock.advance(0.004)
        return _processed()

    def fake_build_provider_image(*_args: object, **_kwargs: object) -> bytes:
        clock.advance(0.007)
        return b"privacy-safe-jpeg"

    monkeypatch.setattr(service_module, "time", SimpleNamespace(perf_counter=clock.perf_counter))
    monkeypatch.setattr(service_module, "preprocess_image", fake_preprocess)
    monkeypatch.setattr(service_module, "build_privacy_safe_provider_image", fake_build_provider_image)
    monkeypatch.setattr(
        service_module, "analyze_processed_image", AsyncMock(return_value=_successful_pipeline_result())
    )

    analysis = await MedicationOcrV3Service(provider=object()).analyze(_validated_image())

    assert analysis.stages[0]["elapsedMs"] == 11


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
    assert analysis.stages[4] == {
        "name": "llm",
        "status": "failed",
        "elapsedMs": 30,
        "callCount": 1,
        "code": "LLM_TIMEOUT",
    }
    assert analysis.structuring_model == "gpt-test"


def _missing_table_result(code="TABLE_NOT_FOUND"):
    return replace(
        _successful_pipeline_result(),
        medication_rows=MedicationRowsResult(None, (), ()),
        project_review={"fields": {}, "medications": [], "lowConfidenceCount": 0},
        stages=(
            StageResult("ocr", "succeeded", 20, 1),
            StageResult("candidate", "failed", 2, 0, code),
            *(StageResult(name, "skipped", 0, 0, "UPSTREAM_FAILED") for name in ("resolve", "llm", "validate")),
        ),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("second_fails", [False, True])
async def test_missing_table_retries_once_without_unsharp_and_accounts_for_both_calls(monkeypatch, second_fails):
    from app.services.medication_ocr_v3 import service as subject

    first = _processed()
    alternate = _processed()
    alternate.operations = ()
    alternate.template_image.jpeg_bytes = b"alternate-jpeg"
    preprocess = Mock(side_effect=[first, alternate])
    pipeline = AsyncMock(
        side_effect=[
            _missing_table_result(),
            _missing_table_result() if second_fails else _successful_pipeline_result(),
        ]
    )
    monkeypatch.setattr(subject, "preprocess_image", preprocess)
    monkeypatch.setattr(subject, "build_privacy_safe_provider_image", lambda p, masks: p.template_image.jpeg_bytes)
    monkeypatch.setattr(subject, "analyze_processed_image", pipeline)

    result = await MedicationOcrV3Service(provider=object()).analyze(_validated_image())

    assert pipeline.await_count == 2
    assert [call.kwargs["preprocess_version"] for call in preprocess.call_args_list] == ["v3.4.1", "v3.4.2"]
    assert pipeline.call_args_list[1].args[1] == b"alternate-jpeg"
    assert result.preprocess_version == "v3.4.2"
    assert result.processed_image_bytes == b"alternate-jpeg"
    assert result.stages[1]["callCount"] == 2
    assert result.stages[1]["elapsedMs"] == 40
    assert result.stages[2]["elapsedMs"] == 4
    assert bool(result.project_review["medications"]) is not second_fails


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("version", "code"),
    [
        ("v3.4.2", "TABLE_NOT_FOUND"),
        ("v3.4.1", "AMBIGUOUS_MEDICATION_TABLE"),
    ],
)
async def test_table_retry_does_not_repeat_alternate_profile_or_bypass_ambiguity(monkeypatch, version, code):
    from app.services.medication_ocr_v3 import service as subject

    preprocess = Mock(return_value=_processed())
    pipeline = AsyncMock(return_value=_missing_table_result(code))
    monkeypatch.setattr(subject, "preprocess_image", preprocess)
    monkeypatch.setattr(subject, "build_privacy_safe_provider_image", Mock(return_value=b"safe"))
    monkeypatch.setattr(subject, "analyze_processed_image", pipeline)
    result = await MedicationOcrV3Service(provider=object(), preprocess_version=version).analyze(_validated_image())
    assert pipeline.await_count == 1
    assert preprocess.call_count == 1
    assert result.project_review["medications"] == []


@pytest.mark.asyncio
async def test_cancel_before_table_retry_does_not_make_second_provider_call(monkeypatch):
    from app.services.medication_ocr_v3 import service as subject

    pipeline = AsyncMock(return_value=_missing_table_result())
    monkeypatch.setattr(subject, "preprocess_image", Mock(return_value=_processed()))
    monkeypatch.setattr(subject, "build_privacy_safe_provider_image", Mock(return_value=b"safe"))
    monkeypatch.setattr(subject, "analyze_processed_image", pipeline)
    with pytest.raises(subject.MedicationOcrV3CancelledError):
        await MedicationOcrV3Service(provider=object(), is_cancelled=AsyncMock(return_value=True)).analyze(
            _validated_image()
        )
    assert pipeline.await_count == 1


@pytest.mark.asyncio
async def test_table_retry_rejects_unsafe_alternate_without_another_ocr_call(monkeypatch):
    from app.services.medication_ocr_v3 import service as subject

    pipeline = AsyncMock(return_value=_missing_table_result())
    monkeypatch.setattr(
        subject,
        "preprocess_image",
        Mock(side_effect=[_processed(), _processed(quality_state=QualityState.RECAPTURE_REQUIRED)]),
    )
    monkeypatch.setattr(subject, "build_privacy_safe_provider_image", Mock(return_value=b"safe"))
    monkeypatch.setattr(subject, "analyze_processed_image", pipeline)
    result = await MedicationOcrV3Service(provider=object()).analyze(_validated_image())
    assert pipeline.await_count == 1
    assert result.preprocess_version == "v3.4.1"
    assert result.project_review["medications"] == []


@pytest.mark.asyncio
async def test_provider_failure_on_table_retry_reports_both_ocr_calls(monkeypatch):
    from app.services.medication_ocr_v3 import service as subject

    failure = AnalyzePipelineFailure(
        code=OcrErrorCode.OCR_TIMEOUT,
        status_code=504,
        stages=(StageResult("ocr", "failed", 30, 1, "OCR_TIMEOUT"),),
    )
    pipeline = AsyncMock(side_effect=[_missing_table_result(), failure])
    monkeypatch.setattr(subject, "preprocess_image", Mock(return_value=_processed()))
    monkeypatch.setattr(subject, "build_privacy_safe_provider_image", Mock(return_value=b"safe"))
    monkeypatch.setattr(subject, "analyze_processed_image", pipeline)
    with pytest.raises(OcrProviderTimeoutError) as error:
        await MedicationOcrV3Service(provider=object()).analyze(_validated_image())
    assert pipeline.await_count == 2
    assert error.value.stages[1]["callCount"] == 2
    assert error.value.stages[1]["elapsedMs"] == 50


@pytest.mark.asyncio
async def test_missing_table_without_sharpening_does_not_retry(monkeypatch):
    from app.services.medication_ocr_v3 import service as subject

    processed = _processed()
    processed.operations = ()
    pipeline = AsyncMock(return_value=_missing_table_result())
    monkeypatch.setattr(subject, "preprocess_image", Mock(return_value=processed))
    monkeypatch.setattr(subject, "build_privacy_safe_provider_image", Mock(return_value=b"safe"))
    monkeypatch.setattr(subject, "analyze_processed_image", pipeline)
    await MedicationOcrV3Service(provider=object()).analyze(_validated_image())
    assert pipeline.await_count == 1
