from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.dependencies.security import get_request_user
from app.dtos.settings import NotifySettingsResponse, NotifySettingsUpdateRequest
from app.models.users import User, UserSettings
from app.services.settings import NotifySettingsService, normalize_medication_time

settings_router = APIRouter(prefix="/me/settings", tags=["settings"])


def _response(settings: UserSettings) -> NotifySettingsResponse:
    return NotifySettingsResponse(
        notify_medication=settings.is_notify_medication,
        notify_supplement=settings.is_notify_supplement,
        notify_schedule=settings.is_notify_schedule,
        notify_consented_at=settings.notify_consented_at,
        morning_medication_time=normalize_medication_time(settings.morning_medication_time),
        lunch_medication_time=normalize_medication_time(settings.lunch_medication_time),
        evening_medication_time=normalize_medication_time(settings.evening_medication_time),
        bedtime_medication_time=normalize_medication_time(settings.bedtime_medication_time),
    )


@settings_router.get("", response_model=NotifySettingsResponse, status_code=status.HTTP_200_OK)
async def get_notify_settings(
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[NotifySettingsService, Depends(NotifySettingsService)],
) -> NotifySettingsResponse:
    return _response(await service.get(user))


@settings_router.patch("", response_model=NotifySettingsResponse, status_code=status.HTTP_200_OK)
async def update_notify_settings(
    data: NotifySettingsUpdateRequest,
    user: Annotated[User, Depends(get_request_user)],
    service: Annotated[NotifySettingsService, Depends(NotifySettingsService)],
) -> NotifySettingsResponse:
    return _response(await service.update(user, data))
