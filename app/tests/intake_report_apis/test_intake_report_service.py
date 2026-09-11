import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from ai_worker.domain.errors import IntakeReportGenerationError
from ai_worker.schemas.intake_report import IntakeReportResult
from app.core.exceptions import AppError, IntakeReportTimeoutError
from app.services.intake_report import IntakeReportApplicationService


class EmptyCore:
    async def generate(self, *, user_id: int) -> IntakeReportResult:
        return IntakeReportResult.empty(user_id=user_id)


class BlockingCore:
    async def generate(self, *, user_id: int) -> IntakeReportResult:
        del user_id
        await asyncio.Event().wait()


class RecordingSpan:
    trace_id = "22222222-2222-4222-8222-222222222222"

    def __init__(self) -> None:
        self.outputs = None

    def end(self, outputs=None) -> None:
        self.outputs = outputs


class RecordingTracer:
    capture_content = False

    def __init__(self) -> None:
        self.name = None
        self.metadata = None
        self.span_instance = RecordingSpan()

    @asynccontextmanager
    async def span(self, name, **kwargs):
        self.name = name
        self.metadata = kwargs.get("metadata")
        yield self.span_instance

    def anonymize_identifier(self, value):
        return f"key-{value}"

    async def aclose(self) -> None:
        return None


async def test_generate_traces_anonymized_user_and_empty_status() -> None:
    tracer = RecordingTracer()
    service = IntakeReportApplicationService(
        core_service=EmptyCore(),
        tracer=tracer,
    )

    result = await service.generate(user=SimpleNamespace(id=7))

    assert result.status == "EMPTY"
    assert tracer.name == "intake-report.generate"
    assert tracer.metadata == {"user_key": "key-7"}
    assert tracer.span_instance.outputs["report_status"] == "EMPTY"


async def test_generate_raises_timeout_when_core_exceeds_guard() -> None:
    service = IntakeReportApplicationService(
        core_service=BlockingCore(),
        timeout_seconds=0.001,
    )

    with pytest.raises(IntakeReportTimeoutError):
        await service.generate(user=SimpleNamespace(id=7))


@pytest.mark.parametrize(
    "reason, expected_code",
    [
        ("VALIDATION_FAILED", "INTAKE_REPORT_GENERATION_FAILED"),
        ("TIMEOUT", "INTAKE_REPORT_TIMEOUT"),
        ("CLIENT_ERROR", "INTAKE_REPORT_UPSTREAM_UNAVAILABLE"),
    ],
)
async def test_generation_failure_reaches_retryable_error_instead_of_report(reason, expected_code) -> None:
    class FailedCore:
        async def generate(self, *, user_id):
            raise IntakeReportGenerationError(reason_code=reason, issue_codes=("MISSING_PRODUCTS",))

    tracer = RecordingTracer()
    service = IntakeReportApplicationService(core_service=FailedCore(), tracer=tracer)
    with pytest.raises(AppError) as caught:
        await service.generate(user=SimpleNamespace(id=7))
    assert caught.value.code == expected_code
    assert tracer.span_instance.outputs["reason_code"] == reason
    assert tracer.span_instance.outputs["issue_codes"] == ["MISSING_PRODUCTS"]
