from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.api_timeout import api_timeout
from app.dependencies.intake_report import get_intake_report_application_service
from app.dependencies.security import get_request_user
from app.dtos.intake_reports import (
    GenerateIntakeReportRequest,
    IntakeReportErrorResponse,
    IntakeReportResponse,
)
from app.models.users import User
from app.services.intake_report import (
    INTAKE_REPORT_API_GUARD_TIMEOUT_SECONDS,
    IntakeReportApplicationService,
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
        "description": "30초 안에 보고서 생성을 완료하지 못함",
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
) -> IntakeReportResponse:
    del data
    result = await service.generate(user=user)
    return IntakeReportResponse.from_result(result)
