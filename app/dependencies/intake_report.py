from fastapi import Request
from qdrant_client import AsyncQdrantClient

from ai_worker.core.config import Config as AIConfig
from ai_worker.domain.errors import AIWorkerError
from ai_worker.services.intake_report_core_service import (
    build_intake_report_core_service,
)
from app.core.exceptions import IntakeReportUpstreamUnavailableError
from app.services.email_jobs import EmailJobService
from app.services.intake_report import IntakeReportApplicationService
from app.services.intake_report_email import IntakeReportEmailService


async def get_intake_report_application_service(
    request: Request,
) -> IntakeReportApplicationService:
    """프로세스 단위 Report Core와 Qdrant 연결을 재사용한다."""
    existing = getattr(
        request.app.state,
        "intake_report_application_service",
        None,
    )
    if existing is not None:
        return existing

    settings = AIConfig()
    qdrant_client = AsyncQdrantClient(
        url=settings.QDRANT_URL,
        timeout=settings.QDRANT_TIMEOUT_SECONDS,
    )
    try:
        core_service = build_intake_report_core_service(
            settings=settings,
            qdrant_client=qdrant_client,
        )
    except AIWorkerError as error:
        await qdrant_client.close()
        raise IntakeReportUpstreamUnavailableError(
            "보고서 생성 설정을 확인해 주세요.",
        ) from error

    service = IntakeReportApplicationService(
        core_service=core_service,
        tracer=core_service.tracer,
    )
    request.app.state.intake_report_qdrant_client = qdrant_client
    request.app.state.intake_report_tracer = core_service.tracer
    request.app.state.intake_report_application_service = service
    return service


def get_intake_report_email_service() -> IntakeReportEmailService:
    return IntakeReportEmailService()


def get_intake_report_email_job_service() -> EmailJobService:
    return EmailJobService()
