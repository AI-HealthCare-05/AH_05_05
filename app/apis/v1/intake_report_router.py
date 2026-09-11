from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.api_timeout import api_timeout
from app.dependencies.intake_report import (
    get_intake_report_application_service,
    get_intake_report_email_job_service,
    get_intake_report_email_service,
)
from app.dependencies.security import get_request_user
from app.dtos.intake_reports import (
    GenerateIntakeReportRequest,
    IntakeReportEmailJobResponse,
    IntakeReportErrorResponse,
    IntakeReportResponse,
    SendIntakeReportEmailRequest,
)
from app.models.background_jobs import BackgroundJob
from app.models.enums import BackgroundJobStatus, BackgroundJobType
from app.models.users import User
from app.services.email_jobs import EmailJobService
from app.services.intake_report import (
    INTAKE_REPORT_API_GUARD_TIMEOUT_SECONDS,
    IntakeReportApplicationService,
)
from app.services.intake_report_email import (
    IntakeReportEmailNotVerifiedError,
    IntakeReportEmailService,
    IntakeReportEmailTokenError,
)

intake_report_router = APIRouter(prefix="/intake-reports", tags=["intake-reports"])

_INTAKE_REPORT_RESPONSES = {
    200: {
        "description": "현재 활성 복용정보 기반 보고서 생성 완료",
    },
    401: {
        "model": IntakeReportErrorResponse,
        "description": "로그인이 필요하거나 인증 정보가 유효하지 않음",
        "content": {
            "application/json": {
                "example": {
                    "code": "UNAUTHORIZED",
                    "message": "인증이 필요합니다.",
                }
            }
        },
    },
    502: {
        "model": IntakeReportErrorResponse,
        "description": "수정 재생성 후에도 보고서 검증에 실패함. 대체 보고서는 반환하지 않음",
        "content": {
            "application/json": {
                "example": {
                    "code": "INTAKE_REPORT_GENERATION_FAILED",
                    "message": "AI 보고서가 검증을 통과하지 못해 표시하지 않았어요. 다시 시도해주세요.",
                }
            }
        },
    },
    503: {
        "model": IntakeReportErrorResponse,
        "description": "활성 복용정보 또는 보고서 생성 서비스를 일시적으로 사용할 수 없음",
        "content": {
            "application/json": {
                "example": {
                    "code": "INTAKE_REPORT_UPSTREAM_UNAVAILABLE",
                    "message": "보고서를 생성하지 못했습니다. 잠시 후 다시 시도해 주세요.",
                }
            }
        },
    },
    504: {
        "model": IntakeReportErrorResponse,
        "description": f"{INTAKE_REPORT_API_GUARD_TIMEOUT_SECONDS:g}초의 요청 제한 또는 모델 생성 시간 제한을 초과함",
        "content": {
            "application/json": {
                "example": {
                    "code": "INTAKE_REPORT_TIMEOUT",
                    "message": "보고서 생성 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
                }
            }
        },
    },
}


@intake_report_router.post(
    "",
    response_model=IntakeReportResponse,
    summary="내 복용약·영양제 생활관리 보고서 생성",
    description=(
        "인증 사용자의 현재 활성 의약품과 영양제를 함께 분석해 카드·표·차트 데이터와 "
        "제한된 Markdown 보고서를 반환합니다. 채팅 세션이나 메시지는 만들지 않으며, "
        "등록 정보·승인 규칙·보유 근거 안에서만 안내합니다."
    ),
    responses=_INTAKE_REPORT_RESPONSES,
)
@api_timeout(INTAKE_REPORT_API_GUARD_TIMEOUT_SECONDS)
async def generate_intake_report(
    data: GenerateIntakeReportRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[
        IntakeReportApplicationService,
        Depends(get_intake_report_application_service),
    ],
    email_service: Annotated[IntakeReportEmailService, Depends(get_intake_report_email_service)],
) -> IntakeReportResponse:
    del data
    result = await service.generate(user=user)
    response = IntakeReportResponse.from_result(result)
    if result.status.value != "EMPTY" and isinstance(getattr(user, "email", None), str):
        response.email_token = email_service.create_snapshot_token(
            user=user,
            report_markdown=result.report_markdown,
        )
    return response


@intake_report_router.post(
    "/email",
    response_model=IntakeReportEmailJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="현재 표시한 복용약·영양제 보고서 이메일 발송",
)
async def send_intake_report_email(
    data: SendIntakeReportEmailRequest,
    user: Annotated[User, Depends(get_request_user)],
    email_service: Annotated[IntakeReportEmailService, Depends(get_intake_report_email_service)],
    email_job_service: Annotated[EmailJobService, Depends(get_intake_report_email_job_service)],
) -> IntakeReportEmailJobResponse:
    try:
        snapshot = email_service.consume_snapshot_token(token=data.email_token, user=user)
        recipient_email = await email_service.require_verified_recipient(user=user)
    except IntakeReportEmailTokenError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IntakeReportEmailNotVerifiedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    job = await email_job_service.enqueue_intake_report(
        user_id=user.id,
        recipient_email=recipient_email,
        report_markdown=snapshot.report_markdown,
        report_id=snapshot.report_id,
    )
    if job.status is BackgroundJobStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="이메일 발송을 접수하지 못했습니다. 보고서를 새로 만든 뒤 다시 시도해 주세요.",
        )
    return IntakeReportEmailJobResponse(job_id=job.id, status=job.status.value)


@intake_report_router.get(
    "/email/{job_id}",
    response_model=IntakeReportEmailJobResponse,
    summary="내 보고서 이메일 발송 상태 확인",
)
async def get_intake_report_email_job(
    job_id: int,
    user: Annotated[User, Depends(get_request_user)],
) -> IntakeReportEmailJobResponse:
    job = await BackgroundJob.filter(
        id=job_id,
        user_id=user.id,
        job_type=BackgroundJobType.EMAIL,
        reference_table="intake_reports",
    ).first()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report email job not found.")
    return IntakeReportEmailJobResponse(job_id=job.id, status=job.status.value)
