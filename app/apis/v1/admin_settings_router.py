from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies.admin import AuthenticatedAdmin, require_admin
from app.dtos.admin_settings import SmtpSettingsResponse, SmtpSettingsUpdateRequest
from app.services.admin_settings import SmtpSettingsService

admin_settings_router = APIRouter(prefix="/admin/settings", tags=["admin-settings"])
AdminOnly = Annotated[AuthenticatedAdmin, Depends(require_admin)]


def get_smtp_settings_service() -> SmtpSettingsService:
    return SmtpSettingsService()


@admin_settings_router.get(
    "/smtp",
    response_model=SmtpSettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="SMTP 설정 조회",
)
async def get_smtp_settings(
    _: AdminOnly,
    service: Annotated[SmtpSettingsService, Depends(get_smtp_settings_service)],
) -> SmtpSettingsResponse:
    """ADMIN이 현재 SMTP 설정을 조회한다. 비밀번호는 존재 여부만 반환한다."""
    return await service.get()


@admin_settings_router.put(
    "/smtp",
    response_model=SmtpSettingsResponse,
    status_code=status.HTTP_200_OK,
    summary="SMTP 설정 저장",
)
async def update_smtp_settings(
    actor: AdminOnly,
    request: SmtpSettingsUpdateRequest,
    service: Annotated[SmtpSettingsService, Depends(get_smtp_settings_service)],
) -> SmtpSettingsResponse:
    """ADMIN이 SMTP 설정을 생성·수정한다. 비밀번호 미전송·빈 값은 기존 암호문을 유지한다."""
    return await service.update(request, actor_admin_id=actor.admin_id)
